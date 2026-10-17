"""Tests for Sonance C4630 SE protocol support."""

from __future__ import annotations

import logging

import pytest

from pyxantech import (
    _merge_zone_status_responses,
    _set_balance_cmd,
    _set_bass_cmd,
    _set_treble_cmd,
    _set_volume_cmd,
    _zone_status_cmd,
    _zone_status_query_commands,
)


class TestSonanceCommands:
    """Tests for Sonance protocol command generation."""

    def test_zone_status_command(self) -> None:
        """Verify Sonance zone status query format."""
        assert _zone_status_cmd('sonance6', 1) == b':Z1?\r'
        assert _zone_status_cmd('sonance6', 6) == b':Z6?\r'

    def test_volume_command(self) -> None:
        """Verify volume command uses 2-digit zero-padded format."""
        assert _set_volume_cmd('sonance6', 1, 40) == b':V140\r'
        assert _set_volume_cmd('sonance6', 2, 5) == b':V205\r'
        assert _set_volume_cmd('sonance6', 3, 60) == b':V360\r'

    def test_bass_positive(self) -> None:
        """Positive bass is an explicit sign plus one digit."""
        assert _set_bass_cmd('sonance6', 1, 5) == b':L1+5\r'
        assert _set_bass_cmd('sonance6', 2, 8) == b':L2+8\r'

    def test_bass_negative(self) -> None:
        """Negative bass keeps the sign; unsigned padding would be wrong."""
        assert _set_bass_cmd('sonance6', 1, -5) == b':L1-5\r'
        assert _set_bass_cmd('sonance6', 2, -8) == b':L2-8\r'

    def test_bass_zero(self) -> None:
        """Zero bass still carries the + sign the amp echoes."""
        assert _set_bass_cmd('sonance6', 1, 0) == b':L1+0\r'

    def test_bass_clamped_to_device_range(self) -> None:
        """Bass is clamped to the sonance6 min/max of -8..+8."""
        assert _set_bass_cmd('sonance6', 1, 20) == b':L1+8\r'
        assert _set_bass_cmd('sonance6', 1, -20) == b':L1-8\r'

    def test_treble_signed(self) -> None:
        """Treble uses the same sign-plus-one-digit format as bass."""
        assert _set_treble_cmd('sonance6', 1, 7) == b':H1+7\r'
        assert _set_treble_cmd('sonance6', 1, -7) == b':H1-7\r'
        assert _set_treble_cmd('sonance6', 1, 0) == b':H1+0\r'
        assert _set_treble_cmd('sonance6', 6, 4) == b':H6+4\r'

    def test_balance_signed(self) -> None:
        """Balance is sign plus two digits; range is -10..+10."""
        assert _set_balance_cmd('sonance6', 1, 10) == b':B1+10\r'
        assert _set_balance_cmd('sonance6', 1, -10) == b':B1-10\r'
        assert _set_balance_cmd('sonance6', 1, 0) == b':B1+00\r'
        assert _set_balance_cmd('sonance6', 1, 2) == b':B1+02\r'

    def test_balance_clamped_to_device_range(self) -> None:
        """Balance outside -10..+10 is clamped before formatting."""
        assert _set_balance_cmd('sonance6', 1, 50) == b':B1+10\r'
        assert _set_balance_cmd('sonance6', 1, -50) == b':B1-10\r'

    def test_invalid_zone_raises(self) -> None:
        """Zone 0 and zone 7 are invalid for sonance6."""
        with pytest.raises(ValueError, match='Invalid zone'):
            _zone_status_cmd('sonance6', 0)
        with pytest.raises(ValueError, match='Invalid zone'):
            _zone_status_cmd('sonance6', 7)
        with pytest.raises(ValueError, match='Invalid zone'):
            _zone_status_query_commands('sonance6', 7)


