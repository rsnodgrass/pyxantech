import asyncio
import functools
import logging
import re
import time
import serial

from functools import wraps
from threading import RLock

from .protocol import get_rs232_async_protocol

LOG = logging.getLogger(__name__)

MONOPRICE6 = 'monoprice6'   # Monoprice 6-zone amplifier
DAYTON6    = 'monoprice6'   # Dayton Audio 6-zone amplifiers are idential to Monoprice
XANTECH8   = 'xantech8'     # Xantech 8-zone amplifier
ZPR68      = 'zpr68'        # Xantech ZPR68 (*NOT IMPLEMENTED*)
SUPPORTED_AMP_TYPES = [ MONOPRICE6, XANTECH8 ]

# NOTE: these ranges are different for each amp type
MAX_BALANCE = 20
MAX_BASS = 14
MAX_TREBLE = 14
MAX_VOLUME = 38

DEFAULT_SERIAL_CONFIG = {
    'baudrate':      9600,
    'bytesize':      serial.EIGHTBITS,
    'parity':        serial.PARITY_NONE,
    'stopbits':      serial.STOPBITS_ONE,
    'timeout':       2.0,
    'write_timeout': 2.0
}

# technically zone = {amp_number}{zone_num_within_amp_1-6} (e.g. 11 = amp number 1, zone 1)
RS232_COMMANDS = {
    MONOPRICE6: {
        'zone_status':   '?{zone}',

        'set_power':     '<{zone}PR{on_off:02}',    # on_off: 1 = on; 0 = off
        'power_on':      '<{zone}PR01',
        'power_off':     '<{zone}PR00',

        'set_mute':      '<{zone}MU{on_off:02}',
        'mute_on':       '<{zone}MU01',
        'mute_off':      '<{zone}MU00',

        'set_volume':    '<{zone}VO{volume:02}',   # volume: 0-38
        'set_treble':    '<{zone}TR{treble}:02}',  # treble: 0-14
        'set_bass':      '<{zone}BS{bass:02}',     # bass: 0-14
        'set_balance':   '<{zone}BL{balance:02}',  # balance: 0-20
        'set_source':    '<{zone}CH{source:02}'    # source: 0-6
    },

    XANTECH8: {
        'set_power':     "!{zone}PR{power}+",
        'power_on':      "!{zone}PR1+",
        'power_off':     "!{zone}PR0+",
        'all_zones_off': '!AO+',

        'set_mute':      '!{zone}MU{mute}+',
        'mute_on':       '!{zone}MU1+',
        'mute_off':      '!{zone}MU0+',
        'mute_toggle':   '!{zone}MT+',

        'set_volume':    '!{zone}VO{volume:02}+',    # volume: 0-38
        'volume_up':     '!{zone}VI+',
        'volume_down':   '!{zone}VD+',

        'set_source':    '!{zone}SS{source}+',      # source (no leading zeros)

        'set_bass':      '!{zone}BS{bass:02}+',     # bass: 0-14
        'bass_up':       '!{zone}BI+',
        'bass_down':     '!{zone}BD+',

        'set_balance':   '!{zone}BL{balance:02}+',     # balance: 0-20
        'balance_left':  '!{zone}BL+',
        'balance_right': '!{zone}BR+',

        'set_treble':    '!{zone}TR{treble:02}+',     # treble: 0-14
        'treble_up':     '!{zone}TI+',
        'treble_down':   '!{zone}TD+',

        'disable_activity_updates': '!ZA0+',
        'disable_status_updates':   '!ZP0+',
        'power_toggle':  '!{zone}PT+',

        # queries
        'zone_status':    '?{zone}ZD+',
        'zone_details':   '?{zone}ZD+',
        'source_status':  '?{zone}SS+',
        'volume_status':  '?{zone}VO+',
        'mute_status':    '?{zone}MU+',
        'power_status':   '?{zone}PR+',
        'treble_status':  '?{zone}TR+',
        'bass_status':    '?{zone}BS+',
        'balance_status': '?{zone}BA+',

        # FIXME: these aren't documented, do they work?
        'set_activity_updates': '!ZA{activity_updates}+',      # on_off: 1 = on; 0 = off
        'set_status_updates':   '!ZP{status_updates}+',      # on_off: 1 = on; 0 = off
    },

    ZPR68: {
        'power_status':     '?{zone:02}C=', # Y or N
        'power_on':         '!{zone:02}:CY+', 
        'power_off':        '!{zone:02}:CN+',
        'all_zones_off':    '!00CN+',

        'volume_status':    '?{zone:02}V=',
        'set_volume':       '!{zone:02}V{volume:02}+',
        'volume_up':        '!{zone:02}LU+',
        'volume_down':      '!{zone:02}LD+',

        'mute_status':      '?{zone:02}M=', # Y or N
        'mute_on':          '!{zone:02}QY+',
        'mute_off':         '!{zone:02}QN+',
        'mute_all_on':      '!00QY+',
        'mute_all_off':     '!00QN+',

        'source_status':    '?{zone:02}I=',
        'set_source':       '!{zone:02}I{source}+',
        'set_source_all':   '!00I{source}+',

        'zone_status':      'Z{zone:02}',

        'set_treble':       '!{zone:02}T{treble:02}+',

        'treble_status':    '?{zone:02}T=',
        'bass_status':      '?{zone:02}B=',
    }
}

