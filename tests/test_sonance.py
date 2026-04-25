"""Tests for Sonance C4630 SE protocol support."""

from __future__ import annotations

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
        assert _set_volume_cmd('sonance6', 2, 5)  == b':V205\r'
        assert _set_volume_cmd('sonance6', 3, 60) == b':V360\r'

    def test_bass_positive(self) -> None:
        """Positive bass uses explicit + sign and 2-digit magnitude."""
        assert _set_bass_cmd('sonance6', 1, 5)  == b':L1+05\r'
        assert _set_bass_cmd('sonance6', 2, 8)  == b':L2+08\r'

    def test_bass_negative(self) -> None:
        """Negative bass uses - sign; standard zero-pad would produce wrong output."""
        assert _set_bass_cmd('sonance6', 1, -5) == b':L1-05\r'
        assert _set_bass_cmd('sonance6', 2, -8) == b':L2-08\r'

    def test_bass_zero(self) -> None:
        """Zero bass uses + sign per Sonance protocol."""
        assert _set_bass_cmd('sonance6', 1, 0)  == b':L1+00\r'

    def test_treble_signed(self) -> None:
        """Treble uses the same signed format as bass."""
        assert _set_treble_cmd('sonance6', 1,  7) == b':H1+07\r'
        assert _set_treble_cmd('sonance6', 1, -7) == b':H1-07\r'
        assert _set_treble_cmd('sonance6', 1,  0) == b':H1+00\r'

    def test_balance_signed(self) -> None:
        """Balance uses signed format; range is -10..+10."""
        assert _set_balance_cmd('sonance6', 1,  10) == b':B1+10\r'
        assert _set_balance_cmd('sonance6', 1, -10) == b':B1-10\r'
        assert _set_balance_cmd('sonance6', 1,   0) == b':B1+00\r'
        assert _set_balance_cmd('sonance6', 1,   2) == b':B1+02\r'

    def test_invalid_zone_raises(self) -> None:
        """Zone 0 and zone 7 are invalid for sonance6."""
        with pytest.raises(ValueError, match='Invalid zone'):
            _zone_status_cmd('sonance6', 0)
        with pytest.raises(ValueError, match='Invalid zone'):
            _zone_status_cmd('sonance6', 7)


class TestSonanceMultiQuery:
    """Tests for multi-query zone_status_queries support."""

    def test_returns_seven_queries(self) -> None:
        """zone_status_queries should expand to 7 command/name pairs."""
        queries = _zone_status_query_commands('sonance6', 1)
        assert queries is not None
        assert len(queries) == 7

    def test_query_names(self) -> None:
        """Verify the expected query names are present."""
        queries = _zone_status_query_commands('sonance6', 1)
        names = [name for name, _ in queries]
        assert 'zone_status'   in names
        assert 'volume_status' in names
        assert 'source_status' in names
        assert 'mute_status'   in names
        assert 'bass_status'   in names
        assert 'treble_status' in names
        assert 'balance_status' in names

    def test_query_commands_contain_zone(self) -> None:
        """Each query command should encode the correct zone number."""
        queries = _zone_status_query_commands('sonance6', 3)
        for _name, cmd in queries:
            assert b'3' in cmd


class TestMergeZoneStatusResponses:
    """Tests for _merge_zone_status_responses zone validation and line scanning."""

    def test_correct_zone_is_merged(self) -> None:
        """Response matching the queried zone is merged."""
        responses = [
            ('zone_status',   ['+Z11']),
            ('volume_status', ['+V140']),
            ('source_status', ['+S13']),
        ]
        result = _merge_zone_status_responses('sonance6', 1, responses)
        assert result is not None
        assert result['power'] == '1'
        assert result['volume'] == '40'
        assert result['source'] == '3'

    def test_wrong_zone_is_skipped(self) -> None:
        """Response for a different zone should not contaminate the merge."""
        responses = [
            ('zone_status',   ['+Z21']),   # zone 2, we want zone 1
            ('volume_status', ['+V140']),  # zone 1 — correct
        ]
        result = _merge_zone_status_responses('sonance6', 1, responses)
        # zone_status had no valid line; volume_status matched
        assert result is not None
        assert 'power' not in result
        assert result['volume'] == '40'

    def test_correct_line_picked_from_multi_line_response(self) -> None:
        """When broadcast and real response arrive together, the right line wins."""
        responses = [
            # first line is zone 2 broadcast, second is the actual zone 1 response
            ('zone_status',   ['+Z21', '+Z11']),
            ('volume_status', ['+V140']),
        ]
        result = _merge_zone_status_responses('sonance6', 1, responses)
        assert result is not None
        assert result['power'] == '1'
        assert result['zone'] == '1'

    def test_all_wrong_zone_returns_none(self) -> None:
        """If every response is for the wrong zone, return None."""
        responses = [
            ('zone_status',   ['+Z21']),
            ('volume_status', ['+V240']),
        ]
        result = _merge_zone_status_responses('sonance6', 1, responses)
        assert result is None

    def test_empty_lines_returns_none(self) -> None:
        """Empty line lists are silently skipped; all-empty → None."""
        responses = [
            ('zone_status',   []),
            ('volume_status', []),
        ]
        result = _merge_zone_status_responses('sonance6', 1, responses)
        assert result is None

    def test_signed_eq_values_parsed(self) -> None:
        """Negative EQ values in amp responses are parsed correctly."""
        responses = [
            ('zone_status',   ['+Z11']),
            ('bass_status',   ['+L1-5']),
            ('treble_status', ['+H1+7']),
            ('balance_status',['+B1-3']),
        ]
        result = _merge_zone_status_responses('sonance6', 1, responses)
        assert result is not None
        assert result['bass']    == '-5'
        assert result['treble']  == '+7'
        assert result['balance'] == '-3'
