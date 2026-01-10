"""Tests for ZoneStatus parsing and dataclass functionality."""

from __future__ import annotations

import pytest

from pyxantech import ZoneStatus


class TestZoneStatusDataclass:
    """Tests for ZoneStatus dataclass behavior."""

    def test_default_values(self) -> None:
        """Verify default field values."""
        status = ZoneStatus()

        assert status.zone == 0
        assert status.power is False
        assert status.mute is False
        assert status.volume == 0
        assert status.treble == 0
        assert status.bass == 0
        assert status.balance == 0
        assert status.source == 0
        assert status.paged is False
        assert status.linked is False
        assert status.pa is False
        assert status.do_not_disturb is False
        assert status.keypad is False

    def test_dict_property_returns_raw_data(self) -> None:
        """Verify dict property returns the raw parsed data."""
        raw = {'zone': '11', 'power': '01', 'volume': '20'}
        status = ZoneStatus.from_dict(raw)

        assert status.dict == raw

    def test_from_dict_type_conversion(self) -> None:
        """Verify boolean and integer type conversion from strings."""
        data = {
            'zone': '11',
            'power': '01',
            'mute': '1',
            'volume': '25',
            'treble': '7',
            'bass': '8',
            'balance': '10',
            'source': '3',
            'paged': '0',
            'keypad': '01',
        }
        status = ZoneStatus.from_dict(data)

        assert status.zone == 11
        assert status.power is True
        assert status.mute is True
        assert status.volume == 25
        assert status.treble == 7
        assert status.bass == 8
        assert status.balance == 10
        assert status.source == 3
        assert status.paged is False
        assert status.keypad is True

    def test_from_dict_handles_invalid_int(self) -> None:
        """Verify graceful handling of non-numeric integer fields."""
        data = {'zone': 'invalid', 'volume': 'bad'}
        status = ZoneStatus.from_dict(data)

        assert status.zone == 0
        assert status.volume == 0


class TestZoneStatusParsing:
    """Tests for ZoneStatus.from_string parsing."""

    def test_empty_string_returns_none(self) -> None:
        """Empty string should return None."""
        assert ZoneStatus.from_string('monoprice6', '') is None

    def test_none_string_returns_none(self) -> None:
        """None value should return None."""
        assert ZoneStatus.from_string('monoprice6', None) is None

    def test_invalid_format_returns_none(self) -> None:
        """Invalid format strings should return None."""
        # non-numeric zone
        assert ZoneStatus.from_string('monoprice6', '\r\n#>a100010000101112100401\r\n#') is None
        # empty response
        assert ZoneStatus.from_string('monoprice6', '\r\n#>\r\n#') is None

    def test_parse_monoprice_status(self) -> None:
        """Parse valid Monoprice zone status response.

        Format: #>zone(2)+power(2)+source(2)+mute(2)+dnd(1)+volume(2)+treble(2)+bass(2)+balance(2)+unknown(2)+keypad(2)
        Example: #>11 01 04 00 0 13 11 12 10 06 01
                    z  pw sr mu d vo tr ba bl uk kp
        """
        # zone=11, power=01(on), source=04, mute=00(off), dnd=0, vol=13, treble=11, bass=12, bal=10, unk=06, keypad=01
        response = '\r\n#>1101040001311121006011\r\n#'
        status = ZoneStatus.from_string('monoprice6', response)

        assert status is not None
        assert status.zone == 11
        assert status.power is True
        assert status.source == 4
        assert status.mute is False
        assert status.volume == 13
        assert status.treble == 11
        assert status.bass == 12
        assert status.balance == 10
        assert status.keypad is True


class TestZoneStatusMonopricePatterns:
    """Tests for specific Monoprice response patterns.

    Monoprice zone status format:
    #>zone(2)+power(2)+source(2)+mute(2)+dnd(1)+volume(2)+treble(2)+bass(2)+balance(2)+unknown(2)+keypad(2)
    Total: 23 digits after #>
    """

    @pytest.mark.parametrize(
        'response,expected_zone,expected_power,expected_volume',
        [
            # zone=11, power=01(on), src=00, mute=00, dnd=0, vol=13, tr=11, bs=12, bal=10, unk=04, kp=01
            ('\r\n#>11010000001311121004011\r\n#', 11, True, 13),
            # zone=12, power=00(off), src=00, mute=00, dnd=0, vol=20, tr=10, bs=10, bal=10, unk=02, kp=01
            ('\r\n#>12000000002010101002011\r\n#', 12, False, 20),
            # zone=16, power=01(on), src=03, mute=00, dnd=0, vol=38, tr=07, bs=07, bal=10, unk=18, kp=01
            ('\r\n#>16010300003807071018011\r\n#', 16, True, 38),
        ],
    )
    def test_parse_various_zone_responses(
        self,
        response: str,
        expected_zone: int,
        expected_power: bool,
        expected_volume: int,
    ) -> None:
        """Test parsing various valid Monoprice zone responses."""
        status = ZoneStatus.from_string('monoprice6', response)

        assert status is not None
        assert status.zone == expected_zone
        assert status.power is expected_power
        assert status.volume == expected_volume