RS232_RESPONSES = {
    MONOPRICE6: {
        'zone_status':    "#>(?P<zone>\d\d)(?P<power>[01]{2})(?P<source>[01]{2})(?P<mute[01]{2})(?P<do_not_disturb[01])(?P<volume>\d\d)(?P<treble>\d\d)(?P<bass>\d\d)(?P<balance>\d\d)(?P<source>\d\d)(?P<keypad>\d\d)",
    },

    XANTECH8: {
        'zone_status':    "#(?P<zone>\d+)ZS PR(?P<power>[01]) SS(?P<source>\d+) VO(?P<volume>\d+) MU(?P<mute>[01]) TR(?P<treble>\d+) BS(?P<bass>\d+) BA(?P<balance>\d+) LS(?P<linked>[01]) PS(?P<paged>[01])\+",
                          # Example:  #1ZS PR0 SS1 VO0 MU1 TR7 BS7 BA32 LS0 PS0+
        'power_status':   "\?(?P<zone>\d+)PR(?P<power[01])\+",
        'source_status':  "\?(?P<zone>\d+)SS(?P<source>[1-8])\+",
        'volume_status':  "\?(?P<zone>\d+)VO(?P<volume>\d+)\+",
        'mute_status':    "\?(?P<zone>\d+)MU(?P<mute>[01])\+",
        'treble_status':  "\?(?P<zone>\d+)TR(?P<treble>\d+)\+",
        'bass_status':    "\?(?P<zone>\d+)BS(?P<bass>\d+)\+",
        'balance_status': "\?(?P<zone>\d+)BA(?P<balance>\d+)\+",
    }
}

AMP_TYPE_CONFIG ={
    MONOPRICE6: {
        'rs232':           DEFAULT_SERIAL_CONFIG,
        'protocol_eol':    b'\r\n#',
        'command_eol':     "\r",
        'max_amps':        3,
        'sources':         [ 1, 2, 3, 4, 5, 6 ],
        'zones':           [ 11, 12, 13, 14, 15, 16,           # main amp 1    (e.g. 15 = amp 1, zone 5)
                             21, 22, 23, 24, 25, 26,           # linked amp 2  (e.g. 23 = amp 2, zone 3)
                             31, 32, 33, 34, 35, 36 ],         # linked amp 3
        'restore_zone':    [ 'set_power', 'set_source', 'set_volume', 'set_mute', 'set_bass', 'set_balance', 'set_treble' ],
        'restore_success': "OK\r"
    },

    # NOTE: Xantech MRC88 seems to indicate zones are 1..8, or 1..16 if expanded; perhaps this scheme for multi-amps changed
    XANTECH8: {
        'rs232':           DEFAULT_SERIAL_CONFIG,
        'protocol_eol':    b'\r', # replies: \r
        'command_eol':     '', # sending: '+'
        'max_amps':        3,
        'sources':         [ 1, 2, 3, 4, 5, 6, 7, 8 ],
        'zones':           [ 1, 2, 3, 4, 5, 6, 7, 8,
                             11, 12, 13, 14, 15, 16, 17, 18,   # main amp 1    (e.g. 15 = amp 1, zone 5)
                             21, 22, 23, 24, 25, 26, 27, 28,   # linked amp 2  (e.g. 23 = amp 2, zone 3)
                             31, 32, 33, 34, 35, 36, 37, 38 ],  # linked amp 3
        'restore_zone':    [ 'set_power', 'set_source', 'set_volume', 'set_mute', 'set_bass', 'set_balance', 'set_treble' ],
        'restore_success': "OK\r"
    },

    ZPR68: {
        'rs232':           DEFAULT_SERIAL_CONFIG,
        'protocol_eol':    b'\r', # replies: \r
        'command_eol':     '', # sending: '='
    }
}

