"""Tests for serial port URL handling (serialx backend)."""

from __future__ import annotations

import asyncio
import socket
import threading

import pytest

from pyxantech import async_get_amp_controller, get_amp_controller
from pyxantech.ports import redact_port_url, serialx_kwargs


class TestSerialxKwargs:
    """Legacy pyserial setting names are translated to serialx names."""

    def test_legacy_names_are_translated(self) -> None:
        result = serialx_kwargs(
            {
                'baudrate': 9600,
                'bytesize': 8,
                'parity': 'N',
                'stopbits': 1,
                'timeout': 1.0,
                'write_timeout': 2.0,
            }
        )
        assert result == {
            'baudrate': 9600,
            'byte_size': 8,
            'parity': 'N',
            'stopbits': 1,
            'read_timeout': 1.0,
            'write_timeout': 2.0,
        }

    def test_modern_names_pass_through(self) -> None:
        config = {'baudrate': 19200, 'byte_size': 7, 'read_timeout': 0.5}
        assert serialx_kwargs(config) == config

    def test_input_is_not_mutated(self) -> None:
        config = {'bytesize': 8}
        serialx_kwargs(config)
        assert config == {'bytesize': 8}


class TestRedactPortUrl:
    """Credentials in ESPHome URLs must never reach the logs."""

    def test_esphome_key_is_redacted(self) -> None:
        url = 'esphome://10.0.0.5:6053/?port_name=RS-232+Port+1&key=SECRET'
        assert 'SECRET' not in redact_port_url(url)

    @pytest.mark.parametrize('url', ['/dev/ttyUSB0', 'socket://host:4999/'])
    def test_plain_urls_unchanged(self, url: str) -> None:
        assert redact_port_url(url) == url


# monoprice6 zone 11: power on, source 3, volume 20
ZONE_REPLY = b'#>110103000200707100001\r'


def _serve_once(reply: bytes) -> tuple[int, threading.Thread]:
    """Tiny TCP server: answer the first request with ``reply``."""
    server = socket.socket()
    server.bind(('127.0.0.1', 0))
    server.listen(1)

    def run() -> None:
        conn, _ = server.accept()
        with conn, server:
            conn.recv(64)
            conn.sendall(reply)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return server.getsockname()[1], thread


def test_sync_controller_talks_over_socket_url() -> None:
    port, thread = _serve_once(ZONE_REPLY)
    amp = get_amp_controller('monoprice6', f'socket://127.0.0.1:{port}/')
    assert amp is not None
    status = amp.zone_status(11)
    thread.join(timeout=2)
    assert status is not None
    assert status['volume'] == 20


async def test_async_controller_talks_over_socket_url() -> None:
    port, thread = _serve_once(ZONE_REPLY)
    amp = await async_get_amp_controller(
        'monoprice6', f'socket://127.0.0.1:{port}/', asyncio.get_running_loop()
    )
    assert amp is not None
    status = await amp.zone_status(11)
    thread.join(timeout=2)
    assert status is not None
    assert status['volume'] == 20


def test_unknown_scheme_raises_oserror_or_serial_exception() -> None:
    import serialx

    with pytest.raises((OSError, serialx.SerialException)):
        get_amp_controller('monoprice6', 'bogus://nowhere')
