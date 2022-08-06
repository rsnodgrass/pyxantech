import logging

import time
import asyncio
import functools
from serial_asyncio import create_serial_connection
from ratelimit import limits

LOG = logging.getLogger(__name__)

CONF_COMMAND_EOL = 'command_eol'
CONF_RESPONSE_EOL = 'response_eol'
CONF_COMMAND_SEPARATOR = 'command_separator'

CONF_THROTTLE_RATE = 'min_time_between_commands'
DEFAULT_TIMEOUT = 1.0

MINUTES = 300


async def async_get_rs232_protocol(serial_port, config, serial_config, protocol_config, loop):

    # ensure only a single, ordered command is sent to RS232 at a time (non-reentrant lock)
    def locked_method(method):
        @functools.wraps(method)
        async def wrapper(self, *method_args, **method_kwargs):
            async with self._lock:
                return await method(self, *method_args, **method_kwargs)
        return wrapper

    # check if connected, and abort calling provided method if no connection before timeout
    def ensure_connected(method):
        @functools.wraps(method)
        async def wrapper(self, *method_args, **method_kwargs):
            try:
                await asyncio.wait_for(self._connected.wait(), self._timeout)
            except:
                LOG.debug(f"Timeout sending data to {self._serial_port}, no connection!")
                return
            return await method(self, *method_args, **method_kwargs)
        return wrapper

    class RS232ControlProtocol(asyncio.Protocol):
        def __init__(self, serial_port, config, serial_config, protocol_config, loop):
            super().__init__()

            self._serial_port = serial_port
            self._config = config
            self._serial_config = serial_config
            self._protocol_config = protocol_config
            self._loop = loop

            self._last_send = time.time() - 1
            self._timeout = self._config.get('timeout', DEFAULT_TIMEOUT)
            LOG.info(f"Timeout set to {self._timeout}")

            self._transport = None
            self._connected = asyncio.Event(loop=loop)
            self._q = asyncio.Queue(loop=loop)

            # ensure only a single, ordered command is sent to RS232 at a time (non-reentrant lock)
            self._lock = asyncio.Lock()

        def connection_made(self, transport):
            self._transport = transport
            LOG.debug(f"Port {self._serial_port} opened {self._transport}")
            self._connected.set()

        def data_received(self, data):
#            LOG.debug(f"Received from {self._serial_port}: {data}")
            asyncio.ensure_future(self._q.put(data), loop=self._loop)

        def connection_lost(self, exc):
            LOG.debug(f"Port {self._serial_port} closed")

        async def _throttle_requests(self):
            """Throttle the number of RS232 sends per second to avoid causing timeouts"""
            min_time_between_commands = self._config[CONF_THROTTLE_RATE]
            delta_since_last_send = time.time() - self._last_send

            if delta_since_last_send < 0:
                delay = -1 * delta_since_last_send
                LOG.debug(f"Sleeping {delay} seconds until sending next RS232 request")
                await asyncio.sleep(delay)

            elif delta_since_last_send < min_time_between_commands:
                delay = min(max(0, min_time_between_commands -
                            delta_since_last_send), min_time_between_commands)
                await asyncio.sleep(delay)

        @locked_method
        @ensure_connected
        async def send(self, request: bytes, wait_for_reply=True, skip=0):
            await self._throttle_requests()

            # clear all buffers of any data waiting to be read before sending the request
            self._transport.serial.reset_output_buffer()
            self._transport.serial.reset_input_buffer()
            while not self._q.empty():
                self._q.get_nowait()

            # send the request
            LOG.debug("Sending RS232 data %s", request)
            self._last_send = time.time()
            self._transport.serial.write(request)

            if not wait_for_reply:
                return

            # read the response
            data = bytearray()
            response_eol = self._protocol_config[CONF_RESPONSE_EOL].encode('ascii')
            try:
                while True:
                    data += await asyncio.wait_for(self._q.get(), self._timeout, loop=self._loop)
                    if response_eol in data[skip:]:
                        # only return the first line
                        LOG.debug(f"Received: %s (eol={response_eol})", bytes(data).decode('ascii'))
                        result_lines = data.split(response_eol)

                        # strip out any blank lines
                        result_lines = [value for value in result_lines if value != b'']

                        if len(result_lines) > 1:
                            LOG.debug("Multiple response lines, ignore all but first: %s", result_lines)
                        
                        if len(result_lines) == 0:
                            return ''

                        result = result_lines[0].decode('ascii')
                        return result

            except asyncio.TimeoutError:
                # log up to two times within a time period to avoid saturating the logs
                @limits(calls=2, period=5*MINUTES)
                def log_timeout():
                    LOG.info(f"Timeout for request '%s': received='%s' ({self._timeout} s; eol={response_eol})", request, data)
                log_timeout()
                raise

    factory = functools.partial(RS232ControlProtocol, serial_port, config, serial_config, protocol_config, loop)
    LOG.info(f"Creating RS232 connection to {serial_port}: {serial_config}")
    _, protocol = await create_serial_connection(loop, factory, serial_port, **serial_config)
    return protocol