def _get_config(amp_type: str, key: str):
    config = AMP_TYPE_CONFIG.get(amp_type)
    if config:
        return config.get(key)
    LOG.error("Invalid amp type '%s' config key '%s'; returning None", amp_type, key)
    return None

# FIXME: populate based on dictionary, not positional
class ZoneStatus(object):
    def __init__(self, status: dict):
#       volume   # 0 - 38
#       treble   # 0 -> -7,  14-> +7
#       bass     # 0 -> -7,  14-> +7
#       balance  # 0 - left, 10 - center, 20 right
        self.dict = status
        self.retype_bools(['power', 'mute', 'paged', 'linked', 'pa'])
        self.retype_ints(['zone', 'volume', 'treble', 'bass', 'balance', 'source'])

    def retype_bools(self, keys):
        for key in keys:
            if key in self.dict:
                self.dict[key] = ((self.dict[key] == '1') or (self.dict[key] == '01'))

    def retype_ints(self, keys):
        for key in keys:
            if key in self.dict:
                self.dict[key] = int(self.dict[key])


    @classmethod
    def from_string(cls, amp_type, string: str):
        if not string:
            return None

        pattern = RS232_RESPONSES[amp_type].get('zone_status')
        match = re.search(pattern, string)
        if not match:
            LOG.debug("Could not pattern match zone status '%s' with '%s'", string, pattern)
            return None

        return ZoneStatus(match.groupdict())

# FIXME: for Xantech the zones can be 11..18, 21..28, 31..38; perhaps split this as;
#   zone_status(self, zone: int, amp_num: int = 1)  with default amp_num
class AmpControlBase(object):
    """
    AmpliferControlBase amplifier interface
    """

    def zone_status(self, zone: int):
        """
        Get the structure representing the status of the zone
        :param zone: zone 11..16, 21..26, 31..36
        :return: status of the zone or None
        """
        raise NotImplemented()

    def set_power(self, zone: int, power: bool):
        """
        Turn zone on or off
        :param zone: zone 11..16, 21..26, 31..36
        :param power: True to turn on, False to turn off
        """
        raise NotImplemented()

    def set_mute(self, zone: int, mute: bool):
        """
        Mute zone on or off
        :param zone: zone 11..16, 21..26, 31..36
        :param mute: True to mute, False to unmute
        """
        raise NotImplemented()

    def set_volume(self, zone: int, volume: int):
        """
        Set volume for zone
        :param zone: zone 11..16, 21..26, 31..36
        :param volume: integer from 0 to 38 inclusive
        """
        raise NotImplemented()

    def set_treble(self, zone: int, treble: int):
        """
        Set treble for zone
        :param zone: zone 11..16, 21..26, 31..36
        :param treble: integer from 0 to 14 inclusive, where 0 is -7 treble and 14 is +7
        """
        raise NotImplemented()

    def set_bass(self, zone: int, bass: int):
        """
        Set bass for zone
        :param zone: zone 11..16, 21..26, 31..36
        :param bass: integer from 0 to 14 inclusive, where 0 is -7 bass and 14 is +7
        """
        raise NotImplemented()

    def set_balance(self, zone: int, balance: int):
        """
        Set balance for zone
        :param zone: zone 11..16, 21..26, 31..36
        :param balance: integer from 0 to 20 inclusive, where 0 is -10(left), 0 is center and 20 is +10 (right)
        """
        raise NotImplemented()

    def set_source(self, zone: int, source: int):
        """
        Set source for zone
        :param zone: zone 11..16, 21..26, 31..36
        :param source: integer from 0 to 6 inclusive
        """
        raise NotImplemented()

    def restore_zone(self, status: ZoneStatus):
        """
        Restores zone to its previous state
        :param status: zone state to restore
        """
        raise NotImplemented()
    

