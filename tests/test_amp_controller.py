"""Tests for amplifier controller factory functions."""

from __future__ import annotations

import pytest

from pyxantech import (
    SUPPORTED_AMP_TYPES,
    get_amp_controller,
)


class TestGetAmpController:
    """Tests for get_amp_controller factory function."""

    def test_unsupported_amp_type_returns_none(self) -> None:
        """Verify unsupported amp types return None."""
        result = get_amp_controller('invalid_type', '/dev/null')
        assert result is None

    def test_supported_amp_types_are_valid(self) -> None:
        """Verify all documented amp types are in supported list."""
        expected_types = ['monoprice6', 'xantech8', 'dax88', 'sonance6']
        for amp_type in expected_types:
            assert amp_type in SUPPORTED_AMP_TYPES, (
                f'{amp_type} should be in SUPPORTED_AMP_TYPES'
            )


class TestAmpControllerInterface:
    """Tests verifying the controller interface exists."""

    def test_controller_has_required_methods(self) -> None:
        """Verify controller interface defines expected methods.

        This tests the abstract base class interface without
        requiring actual hardware.
        """
        from pyxantech import AmpControlBase

        required_methods = [
            'zone_status',
            'set_power',
            'set_mute',
            'set_volume',
            'set_treble',
            'set_bass',
            'set_balance',
            'set_source',
            'restore_zone',
        ]

        for method in required_methods:
            assert hasattr(AmpControlBase, method), (
                f'AmpControlBase should define {method}'
            )
