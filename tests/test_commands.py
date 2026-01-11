"""Tests for command building functions."""

from __future__ import annotations

import pytest

from pyxantech import (
    SUPPORTED_AMP_TYPES,
    _command,
    _set_balance_cmd,
    _set_bass_cmd,
    _set_mute_cmd,
    _set_power_cmd,
    _set_source_cmd,
    _set_treble_cmd,
    _set_volume_cmd,
    _zone_status_cmd,
)


class TestSupportedAmpTypes:
    """Tests for supported amplifier types."""

    def test_known_amp_types_supported(self) -> None:
        """Verify known amplifier types are in supported list."""
        assert 'monoprice6' in SUPPORTED_AMP_TYPES
        assert 'xantech8' in SUPPORTED_AMP_TYPES


class TestMonopriceCommands:
    """Tests for Monoprice protocol command generation."""

    def test_zone_status_command(self) -> None:
        """Verify zone status query command format."""
        cmd = _zone_status_cmd('monoprice6', 11)
        assert cmd == b'?11#\r'

    def test_power_on_command(self) -> None:
        """Verify power on command format."""
        cmd = _set_power_cmd('monoprice6', 11, True)
        assert cmd == b'<11PR01#\r'

    def test_power_off_command(self) -> None:
        """Verify power off command format."""
        cmd = _set_power_cmd('monoprice6', 11, False)
        assert cmd == b'<11PR00#\r'

    def test_mute_on_command(self) -> None:
        """Verify mute on command format."""
        cmd = _set_mute_cmd('monoprice6', 11, True)
        assert cmd == b'<11MU01#\r'

    def test_mute_off_command(self) -> None:
        """Verify mute off command format."""
        cmd = _set_mute_cmd('monoprice6', 11, False)
        assert cmd == b'<11MU00#\r'

    def test_volume_command(self) -> None:
        """Verify volume command format with zero-padding."""
        cmd = _set_volume_cmd('monoprice6', 11, 5)
        assert cmd == b'<11VO05#\r'

        cmd = _set_volume_cmd('monoprice6', 11, 25)
        assert cmd == b'<11VO25#\r'

    def test_volume_clamped_to_max(self) -> None:
        """Verify volume is clamped to max value."""
        cmd = _set_volume_cmd('monoprice6', 11, 100)
        assert cmd == b'<11VO38#\r'  # max is 38

    def test_volume_clamped_to_min(self) -> None:
        """Verify negative volume is clamped to 0."""
        cmd = _set_volume_cmd('monoprice6', 11, -10)
        assert cmd == b'<11VO00#\r'

    def test_source_command(self) -> None:
        """Verify source selection command format."""
        cmd = _set_source_cmd('monoprice6', 11, 3)
        assert cmd == b'<11CH03#\r'

    def test_treble_command(self) -> None:
        """Verify treble command format."""
        cmd = _set_treble_cmd('monoprice6', 11, 7)
        assert cmd == b'<11TR07#\r'

    def test_bass_command(self) -> None:
        """Verify bass command format."""
        cmd = _set_bass_cmd('monoprice6', 11, 10)
        assert cmd == b'<11BS10#\r'

    def test_balance_command(self) -> None:
        """Verify balance command format."""
        cmd = _set_balance_cmd('monoprice6', 11, 15)
        assert cmd == b'<11BL15#\r'


class TestXantechCommands:
    """Tests for Xantech protocol command generation."""

    def test_zone_status_command(self) -> None:
        """Verify Xantech zone status query format."""
        cmd = _zone_status_cmd('xantech8', 1)
        assert cmd == b'?1ZD+'

    def test_power_on_command(self) -> None:
        """Verify Xantech power on command format."""
        cmd = _set_power_cmd('xantech8', 1, True)
        assert cmd == b'!1PR1+'

    def test_power_off_command(self) -> None:
        """Verify Xantech power off command format."""
        cmd = _set_power_cmd('xantech8', 1, False)
        assert cmd == b'!1PR0+'

    def test_volume_command(self) -> None:
        """Verify Xantech volume command format."""
        cmd = _set_volume_cmd('xantech8', 1, 20)
        assert cmd == b'!1VO20+'


class TestDax88Commands:
    """Tests for DAX88 (Dayton Audio) protocol command generation."""

    def test_zone_status_command(self) -> None:
        """Verify DAX88 zone status query format."""
        cmd = _zone_status_cmd('dax88', 11)
        assert cmd == b'?11\r'

    def test_power_on_command(self) -> None:
        """Verify DAX88 power on command format."""
        cmd = _set_power_cmd('dax88', 11, True)
        assert cmd == b'<11PR01\r'

    def test_power_off_command(self) -> None:
        """Verify DAX88 power off command format."""
        cmd = _set_power_cmd('dax88', 11, False)
        assert cmd == b'<11PR00\r'

    def test_volume_command(self) -> None:
        """Verify DAX88 volume command format."""
        cmd = _set_volume_cmd('dax88', 11, 20)
        assert cmd == b'<11VO20\r'

    def test_source_command(self) -> None:
        """Verify DAX88 source command format."""
        cmd = _set_source_cmd('dax88', 11, 4)
        assert cmd == b'<11CH04\r'

    def test_zone_18_commands(self) -> None:
        """Verify DAX88 zone 18 commands."""
        cmd = _zone_status_cmd('dax88', 18)
        assert cmd == b'?18\r'

        cmd = _set_power_cmd('dax88', 18, True)
        assert cmd == b'<18PR01\r'


class TestInvalidZoneHandling:
    """Tests for invalid zone error handling."""

    def test_invalid_zone_raises_valueerror(self) -> None:
        """Verify invalid zone numbers raise ValueError."""
        with pytest.raises(ValueError, match='Invalid zone'):
            _zone_status_cmd('monoprice6', 99)

    def test_invalid_source_raises_valueerror(self) -> None:
        """Verify invalid source numbers raise ValueError."""
        with pytest.raises(ValueError, match='Invalid source'):
            _set_source_cmd('monoprice6', 11, 99)


class TestCommandBuilder:
    """Tests for low-level command builder."""

    def test_command_with_no_args(self) -> None:
        """Verify commands with no format arguments."""
        # all_zones_off typically has no arguments
        cmd = _command('xantech8', 'all_zones_off')
        assert cmd == b'!AO+'

    def test_command_with_zone_arg(self) -> None:
        """Verify commands with zone argument."""
        cmd = _command('monoprice6', 'zone_status', {'zone': 12})
        assert b'12' in cmd