def _pattern_to_dictionary(pattern: str, text: str) -> dict:
    result = pattern.match(text)
    if not result:
        LOG.error(f"Could not parse '{text}' with pattern '{pattern}'")
        return None

    d = result.groupdict()

    # FIXME: for safety, we may want to limit which keys this applies to
    # replace and 0 or 1 with True or False
    boolean_keys = [ 'power', 'mute', 'pa' ]
    for k, v in d.items():
        if k in boolean_keys:
            if v == '0':
                d[k] = False
            elif v == '1':
                d[k] = True

    return d


def _command(amp_type: str, format_code: str, args = {}):
    eol = _get_config(amp_type, 'command_eol')
    command = RS232_COMMANDS[amp_type].get(format_code) + eol
    return command.format(**args).encode('ascii')

def _zone_status_cmd(amp_type, zone: int) -> bytes:
    assert zone in _get_config(amp_type, 'zones')
    return _command(amp_type, 'zone_status', args = { 'zone': zone })

def _set_power_cmd(amp_type, zone: int, power: bool) -> bytes:
    assert zone in _get_config(amp_type, 'zones')
    if power:
        LOG.info("Powering on {amp_type} zone {zone}")
        return _command(amp_type, 'power_on', { 'zone': zone })
    else:
        LOG.info("Powering off {amp_type} zone {zone}")
        return _command(amp_type, 'power_off', { 'zone': zone })

def _set_mute_cmd(amp_type, zone: int, mute: bool) -> bytes:
    assert zone in _get_config(amp_type, 'zones')
    if mute:
        LOG.info("Muting {amp_type} zone {zone}")
        return _command(amp_type, 'mute_on', { 'zone': zone })
    else:
        LOG.info("Turning off mute {amp_type} zone {zone}")
        return _command(amp_type, 'mute_off', { 'zone': zone })
    
def _set_volume_cmd(amp_type, zone: int, volume: int) -> bytes:
    assert zone in _get_config(amp_type, 'zones')
    volume = int(max(0, min(volume, MAX_VOLUME)))
    LOG.info("Setting volume {amp_type} zone {zone} to {volume}")
    return _command(amp_type, 'set_volume', args = { 'zone': zone, 'volume': volume })

def _set_treble_cmd(amp_type, zone: int, treble: int) -> bytes:
    assert zone in _get_config(amp_type, 'zones')
    treble = int(max(0, min(treble, MAX_TREBLE)))
    LOG.info("Setting treble {amp_type} zone {zone} to {treble}")
    return _command(amp_type, 'set_treble', args = { 'zone': zone, 'treble': treble })

def _set_bass_cmd(amp_type, zone: int, bass: int) -> bytes:
    assert zone in _get_config(amp_type, 'zones')
    bass = int(max(0, min(bass, MAX_BASS)))
    LOG.info("Setting bass {amp_type} zone {zone} to {bass}")
    return _command(amp_type, 'set_bass', args = { 'zone': zone, 'bass': bass })

def _set_balance_cmd(amp_type, zone: int, balance: int) -> bytes:
    assert zone in _get_config(amp_type, 'zones')
    balance = max(0, min(balance, MAX_BALANCE))
    LOG.info("Setting balance {amp_type} zone {zone} to {balance}")
    return _command(amp_type, 'set_balance', args = { 'zone': zone, 'balance': balance })

