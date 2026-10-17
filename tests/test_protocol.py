"""Tests for multi-line serial reads.

DAX66 status selection stays on ``send`` / ``_select_status_line``.
Sonance multi-query uses the bounded drain in ``_read_response``.
"""

from __future__ import annotations

import asyncio

from pyxantech.protocol import (
    _MAX_QUEUED_DRAIN,
    RS232ControlProtocol,
    _select_status_line,
)


def test_select_status_line_prefers_dax_prefix() -> None:
    """Echo and a trailing fragment must not hide a #>/#? status line."""
    assert _select_status_line(['echo', '#?>1101', '#']) == '#?>1101'
    assert _select_status_line(['#>11', 'trail']) == '#>11'
    assert _select_status_line(['#?>first', '#>second']) == '#>second'
    assert _select_status_line(['only']) == 'only'
    assert _select_status_line([]) == ''


def _protocol(eol: str) -> RS232ControlProtocol:
    return RS232ControlProtocol(
        'dummy',
        {'timeout': 0.2},
        {},
        {'response_eol': eol},
        asyncio.get_running_loop(),
    )


async def test_one_buffer_keeps_dax_status_without_draining() -> None:
    """Lines that arrive in the same chunk are scanned for a status prefix."""
    protocol = _protocol('\n')
    protocol._queue.put_nowait(b'echo\n#?>11010101010101010101\n#\n')

    lines = await protocol._read_response(0, drain_queued=False)

    assert lines[0] == 'echo'
    assert _select_status_line(lines).startswith('#?')
    assert _select_status_line(lines) != 'echo'
    assert _select_status_line(lines) != '#'


async def test_later_chunk_is_left_for_the_single_line_reader() -> None:
    """``send`` does not pull a following packet into this reply."""
    protocol = _protocol('\n')
    protocol._queue.put_nowait(b'echo\n')
    protocol._queue.put_nowait(b'#?>11010101010101010101\n')

    lines = await protocol._read_response(0, drain_queued=False)

    assert lines == ['echo']
    assert _select_status_line(lines) == 'echo'
    assert protocol._queue.qsize() == 1


async def test_send_lines_drains_a_bounded_number_of_queued_chunks() -> None:
    """Multi-query reads fold in already-queued lines, then stop."""
    protocol = _protocol('\r')
    total = _MAX_QUEUED_DRAIN + 4
    for index in range(total):
        protocol._queue.put_nowait(f'+Z1{index % 2}\r'.encode('ascii'))

    lines = await protocol._read_response(0, drain_queued=True)

    assert len(lines) == 1 + _MAX_QUEUED_DRAIN
    assert protocol._queue.qsize() == total - len(lines)
    assert lines[0] == '+Z10'
    assert '+Z11' in lines


async def test_data_received_still_queues_for_the_reader() -> None:
    """Incoming bytes still land on the queue for the response reader."""
    protocol = _protocol('\r')
    protocol.data_received(b'+Z11\r')
    await asyncio.sleep(0)

    lines = await protocol._read_response(0, drain_queued=False)
    assert lines == ['+Z11']
