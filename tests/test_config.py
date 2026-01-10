"""Tests for configuration loading and parsing."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pyxantech.config import (
    DEVICE_CONFIG,
    PROTOCOL_CONFIG,
    RS232_RESPONSE_PATTERNS,
    get_with_log,
    pattern_to_dictionary,
)


class TestConfigLoading:
    """Tests for configuration file loading."""

    def test_device_config_loaded(self) -> None:
        """Verify device configurations are loaded from YAML files."""
        assert len(DEVICE_CONFIG) > 0
        assert 'monoprice6' in DEVICE_CONFIG
        assert 'xantech8' in DEVICE_CONFIG

    def test_protocol_config_loaded(self) -> None:
        """Verify protocol configurations are loaded."""
        assert len(PROTOCOL_CONFIG) > 0
        assert 'monoprice' in PROTOCOL_CONFIG
        assert 'xantech' in PROTOCOL_CONFIG

    def test_response_patterns_precompiled(self) -> None:
        """Verify response patterns are precompiled regex objects."""
        assert len(RS232_RESPONSE_PATTERNS) > 0

        for protocol, patterns in RS232_RESPONSE_PATTERNS.items():
            for name, pattern in patterns.items():
                assert isinstance(pattern, re.Pattern), (
                    f'Pattern {name} in {protocol} should be compiled regex'
                )


class TestDeviceConfigStructure:
    """Tests for device configuration structure."""

    @pytest.mark.parametrize('amp_type', ['monoprice6', 'xantech8'])
    def test_required_device_fields(self, amp_type: str) -> None:
        """Verify required fields exist in device configs."""
        config = DEVICE_CONFIG[amp_type]

        assert 'protocol' in config
        assert 'zones' in config
        assert 'sources' in config
        assert 'rs232' in config

    def test_monoprice6_zones(self) -> None:
        """Verify Monoprice 6-zone amp has correct zone configuration."""
        config = DEVICE_CONFIG['monoprice6']
        zones = config['zones']

        # unit 1 zones
        assert 11 in zones
        assert 12 in zones
        assert 16 in zones
        # expansion unit zones
        assert 21 in zones
        assert 31 in zones

    def test_xantech8_sources(self) -> None:
        """Verify Xantech 8-zone has 8 sources configured."""
        config = DEVICE_CONFIG['xantech8']
        sources = config['sources']

        assert len(sources) == 8
        for i in range(1, 9):
            assert i in sources


class TestProtocolConfigStructure:
    """Tests for protocol configuration structure."""

    @pytest.mark.parametrize('protocol', ['monoprice', 'xantech'])
    def test_required_protocol_fields(self, protocol: str) -> None:
        """Verify required fields exist in protocol configs."""
        config = PROTOCOL_CONFIG[protocol]

        assert 'commands' in config
        assert 'responses' in config

    def test_monoprice_commands(self) -> None:
        """Verify Monoprice protocol has essential commands."""
        commands = PROTOCOL_CONFIG['monoprice']['commands']

        required_commands = [
            'zone_status',
            'power_on',
            'power_off',
            'mute_on',
            'mute_off',
            'set_volume',
            'set_source',
        ]
        for cmd in required_commands:
            assert cmd in commands, f'Missing command: {cmd}'


class TestGetWithLog:
    """Tests for get_with_log utility function."""

    def test_returns_existing_key(self) -> None:
        """Verify existing keys return their values."""
        data = {'key1': 'value1', 'key2': 42}

        assert get_with_log('test', data, 'key1') == 'value1'
        assert get_with_log('test', data, 'key2') == 42

    def test_returns_none_for_missing_key(self) -> None:
        """Verify missing keys return None."""
        data = {'key1': 'value1'}

        assert get_with_log('test', data, 'missing', log_missing=False) is None

    def test_returns_none_values(self) -> None:
        """Verify None values are returned correctly."""
        data = {'key1': None}

        assert get_with_log('test', data, 'key1', log_missing=False) is None


class TestPatternToDictionary:
    """Tests for pattern_to_dictionary function."""

    def test_converts_match_to_dict(self) -> None:
        """Verify regex match groups are converted to dictionary."""
        pattern = re.compile(r'zone=(?P<zone>\d+),power=(?P<power>\d)')
        match = pattern.search('zone=11,power=1')

        assert match is not None
        # requires boolean_fields to be configured in protocol
        result = pattern_to_dictionary('monoprice', match, 'zone=11,power=1')

        assert 'zone' in result
        assert result['zone'] == '11'
