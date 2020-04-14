import logging

import time
import asyncio
import functools
import serial
from serial_asyncio import create_serial_connection

LOG = logging.getLogger(__name__)

CONF_EOL = 'command_eol'
CONF_THROTTLE_RATE = 'min_time_between_commands'

async def get_async_rs232_protocol(serial_port_url, serial_config, protocol_config, loop):

    lock = asyncio.Lock()

    def locked_coro(coro):
        """While this is asynchronous, ensure only a single, ordered command is sent to RS232 at a time (non-reentrant lock)"""
        @wraps(coro)
        async def wrapper(*args, **kwargs):
            LOG.debug("Waiting on coro lock: %s %s", args, kwargs)
            with (await lock):
                LOG.debug("Lock acquired! %s %s", args, kwargs)
                return (await coro(*args, **kwargs))
        return wrapper

    class RS232ControlProtocol(asyncio.Protocol):
        def __init__(self, serial_port_url, protocol_config, loop):
            super().__init__()

            self._serial_port_url = serial_port_url
            self._config = protocol_config
            self._loop = loop

            self._timeout = self._config.get('timeout')
            if self._timeout is None:
                self._timeout = 1.0 # default to 1 second if None
            LOG.info(f"Timeout set to {self._timeout}")
            
            self._last_send = time.time() - 1

            self._lock = asyncio.Lock()
            self._transport = None
            self._connected = asyncio.Event(loop=loop)
            self._q = asyncio.Queue(loop=loop)

        def connection_made(self, transport):
            self._transport = transport
            self._connected.set()
            LOG.debug(f"Port {self._serial_port_url} opened {self._transport}")

        def data_received(self, data):
#            LOG.debug(f"Received from {self._serial_port_url}: {data}")
            asyncio.ensure_future(self._q.put(data), loop=self._loop)

        def connection_lost(self, exc):
            LOG.debug(f"Port {self._serial_port_url} closed")

#        @locked_coro
        async def send(self, request: bytes, wait_for_reply=True, skip=0):
            data = bytearray()
            eol = self._config[CONF_EOL].encode('ascii')
            min_time_between_commands = self._config[CONF_THROTTLE_RATE]

            await self._connected.wait()

            # only one write/read at a time
            with (await self._lock):
                # clear all buffers of any data waiting to be read before sending the request
                self._transport.serial.reset_output_buffer()
                self._transport.serial.reset_input_buffer()
                while not self._q.empty():
                    self._q.get_nowait()

                # throttle the number of RS232 sends per second to avoid causing timeouts
                delta_since_last_send = time.time() - self._last_send

                if delta_since_last_send < 0:
                    delay = -1 * delta_since_last_send
                    LOG.debug(f"Sleeping {delay} seconds until sending another RS232 request as {self._name} is powering up")
                    await asyncio.sleep(delay)

                elif delta_since_last_send < min_time_between_commands:
                    delay = min(max(0, min_time_between_commands - delta_since_last_send), min_time_between_commands)
                    await asyncio.sleep(delay)

                # send the request
                LOG.debug("Sending RS232 data %s", request)
                self._last_send = time.time()
                self._transport.write(request)

                # special case for power on, since the Anthem units can't accept more RS232 requests
                # for many seconds after initial powering up
                if request in [ "P1P1\n", "P2P1\n", "P1P3\n" ]:
                    self._last_send = time.time() + self._config['delay_after_power_on']

                if not wait_for_reply:
                    return

                # read the response
                try:
                    while True:
                        data += await asyncio.wait_for(self._q.get(), self._timeout, loop=self._loop)
#                        LOG.debug("Partial receive %s", bytes(data).decode('ascii'))
                        if eol in data:
                            # only return the first line
                            result_lines = data.split(eol)
                            if len(result_lines) > 1:
                                LOG.debug("Multiple response lines, ignore all but the first: %s", result_lines)

                            result = result_lines[0].decode('ascii')
#                            LOG.debug('Received "%s"', result)
                            return result
                except asyncio.TimeoutError:
                    LOG.error("Timeout receiving response for '%s': received='%s'", request, data)
                    raise

    factory = functools.partial(RS232ControlProtocol, serial_port_url, protocol_config, loop)
    LOG.debug(f"Creating RS232 connection to {serial_port_url}: {serial_config}")
    _, protocol = await create_serial_connection(loop, factory, serial_port_url, **serial_config)
    return protocol