def _set_source_cmd(amp_type, zone: int, source: int) -> bytes:
    assert zone in _get_config(amp_type, 'zones')
    assert source in _get_config(amp_type, 'sources')
    LOG.info("Setting source {amp_type} zone {zone} to {source}")
    return _command(amp_type, 'set_source', args = { 'zone': zone, 'source': source })

def get_amp_controller(amp_type: str, port_url, config):
    """
    Return synchronous version of amplifier control interface
    :param port_url: serial port, i.e. '/dev/ttyUSB0'
    :return: synchronous implementation of amplifier control interface
    """

    # sanity check the provided amplifier type
    if amp_type not in SUPPORTED_AMP_TYPES:
        LOG.error("Unsupported amplifier type '%s'", amp_type)
        return None

    lock = RLock()

    def synchronized(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with lock:
                return func(*args, **kwargs)
        return wrapper


    class AmpControlSync(AmpControlBase):
        def __init__(self, amp_type, port_url, config):
            self._amp_type = amp_type
            self._config = config

            serial_init_config = DEFAULT_SERIAL_CONFIG
            serial_init_config.update(config.get("rs232"))
            print(serial_init_config)

            self._port = serial.serial_for_url(port_url, **serial_init_config)

        def _send_request(self, request: bytes, skip=0):
            """
            :param request: request that is sent to the xantech
            :param skip: number of bytes to skip for end of transmission decoding
            :return: ascii string returned by xantech
            """
            # clear
            self._port.reset_output_buffer()
            self._port.reset_input_buffer()

            print(f"Sending:  {request}")
            LOG.debug(f"Sending:  {request}")

            # send
            self._port.write(request)
            self._port.flush()

            eol = _get_config(self._amp_type, 'protocol_eol')
            len_eol = len(eol)

            # receive
            result = bytearray()
            while True:
                c = self._port.read(1)
                print(c)
                if not c:
                    ret = bytes(result)
                    LOG.info(result)
                    raise serial.SerialTimeoutException(
                        'Connection timed out! Last received bytes {}'.format([hex(a) for a in result]))
                result += c
                if len(result) > skip and result[-len_eol:] == eol:
                    break

            ret = bytes(result)
            LOG.debug('Received "%s"', ret)
            print(f"Received: {ret}")
            return ret.decode('ascii')

        @synchronized
        def zone_status(self, zone: int):
            response = self._send_request(_zone_status_cmd(self._amp_type, zone))
            return ZoneStatus.from_string(self._amp_type, response).dict

        @synchronized
        def set_power(self, zone: int, power: bool):
            self._send_request(_set_power_cmd(self._amp_type, zone, power))

        @synchronized
        def set_mute(self, zone: int, mute: bool):
            self._send_request(_set_mute_cmd(self._amp_type, zone, mute))

        @synchronized
        def set_volume(self, zone: int, volume: int):
            self._send_request(_set_volume_cmd(self._amp_type, zone, volume))

        @synchronized
        def set_treble(self, zone: int, treble: int):
            self._send_request(_set_treble_cmd(self._amp_type, zone, treble))

        @synchronized
        def set_bass(self, zone: int, bass: int):
            self._send_request(_set_bass_cmd(self._amp_type, zone, bass))

        @synchronized
        def set_balance(self, zone: int, balance: int):
            self._send_request(_set_balance_cmd(self._amp_type, zone, balance))

        @synchronized
        def set_source(self, zone: int, source: int):
            self._send_request(_set_source_cmd(self._amp_type, zone, source))

        @synchronized
        def all_off(self):
            self._send_request( _command(amp_type, 'all_zones_off') )

        @synchronized
        def restore_zone(self, status: dict):
            zone = status['zone']
            amp_type = self._amp_type
            success = AMP_TYPE_CONFIG[amp_type].get('restore_success')
            #LOG.debug(f"Restoring amp {amp_type} zone {zone} from {status}")

            # FIXME: fetch current status first and only call those that changed

            # send all the commands necessary to restore the various status settings to the amp
            restore_commands = AMP_TYPE_CONFIG[amp_type].get('restore_zone')
            for command in restore_commands:
                result = self._send_request( _command(amp_type, command, status) )
                if result != success:
                    LOG.warning(f"Failed restoring zone {zone} command {command}")
                time.sleep(0.1) # pause 100 ms

    return AmpControlSync(amp_type, port_url, config)


# backwards compatible API
async def get_async_monoprice(port_url, loop):
    """
    *DEPRECATED* For backwards compatibility only.
    Return asynchronous version of amplifier control interface
    :param port_url: serial port, i.e. '/dev/ttyUSB0'
    :return: asynchronous implementation of amplifier control interface
    """
    return get_async_amp_controller(MONOPRICE6, port_url, DEFAULT_SERIAL_CONFIG, loop)

async def get_async_amp_controller(amp_type, port_url, config_override, loop):
    """
    Return asynchronous version of amplifier control interface
    :param port_url: serial port, i.e. '/dev/ttyUSB0'
    :return: asynchronous implementation of amplifier control interface
    """

    # sanity check the provided amplifier type
    if amp_type not in SUPPORTED_AMP_TYPES:
        LOG.error("Unsupported amplifier type '%s'", amp_type)
        return None

    config = AMP_TYPE_CONFIG[amp_type]
    config.update(config_override)

    protocol_type = config.get('protocol')

    lock = asyncio.Lock()

    def locked_coro(coro):
        @wraps(coro)
        async def wrapper(*args, **kwargs):
            with (await lock):
                return (await coro(*args, **kwargs))
        return wrapper

    class AmpControlAsync(AmpControlBase):
        def __init__(self, amp_type, protocol):
            self._amp_type = amp_type
            self._protocol = protocol

        @locked_coro
        async def zone_status(self, zone: int):
            # Ignore first 6 bytes as they will contain 3 byte command and 3 bytes of EOL
            string = await self._protocol.send(_zone_status_cmd(self._amp_type, zone))
            return ZoneStatus.from_string(string).dict

        @locked_coro
        async def set_power(self, zone: int, power: bool):
            await self._protocol.send(_set_power_cmd(self._amp_type, zone, power))

        @locked_coro
        async def set_mute(self, zone: int, mute: bool):
            await self._protocol.send(_set_mute_cmd(self._amp_type, zone, mute))

        @locked_coro
        async def set_volume(self, zone: int, volume: int):
            await self._protocol.send(_set_volume_cmd(self._amp_type, zone, volume))

        @locked_coro
        async def set_treble(self, zone: int, treble: int):
            await self._protocol.send(_set_treble_cmd(self._amp_type, zone, treble))

        @locked_coro
        async def set_bass(self, zone: int, bass: int):
            await self._protocol.send(_set_bass_cmd(self._amp_type, zone, bass))

        @locked_coro
        async def set_balance(self, zone: int, balance: int):
            await self._protocol.send(_set_balance_cmd(self._amp_type, zone, balance))

        @locked_coro
        async def set_source(self, zone: int, source: int):
            await self._protocol.send(_set_source_cmd(self._amp_type, zone, source))

        @locked_coro
        async def all_off(self):
            await self._protocol.send(_command(amp_type, 'all_zones_off'))

        @locked_coro
        async def restore_zone(self, status: dict):
            zone = status['zone']
            amp_type = self._amp_type
            success = AMP_TYPE_CONFIG[amp_type].get('restore_success')
            #LOG.debug(f"Restoring amp {amp_type} zone {zone} from {status}")

            # send all the commands necessary to restore the various status settings to the amp
            restore_commands = AMP_TYPE_CONFIG[amp_type].get('restore_zone')
            for command in restore_commands:
                result = await self._protocol._send( _command(amp_type, command, status) )
                if result != success:
                    LOG.warning(f"Failed restoring zone {zone} command {command}")
                await asyncio.sleep(0.1) # pause 100 ms

    protocol = await get_rs232_async_protocol(port_url, config.get('rs232'), config, loop)
    return AmpControlAsync(protocol_type, protocol)
