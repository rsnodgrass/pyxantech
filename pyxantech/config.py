"""Configuration loader for supported multi-zone amplifier devices.

This module handles loading YAML configuration files that define:
- Device series specifications (zones, sources, RS232 settings)
- Protocol definitions (commands, responses, patterns)
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

LOG = logging.getLogger(__name__)

# global configuration dictionaries populated at module load
DEVICE_CONFIG: dict[str, dict[str, Any]] = {}
PROTOCOL_CONFIG: dict[str, dict[str, Any]] = {}
RS232_RESPONSE_PATTERNS: dict[str, dict[str, re.Pattern[str]]] = {}


def _load_config(config_file: Path) -> dict[str, Any] | None:
    """Load a single YAML configuration file.

    Args:
        config_file: Path to the YAML configuration file.

    Returns:
        Parsed configuration dictionary or None if loading failed.
    """
    try:
        with config_file.open(encoding='utf-8') as stream:
            config = yaml.safe_load(stream)
            if config and isinstance(config, list) and len(config) > 0:
                return config[0]  # type: ignore[no-any-return]
            return None
    except yaml.YAMLError:
        LOG.exception('Failed reading config file: path=%s', config_file)
        return None


def _load_config_dir(directory: Path) -> dict[str, dict[str, Any]]:
    """Load all YAML configuration files from a directory.

    Args:
        directory: Path to directory containing YAML files.

    Returns:
        Dictionary mapping config names to their parsed contents.
    """
    config_tree: dict[str, dict[str, Any]] = {}

    if not directory.is_dir():
        LOG.warning('Config directory does not exist: path=%s', directory)
        return config_tree

    for file_path in directory.glob('*.yaml'):
        series = file_path.stem
        config = _load_config(file_path)
        if config:
            config_tree[series] = config

    return config_tree


def pattern_to_dictionary(
    protocol_type: str,
    match: re.Match[str],
    source_text: str,
) -> dict[str, str | bool]:
    """Convert regex match to dictionary with boolean type conversion.

    Args:
        protocol_type: Protocol identifier for looking up boolean fields.
        match: Regex match object containing named groups.
        source_text: Original text that was matched (for logging).

    Returns:
        Dictionary with match group values, with boolean fields converted.
    """
    LOG.debug('Pattern matching: source=%s, match=%s', source_text, match)
    result: dict[str, str | bool] = dict(match.groupdict())

    boolean_fields = PROTOCOL_CONFIG.get(protocol_type, {}).get('boolean_fields', [])
    for key, value in result.items():
        if key in boolean_fields and isinstance(value, str):
            result[key] = value == '1'

    return result


def get_with_log(
    name: str,
    dictionary: dict[str, Any],
    key: str,
    *,
    log_missing: bool = True,
) -> Any:
    """Get value from dictionary with optional missing key warning.

    Args:
        name: Identifier for the dictionary (for logging).
        dictionary: Dictionary to retrieve value from.
        key: Key to look up.
        log_missing: Whether to log a warning if key is missing.

    Returns:
        Value from dictionary or None if not found.
    """
    value = dictionary.get(key)
    if value is None and log_missing:
        LOG.warning("Missing key '%s' in dictionary '%s'", key, name)
    return value


def _precompile_response_patterns() -> dict[str, dict[str, re.Pattern[str]]]:
    """Precompile all response regex patterns for efficiency.

    Returns:
        Nested dictionary mapping protocol types to pattern name to compiled regex.
    """
    precompiled: dict[str, dict[str, re.Pattern[str]]] = {}

    for protocol_type, config in PROTOCOL_CONFIG.items():
        patterns: dict[str, re.Pattern[str]] = {}
        responses = config.get('responses', {})

        LOG.debug('Precompiling patterns for protocol: %s', protocol_type)
        for name, pattern in responses.items():
            if isinstance(pattern, str):
                patterns[name] = re.compile(pattern)

        precompiled[protocol_type] = patterns

    return precompiled


def _initialize_config() -> None:
    """Initialize global configuration by loading all config files."""
    global DEVICE_CONFIG, PROTOCOL_CONFIG, RS232_RESPONSE_PATTERNS

    config_dir = Path(__file__).parent
    DEVICE_CONFIG = _load_config_dir(config_dir / 'series')
    PROTOCOL_CONFIG = _load_config_dir(config_dir / 'protocols')
    RS232_RESPONSE_PATTERNS = _precompile_response_patterns()


# initialize configuration on module import
_initialize_config()