class TestSonanceMultiQuery:
    """Tests for multi-query zone_status_queries support."""

    def test_returns_seven_queries(self) -> None:
        """zone_status_queries should expand to 7 command/name pairs."""
        queries = _zone_status_query_commands('sonance6', 1)
        assert queries is not None
        assert len(queries) == 7

    def test_query_names(self) -> None:
        """Verify the expected query names and order."""
        queries = _zone_status_query_commands('sonance6', 1)
        assert queries is not None
        names = [name for name, _cmd in queries]
        assert names == [
            'zone_status',
            'volume_status',
            'source_status',
            'mute_status',
            'bass_status',
            'treble_status',
            'balance_status',
        ]

    def test_query_commands_contain_zone(self) -> None:
        """Each query command should encode the correct zone number."""
        queries = _zone_status_query_commands('sonance6', 3)
        assert queries is not None
        expected = {
            'zone_status': b':Z3?\r',
            'volume_status': b':V3?\r',
            'source_status': b':S3?\r',
            'mute_status': b':M3?\r',
            'bass_status': b':L3?\r',
            'treble_status': b':H3?\r',
            'balance_status': b':B3?\r',
        }
        assert dict(queries) == expected

    def test_other_amps_stay_single_query(self) -> None:
        """zone_status_queries is Sonance-only; other series keep one snapshot."""
        assert _zone_status_query_commands('monoprice6', 11) is None
        assert _zone_status_query_commands('xantech8', 1) is None
        assert _zone_status_query_commands('dax88', 11) is None
        assert _zone_status_query_commands('dax66', 11) is None

    def test_amps_without_min_still_clamp_at_zero(self) -> None:
        """Missing min_* falls back to 0 so non-Sonance commands are unchanged."""
        assert _set_bass_cmd('monoprice6', 11, -3) == b'<11BS00#\r'
        assert _set_treble_cmd('monoprice6', 11, -1) == b'<11TR00#\r'
        assert _set_balance_cmd('monoprice6', 11, -4) == b'<11BL00#\r'
        assert _set_bass_cmd('xantech8', 1, -2) == b'!1BS00+'
        assert _set_treble_cmd('dax88', 11, -5) == b'<11TR00\r'


class TestMergeZoneStatusResponses:
    """Tests for _merge_zone_status_responses zone validation and line scanning."""

    def test_correct_zone_is_merged(self) -> None:
        """Response matching the queried zone is merged."""
        responses = [
            ('zone_status', ['+Z11']),
            ('volume_status', ['+V140']),
            ('source_status', ['+S13']),
        ]
        result = _merge_zone_status_responses('sonance6', 1, responses)
        assert result is not None
        assert result['power'] == '1'
        assert result['volume'] == '40'
        assert result['source'] == '3'

    def test_volume_zone_is_not_greedy(self) -> None:
        """+V105 is zone 1 volume 05, not zone 10 volume 5."""
        result = _merge_zone_status_responses(
            'sonance6',
            1,
            [('volume_status', ['+V105'])],
        )
        assert result is not None
        assert result['zone'] == '1'
        assert result['volume'] == '05'

        result = _merge_zone_status_responses(
            'sonance6',
            6,
            [('volume_status', ['+V660'])],
        )
        assert result is not None
        assert result['zone'] == '6'
        assert result['volume'] == '60'

    def test_wrong_zone_is_skipped(self) -> None:
        """Response for a different zone should not contaminate the merge."""
        responses = [
            ('zone_status', ['+Z21']),
            ('volume_status', ['+V140']),
        ]
        result = _merge_zone_status_responses('sonance6', 1, responses)
        assert result is not None
        assert 'power' not in result
        assert result['volume'] == '40'

    def test_correct_line_picked_from_multi_line_response(self) -> None:
        """When a broadcast and the real response arrive together, the right line wins."""
        responses = [
            ('zone_status', ['+Z21', '+Z11']),
            ('volume_status', ['+V140']),
        ]
        result = _merge_zone_status_responses('sonance6', 1, responses)
        assert result is not None
        assert result['power'] == '1'
        assert result['zone'] == '1'

    def test_all_wrong_zone_returns_none(self) -> None:
        """If every response is for the wrong zone, return None."""
        responses = [
            ('zone_status', ['+Z21']),
            ('volume_status', ['+V240']),
        ]
        result = _merge_zone_status_responses('sonance6', 1, responses)
        assert result is None

    def test_empty_lines_returns_none(self) -> None:
        """Empty line lists are skipped; all-empty returns None."""
        responses = [
            ('zone_status', []),
            ('volume_status', []),
        ]
        result = _merge_zone_status_responses('sonance6', 1, responses)
        assert result is None

    def test_signed_eq_values_parsed(self) -> None:
        """Negative EQ values in amp responses are parsed correctly."""
        responses = [
            ('zone_status', ['+Z11']),
            ('bass_status', ['+L1-5']),
            ('treble_status', ['+H1+7']),
            ('balance_status', ['+B1-3']),
        ]
        result = _merge_zone_status_responses('sonance6', 1, responses)
        assert result is not None
        assert result['bass'] == '-5'
        assert result['treble'] == '+7'
        assert result['balance'] == '-3'

    def test_partial_and_wrong_zone_are_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """Empty, wrong-zone, and partial merges are visible at debug."""
        caplog.set_level(logging.DEBUG, logger='pyxantech')
        responses = [
            ('zone_status', []),
            ('volume_status', ['+V21']),
            ('bass_status', ['+L1-8']),
        ]
        result = _merge_zone_status_responses('sonance6', 1, responses)
        assert result is not None
        assert 'power' not in result
        assert 'volume' not in result
        assert result['bass'] == '-8'
        text = caplog.text
        assert 'No response lines' in text
        assert 'wrong zone' in text
        assert 'Partial zone status' in text
        assert 'matched=1/3' in text
