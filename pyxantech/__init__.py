"""Multi-zone amplifier control library for Xantech, Monoprice, and Dayton Audio.

This library provides both synchronous and asynchronous interfaces for controlling
multi-zone audio amplifiers via RS232 serial connections.

Example usage:
    # Synchronous
    amp = get_amp_controller('xantech8', '/dev/ttyUSB0')
    status = amp.zone_status(1)
    amp.set_volume(1, 20)

    # Asynchronous
    amp = await async_get_amp_controller('xantech8', '/dev/ttyUSB0', loop)
    status = await amp.zone_status(1)
    await amp.set_volume(1, 20)
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import wraps
from threading import RLock
from typing import TYPE_CHECKING, Any

import serial

from .config import (
    DEVICE_CONFIG,
    PROTOCOL_CONFIG,
    RS232_RESPONSE_PATTERNS,
    get_with_log,
)
from .protocol import (
    CONF_COMMAND_EOL,
    CONF_COMMAND_SEPARATOR,
    CONF_RESPONSE_EOL,
    RS232ControlProtocol,
    async_get_rs232_protocol,
)

if TYPE_CHECKING:
    from asyncio import AbstractEventLoop
    from collections.abc import Callable, KeysView

__all__ = [
    'ZoneStatus',
    'AmpControlBase',
    'get_amp_controller',
    'async_get_amp_controller',
    'get_async_monoprice',
    'SUPPORTED_AMP_TYPES',
    'BAUD_RATES',
    'MONOPRICE6',
]

LOG = logging.getLogger(__name__)

# backwards compatibility constant
MONOPRICE6 = 'monoprice6'
BAUD_RATES = [9600, 14400, 19200, 38400, 57600, 115200]

SUPPORTED_AMP_TYPES: KeysView[str] = DEVICE_CONFIG.keys()

CONF_SERIAL_CONFIG = 'rs232'


def get_device_config(
    amp_type: str,
    key: str,
    *,
    log_missing: bool = True,
) -> Any:
    """Get device configuration value.

    Args:
        amp_type: Amplifier type identifier.
        key: Configuration key to retrieve.
        log_missing: Whether to log a warning if key is missing.

    Returns:
        Configuration value or None if not found.
    """
    return get_with_log(amp_type, DEVICE_CONFIG[amp_type], key, log_missing=log_missing)


def get_protocol_config(amp_type: str, key: str) -> Any:
    """Get protocol configuration value for an amplifier type.

    Args:
        amp_type: Amplifier type identifier.
        key: Configuration key to retrieve.

    Returns:
        Configuration value or None if not found.
    """
    protocol = get_device_config(amp_type, 'protocol')
    return PROTOCOL_CONFIG[protocol].get(key)


@dataclass
class ZoneStatus:
    """Represents the current status of an amplifier zone.

    Attributes:
        zone: Zone number.
        power: Power state (on/off).
        mute: Mute state.
        volume: Volume level (0 to max_volume).
        treble: Treble level.
        bass: Bass level.
        balance: Balance level.
        source: Source input number.
        paged: Paging state.
        linked: Linked zone state.
        pa: Public address mode.
        do_not_disturb: Do not disturb mode.
        keypad: Keypad connected state.
    """

    zone: int = 0
    power: bool = False
    mute: bool = False
    volume: int = 0
    treble: int = 0
    bass: int = 0
    balance: int = 0
    source: int = 0
    paged: bool = False
    linked: bool = False
    pa: bool = False
    do_not_disturb: bool = False
    keypad: bool = False
    _raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def dict(self) -> dict[str, Any]:
        """Return status as dictionary for backwards compatibility."""
        return self._raw

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ZoneStatus:
        """Create ZoneStatus from dictionary.

        Args:
            data: Dictionary with zone status values.

        Returns:
            ZoneStatus instance with parsed values.
        """
        bool_keys = {'power', 'mute', 'paged', 'linked', 'pa', 'do_not_disturb', 'keypad'}
        int_keys = {'zone', 'volume', 'treble', 'bass', 'balance', 'source'}

        parsed: dict[str, Any] = {'_raw': data.copy()}

        for key, value in data.items():
            if key in bool_keys:
                parsed[key] = value in ('1', '01', True, 1)
            elif key in int_keys:
                try:
                    parsed[key] = int(value)
                except (ValueError, TypeError):
                    parsed[key] = 0
            elif key in cls.__dataclass_fields__:
                parsed[key] = value

        return cls(**{k: v for k, v in parsed.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_string(cls, amp_type: str, string: str | None) -> ZoneStatus | None:
        """Parse zone status from RS232 response string.

        Args:
            amp_type: Amplifier type for protocol pattern lookup.
            string: RS232 response string to parse.

        Returns:
            ZoneStatus instance or None if parsing failed.
        """
        if not string:
            return None

        protocol_type = get_device_config(amp_type, 'protocol')
        pattern = RS232_RESPONSE_PATTERNS.get(protocol_type, {}).get('zone_status')

        if pattern is None:
            LOG.warning('No zone_status pattern for protocol: %s', protocol_type)
            return None

        match = pattern.search(string)
        if not match:
            LOG.debug(
                'Could not match zone status: string=%s, pattern=%s',
                string,
                pattern.pattern,
            )
            return None

        match_dict = match.groupdict()

        # apply status translation if configured
        status_translation = get_protocol_config(amp_type, 'status_translation')
        if status_translation:
            for key, value in match_dict.items():
                if key in status_translation and value in status_translation[key]:
                    match_dict[key] = status_translation[key][value]

        return cls.from_dict(match_dict)


class AmpControlBase(ABC):
    """Abstract base class for amplifier control interfaces.

    Defines the common interface for both sync and async implementations.
    """

    @abstractmethod
    def zone_status(self, zone: int) -> dict[str, Any] | None:
        """Get the current status of a zone.

        Args:
            zone: Zone number (format varies by amp type, e.g., 11-16 for unit 1).

        Returns:
            Dictionary with zone status or None if unavailable.
        """

    @abstractmethod
    def set_power(self, zone: int, power: bool) -> None:
        """Set zone power state.

        Args:
            zone: Zone number.
            power: True to turn on, False to turn off.
        """

    @abstractmethod
    def set_mute(self, zone: int, mute: bool) -> None:
        """Set zone mute state.

        Args:
            zone: Zone number.
            mute: True to mute, False to unmute.
        """

    @abstractmethod
    def set_volume(self, zone: int, volume: int) -> None:
        """Set zone volume level.

        Args:
            zone: Zone number.
            volume: Volume level (0 to max_volume, typically 38).
        """

    @abstractmethod
    def set_treble(self, zone: int, treble: int) -> None:
        """Set zone treble level.

        Args:
            zone: Zone number.
            treble: Treble level (typically 0-14, where 7 is neutral).
        """

    @abstractmethod
    def set_bass(self, zone: int, bass: int) -> None:
        """Set zone bass level.

        Args:
            zone: Zone number.
            bass: Bass level (typically 0-14, where 7 is neutral).
        """

    @abstractmethod
    def set_balance(self, zone: int, balance: int) -> None:
        """Set zone balance.

        Args:
            zone: Zone number.
            balance: Balance level (0=left, 10=center, 20=right typically).
        """

    @abstractmethod
    def set_source(self, zone: int, source: int) -> None:
        """Set zone input source.

        Args:
            zone: Zone number.
            source: Source input number (1-6 or 1-8 depending on amp).
        """

    @abstractmethod
    def restore_zone(self, status: dict[str, Any]) -> None:
        """Restore zone to a previously saved state.

        Args:
            status: Dictionary with zone status to restore.
        """


def _command(amp_type: str, format_code: str, args: dict[str, Any] | None = None) -> bytes:
    """Build a command string for the amplifier.

    Args:
        amp_type: Amplifier type identifier.
        format_code: Command format key from protocol config.
        args: Format arguments for the command template.

    Returns:
        Encoded command bytes.
    """
    if args is None:
        args = {}

    cmd_eol = get_protocol_config(amp_type, CONF_COMMAND_EOL) or ''
    cmd_separator = get_protocol_config(amp_type, CONF_COMMAND_SEPARATOR) or ''

    rs232_commands = get_protocol_config(amp_type, 'commands')
    command = rs232_commands.get(format_code, '') + cmd_separator + cmd_eol

    return command.format(**args).encode('ascii')


def _zone_status_cmd(amp_type: str, zone: int) -> bytes:
    """Build zone status query command."""
    zones = get_device_config(amp_type, 'zones')
    if zone not in zones:
        raise ValueError(f'Invalid zone {zone} for amp type {amp_type}')
    return _command(amp_type, 'zone_status', args={'zone': zone})


def _set_power_cmd(amp_type: str, zone: int, power: bool) -> bytes:
    """Build power control command."""
    zones = get_device_config(amp_type, 'zones')
    if zone not in zones:
        raise ValueError(f'Invalid zone {zone} for amp type {amp_type}')

    if power:
        LOG.info('Powering on zone: amp_type=%s, zone=%s', amp_type, zone)
        return _command(amp_type, 'power_on', {'zone': zone})
    else:
        LOG.info('Powering off zone: amp_type=%s, zone=%s', amp_type, zone)
        return _command(amp_type, 'power_off', {'zone': zone})


def _set_mute_cmd(amp_type: str, zone: int, mute: bool) -> bytes:
    """Build mute control command."""
    zones = get_device_config(amp_type, 'zones')
    if zone not in zones:
        raise ValueError(f'Invalid zone {zone} for amp type {amp_type}')

    if mute:
        LOG.info('Muting zone: amp_type=%s, zone=%s', amp_type, zone)
        return _command(amp_type, 'mute_on', {'zone': zone})
    else:
        LOG.info('Unmuting zone: amp_type=%s, zone=%s', amp_type, zone)
        return _command(amp_type, 'mute_off', {'zone': zone})


def _set_volume_cmd(amp_type: str, zone: int, volume: int) -> bytes:
    """Build volume control command."""
    zones = get_device_config(amp_type, 'zones')
    if zone not in zones:
        raise ValueError(f'Invalid zone {zone} for amp type {amp_type}')

    max_volume = get_device_config(amp_type, 'max_volume') or 38
    volume = int(max(0, min(volume, max_volume)))
    LOG.info('Setting volume: amp_type=%s, zone=%s, volume=%s', amp_type, zone, volume)
    return _command(amp_type, 'set_volume', args={'zone': zone, 'volume': volume})


def _set_treble_cmd(amp_type: str, zone: int, treble: int) -> bytes:
    """Build treble control command."""
    zones = get_device_config(amp_type, 'zones')
    if zone not in zones:
        raise ValueError(f'Invalid zone {zone} for amp type {amp_type}')

    max_treble = get_device_config(amp_type, 'max_treble') or 14
    treble = int(max(0, min(treble, max_treble)))
    LOG.info('Setting treble: amp_type=%s, zone=%s, treble=%s', amp_type, zone, treble)
    return _command(amp_type, 'set_treble', args={'zone': zone, 'treble': treble})


def _set_bass_cmd(amp_type: str, zone: int, bass: int) -> bytes:
    """Build bass control command."""
    zones = get_device_config(amp_type, 'zones')
    if zone not in zones:
        raise ValueError(f'Invalid zone {zone} for amp type {amp_type}')

    max_bass = get_device_config(amp_type, 'max_bass') or 14
    bass = int(max(0, min(bass, max_bass)))
    LOG.info('Setting bass: amp_type=%s, zone=%s, bass=%s', amp_type, zone, bass)
    return _command(amp_type, 'set_bass', args={'zone': zone, 'bass': bass})


def _set_balance_cmd(amp_type: str, zone: int, balance: int) -> bytes:
    """Build balance control command."""
    zones = get_device_config(amp_type, 'zones')
    if zone not in zones:
        raise ValueError(f'Invalid zone {zone} for amp type {amp_type}')

    max_balance = get_device_config(amp_type, 'max_balance') or 20
    balance = max(0, min(balance, max_balance))
    LOG.info('Setting balance: amp_type=%s, zone=%s, balance=%s', amp_type, zone, balance)
    return _command(amp_type, 'set_balance', args={'zone': zone, 'balance': balance})


def _set_source_cmd(amp_type: str, zone: int, source: int) -> bytes:
    """Build source selection command."""
    zones = get_device_config(amp_type, 'zones')
    sources = get_device_config(amp_type, 'sources')

    if zone not in zones:
        raise ValueError(f'Invalid zone {zone} for amp type {amp_type}')
    if source not in sources:
        raise ValueError(f'Invalid source {source} for amp type {amp_type}')

    LOG.info('Setting source: amp_type=%s, zone=%s, source=%s', amp_type, zone, source)
    return _command(amp_type, 'set_source', args={'zone': zone, 'source': source})


def get_amp_controller(
    amp_type: str,
    port_url: str,
    serial_config_overrides: dict[str, Any] | None = None,
) -> AmpControlBase | None:
    """Create a synchronous amplifier controller.

    Args:
        amp_type: Amplifier type (e.g., 'xantech8', 'monoprice6').
        port_url: Serial port path or URL (e.g., '/dev/ttyUSB0').
        serial_config_overrides: Optional serial port configuration overrides.

    Returns:
        Synchronous amplifier control interface or None if amp_type unsupported.
    """
    if serial_config_overrides is None:
        serial_config_overrides = {}

    if amp_type not in SUPPORTED_AMP_TYPES:
        LOG.error("Unsupported amplifier type: amp_type=%s", amp_type)
        return None

    lock = RLock()

    def synchronized(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with lock:
                return func(*args, **kwargs)
        return wrapper

    class AmpControlSync(AmpControlBase):
        """Synchronous amplifier control implementation."""

        def __init__(
            self,
            amp_type: str,
            port_url: str,
            serial_config_overrides: dict[str, Any],
        ) -> None:
            self._amp_type = amp_type

            serial_config = get_device_config(amp_type, CONF_SERIAL_CONFIG)
            if serial_config_overrides:
                LOG.debug(
                    'Overriding serial config: port=%s, overrides=%s',
                    port_url,
                    serial_config_overrides,
                )
                serial_config.update(serial_config_overrides)

            self._port = serial.serial_for_url(port_url, **serial_config)

        def _send_request(self, request: bytes, skip: int = 0) -> str:
            """Send request and read response.

            Args:
                request: Command bytes to send.
                skip: Bytes to skip for EOL detection.

            Returns:
                Response string.

            Raises:
                serial.SerialTimeoutException: If no response received.
            """
            self._port.reset_output_buffer()
            self._port.reset_input_buffer()

            LOG.debug('Sending request: request=%s', request)
            self._port.write(request)
            self._port.flush()

            response_eol = get_protocol_config(amp_type, CONF_RESPONSE_EOL) or '\r'
            len_eol = len(response_eol)

            result = bytearray()
            while True:
                c = self._port.read(1)
                if not c:
                    LOG.info('Connection timed out: last_bytes=%s', [hex(a) for a in result])
                    raise serial.SerialTimeoutException(
                        f'Connection timed out! Last received: {[hex(a) for a in result]}'
                    )
                result += c
                if len(result) > skip and result[-len_eol:] == response_eol.encode('ascii'):
                    break

            ret = bytes(result)
            LOG.debug('Received response: response=%s', ret)
            return ret.decode('ascii')

        @synchronized
        def zone_status(self, zone: int) -> dict[str, Any] | None:
            skip = get_device_config(amp_type, 'zone_status_skip', log_missing=False) or 0
            response = self._send_request(_zone_status_cmd(self._amp_type, zone), skip)
            status = ZoneStatus.from_string(self._amp_type, response)
            LOG.debug('Zone status: status=%s, raw=%s', status, response)
            return status.dict if status else None

        @synchronized
        def set_power(self, zone: int, power: bool) -> None:
            self._send_request(_set_power_cmd(self._amp_type, zone, power))

        @synchronized
        def set_mute(self, zone: int, mute: bool) -> None:
            self._send_request(_set_mute_cmd(self._amp_type, zone, mute))

        @synchronized
        def set_volume(self, zone: int, volume: int) -> None:
            self._send_request(_set_volume_cmd(self._amp_type, zone, volume))

        @synchronized
        def set_treble(self, zone: int, treble: int) -> None:
            self._send_request(_set_treble_cmd(self._amp_type, zone, treble))

        @synchronized
        def set_bass(self, zone: int, bass: int) -> None:
            self._send_request(_set_bass_cmd(self._amp_type, zone, bass))

        @synchronized
        def set_balance(self, zone: int, balance: int) -> None:
            self._send_request(_set_balance_cmd(self._amp_type, zone, balance))

        @synchronized
        def set_source(self, zone: int, source: int) -> None:
            self._send_request(_set_source_cmd(self._amp_type, zone, source))

        @synchronized
        def all_off(self) -> None:
            """Turn off all zones."""
            self._send_request(_command(amp_type, 'all_zones_off'))

        @synchronized
        def restore_zone(self, status: dict[str, Any]) -> None:
            zone = status['zone']
            extras = get_protocol_config(amp_type, 'extras') or {}
            success = extras.get('restore_success')
            LOG.debug('Restoring zone: amp_type=%s, zone=%s, status=%s', amp_type, zone, status)

            restore_commands = extras.get('restore_zone', [])
            for command in restore_commands:
                result = self._send_request(command(amp_type, zone, status))
                if result != success:
                    LOG.warning('Failed restoring zone command: zone=%s, command=%s', zone, command)
                time.sleep(0.1)

    return AmpControlSync(amp_type, port_url, serial_config_overrides)


async def get_async_monoprice(
    port_url: str,
    loop: AbstractEventLoop,
) -> AmpControlBase | None:
    """Create async controller for Monoprice 6-zone amp.

    DEPRECATED: Use async_get_amp_controller('monoprice6', ...) instead.

    Args:
        port_url: Serial port path or URL.
        loop: Event loop for async operations.

    Returns:
        Async amplifier control interface.
    """
    return await async_get_amp_controller(MONOPRICE6, port_url, loop)


async def async_get_amp_controller(
    amp_type: str,
    port_url: str,
    loop: AbstractEventLoop,
    serial_config_overrides: dict[str, Any] | None = None,
) -> AmpControlBase | None:
    """Create an asynchronous amplifier controller.

    Args:
        amp_type: Amplifier type (e.g., 'xantech8', 'monoprice6').
        port_url: Serial port path or URL.
        loop: Event loop for async operations.
        serial_config_overrides: Optional serial port configuration overrides.

    Returns:
        Async amplifier control interface or None if amp_type unsupported.
    """
    if serial_config_overrides is None:
        serial_config_overrides = {}

    if amp_type not in SUPPORTED_AMP_TYPES:
        LOG.error("Unsupported amplifier type: amp_type=%s", amp_type)
        return None

    lock = asyncio.Lock()

    def locked_coro(coro: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(coro)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            async with lock:
                return await coro(*args, **kwargs)
        return wrapper

    class AmpControlAsync(AmpControlBase):
        """Asynchronous amplifier control implementation."""

        def __init__(
            self,
            amp_type: str,
            serial_config: dict[str, Any],
            protocol: RS232ControlProtocol,
        ) -> None:
            self._amp_type = amp_type
            self._serial_config = serial_config
            self._protocol = protocol

        @locked_coro
        async def zone_status(self, zone: int) -> dict[str, Any] | None:
            cmd = _zone_status_cmd(self._amp_type, zone)
            skip = get_device_config(amp_type, 'zone_status_skip', log_missing=False) or 0
            status_string = await self._protocol.send(cmd, skip=skip)

            status = ZoneStatus.from_string(self._amp_type, status_string)
            LOG.debug('Zone status: status=%s, raw=%s', status, status_string)
            return status.dict if status else None

        @locked_coro
        async def set_power(self, zone: int, power: bool) -> None:
            await self._protocol.send(_set_power_cmd(self._amp_type, zone, power))

        @locked_coro
        async def set_mute(self, zone: int, mute: bool) -> None:
            await self._protocol.send(_set_mute_cmd(self._amp_type, zone, mute))

        @locked_coro
        async def set_volume(self, zone: int, volume: int) -> None:
            await self._protocol.send(_set_volume_cmd(self._amp_type, zone, volume))

        @locked_coro
        async def set_treble(self, zone: int, treble: int) -> None:
            await self._protocol.send(_set_treble_cmd(self._amp_type, zone, treble))

        @locked_coro
        async def set_bass(self, zone: int, bass: int) -> None:
            await self._protocol.send(_set_bass_cmd(self._amp_type, zone, bass))

        @locked_coro
        async def set_balance(self, zone: int, balance: int) -> None:
            await self._protocol.send(_set_balance_cmd(self._amp_type, zone, balance))

        @locked_coro
        async def set_source(self, zone: int, source: int) -> None:
            await self._protocol.send(_set_source_cmd(self._amp_type, zone, source))

        @locked_coro
        async def all_off(self) -> None:
            """Turn off all zones."""
            await self._protocol.send(_command(self._amp_type, 'all_zones_off'))

        @locked_coro
        async def restore_zone(self, status: dict[str, Any]) -> None:
            set_commands: dict[str, Callable[[str, int, Any], bytes]] = {
                'power': _set_power_cmd,
                'mute': _set_mute_cmd,
                'volume': _set_volume_cmd,
                'treble': _set_treble_cmd,
                'bass': _set_bass_cmd,
                'balance': _set_balance_cmd,
                'source': _set_source_cmd,
            }
            zone = status['zone']
            extras = get_protocol_config(amp_type, 'extras') or {}
            success = extras.get('restore_success')

            restore_commands = extras.get('restore_zone', [])
            if not restore_commands:
                LOG.info(
                    'Restore not supported: amp_type=%s, zone=%s',
                    amp_type,
                    zone,
                )
                return

            for command in restore_commands:
                if command in set_commands:
                    result = await self._protocol.send(
                        set_commands[command](amp_type, zone, status[command])
                    )
                    if result != success:
                        LOG.warning(
                            'Failed restore command: zone=%s, command=%s',
                            zone,
                            command,
                        )
                    await asyncio.sleep(0.1)

    protocol_name = get_device_config(amp_type, 'protocol')
    protocol_config = PROTOCOL_CONFIG[protocol_name]

    serial_config = get_device_config(amp_type, CONF_SERIAL_CONFIG)
    if serial_config_overrides:
        LOG.debug(
            'Overriding serial config: port=%s, overrides=%s',
            port_url,
            serial_config_overrides,
        )
        serial_config.update(serial_config_overrides)

    LOG.debug(
        'Creating async amp controller: amp_type=%s, protocol=%s, serial=%s',
        amp_type,
        protocol_name,
        serial_config,
    )
    protocol = await async_get_rs232_protocol(
        port_url, DEVICE_CONFIG[amp_type], serial_config, protocol_config, loop
    )
    return AmpControlAsync(amp_type, serial_config, protocol)
