"""RS232 protocol handler for multi-zone amplifier communication.

This module provides async serial communication with rate limiting
and proper connection management.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from typing import TYPE_CHECKING, Any

from ratelimit import limits

if TYPE_CHECKING:
    from asyncio import AbstractEventLoop
    from collections.abc import Callable

LOG = logging.getLogger(__name__)

# protocol configuration keys
CONF_COMMAND_EOL = 'command_eol'
CONF_RESPONSE_EOL = 'response_eol'
CONF_COMMAND_SEPARATOR = 'command_separator'
CONF_THROTTLE_RATE = 'min_time_between_commands'

DEFAULT_TIMEOUT = 1.0
RATE_LIMIT_PERIOD_SECONDS = 300  # 5 minutes


async def async_get_rs232_protocol(
    serial_port: str,
    config: dict[str, Any],
    serial_config: dict[str, Any],
    protocol_config: dict[str, Any],
    loop: AbstractEventLoop,
) -> RS232ControlProtocol:
    """Create an async RS232 protocol handler.

    Args:
        serial_port: Serial port path or URL.
        config: Device configuration dictionary.
        serial_config: Serial port settings (baudrate, parity, etc).
        protocol_config: Protocol-specific settings.
        loop: Event loop for async operations.

    Returns:
        Configured RS232ControlProtocol instance.
    """
    factory = functools.partial(
        RS232ControlProtocol,
        serial_port,
        config,
        serial_config,
        protocol_config,
        loop,
    )
    LOG.info('Creating RS232 connection: port=%s, config=%s', serial_port, serial_config)

    # defer import to avoid blocking in event loop
    def _import_serial_asyncio() -> Callable[..., Any]:
        from serial_asyncio import create_serial_connection
        return create_serial_connection

    create_serial_connection = await loop.run_in_executor(None, _import_serial_asyncio)

    _, protocol = await create_serial_connection(
        loop, factory, serial_port, **serial_config
    )
    return protocol  # type: ignore[return-value]


class RS232ControlProtocol(asyncio.Protocol):
    """Async protocol handler for RS232 amplifier communication.

    Handles connection management, request throttling, and response parsing
    for multi-zone amplifier serial protocols.
    """

    def __init__(
        self,
        serial_port: str,
        config: dict[str, Any],
        serial_config: dict[str, Any],
        protocol_config: dict[str, Any],
        loop: AbstractEventLoop,
    ) -> None:
        """Initialize the RS232 protocol handler.

        Args:
            serial_port: Serial port path or URL.
            config: Device configuration dictionary.
            serial_config: Serial port settings.
            protocol_config: Protocol-specific settings.
            loop: Event loop for async operations.
        """
        super().__init__()

        self._serial_port = serial_port
        self._config = config
        self._serial_config = serial_config
        self._protocol_config = protocol_config
        self._loop = loop

        self._last_send = time.time() - 1
        self._timeout = float(config.get('timeout', DEFAULT_TIMEOUT))
        LOG.debug('Protocol initialized: port=%s, timeout=%s', serial_port, self._timeout)

        self._transport: Any = None
        self._connected = asyncio.Event()
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._lock = asyncio.Lock()

    def connection_made(self, transport: Any) -> None:
        """Handle successful connection establishment."""
        self._transport = transport
        LOG.debug('Port opened: port=%s, transport=%s', self._serial_port, transport)
        self._connected.set()

    def data_received(self, data: bytes) -> None:
        """Handle incoming data from serial port."""
        asyncio.ensure_future(self._queue.put(data))

    def connection_lost(self, exc: Exception | None) -> None:
        """Handle connection closure."""
        LOG.debug('Port closed: port=%s', self._serial_port)

    async def _throttle_requests(self) -> None:
        """Enforce minimum time between RS232 commands to prevent timeouts."""
        min_time = self._config.get(CONF_THROTTLE_RATE, 0.05)
        delta = time.time() - self._last_send

        if delta < 0:
            delay = -delta
            LOG.debug('Clock skew detected, sleeping: delay=%s', delay)
            await asyncio.sleep(delay)
        elif delta < min_time:
            delay = min(max(0, min_time - delta), min_time)
            await asyncio.sleep(delay)

    async def _wait_for_connection(self) -> bool:
        """Wait for connection to be established.

        Returns:
            True if connected, False if timeout.
        """
        try:
            await asyncio.wait_for(self._connected.wait(), self._timeout)
            return True
        except asyncio.TimeoutError:
            LOG.debug('Connection timeout: port=%s', self._serial_port)
            return False

    async def send(
        self,
        request: bytes,
        *,
        wait_for_reply: bool = True,
        skip: int = 0,
    ) -> str:
        """Send command and optionally wait for response.

        Args:
            request: Command bytes to send.
            wait_for_reply: Whether to wait for and return response.
            skip: Number of bytes to skip when looking for EOL.

        Returns:
            Response string, or empty string if no reply expected/received.

        Raises:
            asyncio.TimeoutError: If response not received within timeout.
        """
        async with self._lock:
            if not await self._wait_for_connection():
                return ''

            await self._throttle_requests()

            # clear buffers before sending
            self._transport.serial.reset_output_buffer()
            self._transport.serial.reset_input_buffer()
            while not self._queue.empty():
                self._queue.get_nowait()

            LOG.debug('Sending RS232 command: request=%s', request)
            self._last_send = time.time()
            self._transport.serial.write(request)

            if not wait_for_reply:
                return ''

            return await self._read_response(skip)

    async def _read_response(self, skip: int) -> str:
        """Read and parse response from serial port.

        Args:
            skip: Number of bytes to skip when looking for EOL.

        Returns:
            Parsed response string.

        Raises:
            asyncio.TimeoutError: If response not received within timeout.
        """
        data = bytearray()
        response_eol = self._protocol_config.get(CONF_RESPONSE_EOL, '\r').encode('ascii')

        try:
            while True:
                chunk = await asyncio.wait_for(self._queue.get(), self._timeout)
                data += chunk

                if response_eol in data[skip:]:
                    decoded = bytes(data).decode('ascii', errors='ignore')
                    LOG.debug(
                        'Received response: data=%s, length=%d, eol=%s',
                        decoded,
                        len(data),
                        response_eol,
                    )

                    result_lines = [
                        line for line in data.split(response_eol)
                        if line
                    ]

                    if not result_lines:
                        return ''

                    if len(result_lines) > 1:
                        LOG.debug(
                            'Multiple response lines, using first: lines=%s',
                            result_lines,
                        )

                    return result_lines[0].decode('ascii', errors='ignore')

        except asyncio.TimeoutError:
            self._log_timeout(request=b'', data=data, response_eol=response_eol)
            raise

    @limits(calls=2, period=RATE_LIMIT_PERIOD_SECONDS)
    def _log_timeout(
        self,
        request: bytes,
        data: bytearray,
        response_eol: bytes,
    ) -> None:
        """Log timeout with rate limiting to prevent log saturation."""
        LOG.info(
            "Request timeout: request=%s, received=%s, timeout=%s, eol=%s",
            request,
            bytes(data),
            self._timeout,
            response_eol,
        )
