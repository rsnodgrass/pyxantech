""" Read the configuration for supported devices """
import os
import re
import yaml
import logging

LOG = logging.getLogger(__name__)

DEVICE_CONFIG = {}
PROTOCOL_CONFIG = {}

def _load_config(config_file):
    """Load the amp series configuration"""

#    LOG.debug(f"Loading {config_file}")
    with open(config_file, 'r') as stream:
        try:
            config = yaml.load(stream, Loader=yaml.FullLoader)
            return config[0]
        except yaml.YAMLError as exc:
            LOG.error(f"Failed reading config {config_file}: {exc}")
            return None

def _load_config_dir(directory):
    config_tree = {}

    for filename in os.listdir(directory):
#        try:
          if filename.endswith('.yaml'):
                series = filename.split('.yaml')[0]
                config = _load_config(os.path.join(directory, filename))
                if config:
                    config_tree[series] = config
#        except Exception as e:
#            LOG.warning(f"Failed parsing {filename}; ignoring that configuration file: {e}")

    return config_tree

def pattern_to_dictionary(protocol_type, match, source_text: str) -> dict:
    """Convert the pattern to a dictionary, replacing 0 and 1's with True/False"""
    LOG.info(f"Pattern matching {source_text} {match}")
    d = match.groupdict()
            
    # type convert any pre-configured fields
    # TODO: this could be a lot more efficient LOL
    boolean_fields = PROTOCOL_CONFIG[protocol_type].get('boolean_fields')
    for k, v in d.items():
        if k in boolean_fields:
            # replace and 0 or 1 with True or False
            if v == '0':
                d[k] = False
            elif v == '1':
                d[k] = True
    return d

def get_with_log(name, dictionary, key: str):
    value = dictionary.get(key)
    if value:
        return dictionary.get(key)
    LOG.warning(f"Invalid key '{key}' in dictionary '{name}'; returning None")
    return None

# cached dictionary pattern matches for all responses for each protocol
def _precompile_response_patterns():
    """Precompile all response patterns"""
    precompiled = {}
    for protocol_type, config in PROTOCOL_CONFIG.items():
        patterns = {}

        LOG.debug(f"Precompile patterns for {protocol_type}")
        for name, pattern in config['responses'].items():
            #LOG.debug(f"Precompiling pattern {name}: {pattern}")
            patterns[name] = re.compile(pattern)
        precompiled[protocol_type] = patterns
    return precompiled




config_dir = os.path.dirname(__file__)
DEVICE_CONFIG = _load_config_dir(f"{config_dir}/series")
PROTOCOL_CONFIG = _load_config_dir(f"{config_dir}/protocols")

RS232_RESPONSE_PATTERNS = _precompile_response_patterns()