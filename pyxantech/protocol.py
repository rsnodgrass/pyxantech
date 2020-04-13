import logging

import functools
import serial

import asyncio
#import serial_asyncio

LOG = logging.getLogger(__name__)

CONF_EOL = 'eol'

async def get_rs232_async_protocol(serial_port_url, serial_config, protocol_config, loop):
    import serial_asyncio

    class RS232ControlProtocol(asyncio.Protocol):
        def __init__(self, serial_port_url, serial_config, protocol_config, loop):
            super().__init__()

            self._serial_port_url = serial_port_url
            self._serial_config = serial_config
            self._timeout = self._serial_config.get('timeout')

            self._protocol_config = protocol_config
            self._loop = loop

            self._lock = asyncio.Lock()
            self._transport = None
            self._connected = asyncio.Event(loop=loop)
            self._q = asyncio.Queue(loop=loop)

        def connection_made(self, transport):
            self._transport = transport
            self._connected.set()
            LOG.debug(f"Port {self._serial_port_url} opened {self._transport}")

        def data_received(self, data):
            asyncio.ensure_future(self._q.put(data), loop=self._loop)

        def connection_lost(self, exc):
            LOG.info(f"Port {self._serial_port_url} closed")

        async def send(self, request: bytes, skip=0):
            await self._connected.wait()
            result = bytearray()

            eol = self._protocol_config.get(CONF_EOL)
            if eol == None:
                eol = '\n'
            len_eol = len(eol)

            # only one write/read at a time
            with (await self._lock):
                # clear all waiting to be received data before sending the command
                self._transport.serial.reset_output_buffer()
                self._transport.serial.reset_input_buffer()
                while not self._q.empty():
                    self._q.get_nowait()

                # send the request
                self._transport.write(request)

                # read the response
                try:
                    while True:
                        result += await asyncio.wait_for(self._q.get(), self._timeout, loop=self._loop)
                        if len(result) > skip and result[-len_eol:] == eol:
                            ret = bytes(result)
                            LOG.debug('Received "%s"', ret)
                            return ret.decode('ascii')
                except asyncio.TimeoutError:
                    LOG.error("Timeout receiving response for '%s': received='%s'", request, result)
                    raise

    factory = functools.partial(RS232ControlProtocol, serial_port_url, serial_config, protocol_config, loop)
    _, protocol = await serial_asyncio.create_serial_connection(loop, factory, serial_port_url, **serial_config)
    return protocol