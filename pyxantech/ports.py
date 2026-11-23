"""Helpers for opening serial ports through serialx.

serialx resolves the port URL itself, so every form it understands works
unchanged: ``/dev/ttyUSB0``, ``COM3``, ``socket://host:port``,
``rfc2217://host:port``, ``esphome://host:port?port_name=...`` and, inside
Home Assistant, the ``esphome-hass://`` URLs produced by its serial port
selector.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# pyserial names used by the device YAML files and by callers' overrides,
# mapped to the names serialx prefers (the old ones are deprecated aliases)
_SECRET_QUERY_KEYS = {'key', 'password', 'noise_psk'}

_LEGACY_KWARG_NAMES = {
    'bytesize': 'byte_size',
    'timeout': 'read_timeout',
    'writeTimeout': 'write_timeout',
}


def serialx_kwargs(serial_config: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``serial_config`` using serialx setting names."""
    return {
        _LEGACY_KWARG_NAMES.get(key, key): value for key, value in serial_config.items()
    }


def redact_port_url(port_url: str) -> str:
    """Hide credentials (ESPHome ``key``/``password``) before logging a URL.

    Done here rather than with ``serialx.redact_uri`` because Home Assistant
    pins serialx and older pins do not have it.
    """
    parts = urlsplit(port_url)
    if not parts.query:
        return port_url

    query = [
        (name, 'REDACTED' if name in _SECRET_QUERY_KEYS else value)
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
    ]
    return urlunsplit(parts._replace(query=urlencode(query)))
