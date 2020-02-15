import asyncio
import functools
import logging
import re
import serial
from functools import wraps
from threading import RLock

_LOGGER = logging.getLogger(__name__)

MONOPRICE6 = 'monoprice6'   # Monoprice 6-zone amplifier
DAYTON6    = 'monoprice6'   # Dayton Audio 6-zone amplifiers are idential to Monoprice
XANTECH8   = 'xantech8'     # Xantech 8-zone amplifier
SUPPORTED_AMP_TYPES = [ MONOPRICE6, XANTECH8 ]

MAX_BALANCE = 20
MAX_BASS = 14
MAX_TREBLE = 14
MAX_VOLUME = 38

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

        'set_volume':    '<{zone}VO{level:02}',     # level: 0-38
        'set_treble':    '<{zone}TR{level:02}',     # level: 0-14
        'set_bass':      '<{zone}BS{level:02}',     # level: 0-14
        'set_balance':   '<{zone}BL{level:02}',     # level: 0-20
        'set_source':    '<{zone}CH{channel:02}'    # level: 0-6
    },

    XANTECH8: {
        'zone_status':   '?{zone}ZD+',
        'zone_details':  '?{zone}ZD+',
        'source_select': '!{zone}SS{source}+',    # source (no leading zeros)

        'set_power':     '<{zone}PR{onoff}+',
        'power_on':      '!{zone}PR1+',
        'power_off':     '!{zone}PR0+',
        'all_zones_off': '!AO+',

        'set_mute':      '!{zone}MU{on_off}+',
        'mute_on':       '!{zone}MU1+',
        'mute_off':      '!{zone}MU0+',
        'mute_toggle':   '!{zone}MT+',

        'set_volume':    '!{zone}VO{level:02}+',  # level: 0-38
        'volume_up':     '!{zone}VI+',
        'volume_down':   '!{zone}VD+',
        
        'set_bass':      '!{zone}BS{level:02}',     # level: 0-14
        'bass_up':       '!{zone}BI+',
        'bass_down':     '!{zone}BD+',

        'set_balance':   '!{zone}BL{level:02}',     # level: 0-20
        'balance_left':  '!{zone}BL+',
        'balance_right': '!{zone}BR+',

        'set_treble':    '!{zone}TR{level:02}',     # level: 0-14
        'treble_up':     '!{zone}TI+',
        'treble_down':   '!{zone}TD+',

        'disable_activity_updates': '!ZA0+',
        'disable_status_updates':   '!ZP0+',
        'power_toggle':  '!{zone}PT+',

        'current_source':  '?{zone}SS+', # RESPONSE: ?{zone}SS{source}+
        'current_volume':  '?{zone}VO+', # RESPONSE: ?{zone}VO{volume}+
        'current_mute':    '?{zone}MU+', # RESPONSE: ?{zone}MU{0/1}+
        'current_power':   '?{zone}PR+', # RESPONSE: ?{zone}PR{0/1}+
        'current_treble':  '?{zone}TR+', # RESPONSE: ?{zone}TR{level}+
        'current_bass':    '?{zone}BS+', # RESPONSE: ?{zone}BS{level}+
        'current_balance': '?{zone}BA+', # RESPONSE: ?{zone}BA{level}+

        # FIXME: these aren't documented, do they work?
        'set_activity_updates': '!ZA{on_off}+',      # on_off: 1 = on; 0 = off
        'set_status_updates':   '!ZP{on_off}+',      # on_off: 1 = on; 0 = off
    }
}

AMP_TYPE_CONFIG ={
    MONOPRICE6: {
        'protocol_eol':    b'\r\n#',
        'command_eol':     "\r",
        'zone_pattern':    re.compile('#>(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)'),
        'max_amps':        3,
        'sources':         [ 1, 2, 3, 4, 5, 6 ],
        'zones':           [ 11, 12, 13, 14, 15, 16,           # main amp 1    (e.g. 15 = amp 1, zone 5)
                             21, 22, 23, 24, 25, 26,           # linked amp 2  (e.g. 23 = amp 2, zone 3)
                             31, 32, 33, 34, 35, 36 ]          # linked amp 3
    },

    # NOTE: Xantech MRC88 seems to indicate zones are 1..8, or 1..16 if expanded; perhaps this scheme for multi-amps changed
    XANTECH8: {
        'protocol_eol':    b'\r\n#',
        'command_eol':     "\r",
        'zone_pattern':    re.compile('#>(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)'),
        'max_amps':        3,
        'sources':         [ 1, 2, 3, 4, 5, 6, 7, 8 ],
        'zones':           [ 11, 12, 13, 14, 15, 16, 17, 18,   # main amp 1    (e.g. 15 = amp 1, zone 5)
                             21, 22, 23, 24, 25, 26, 27, 28,   # linked amp 2  (e.g. 23 = amp 2, zone 3)
                             31, 32, 33, 34, 35, 36, 37, 38 ]  # linked amp 3
    }
}

TIMEOUT = 2  # serial operation timeout (seconds)

SERIAL_INIT_ARGS = {
    'baudrate':      9600,
    'stopbits':      serial.STOPBITS_ONE,
    'bytesize':      serial.EIGHTBITS,
    'parity':        serial.PARITY_NONE,
    'timeout':       TIMEOUT,
    'write_timeout': TIMEOUT
}

def _get_config(amp_type: str, key: str):
    config = AMP_TYPE_CONFIG.get(amp_type)
    if config:
        return config.get(key)
    _LOGGER.error("Invalid amp type '%s' config key '%s'; returning None", amp_type, key)
    return None

class ZoneStatus(object):
    def __init__(self,
                 zone: int,
                 pa: bool,
                 power: bool,
                 mute: bool,
                 do_not_disturb: bool,
                 volume: int,  # 0 - 38
                 treble: int,  # 0 -> -7,  14-> +7
                 bass: int,  # 0 -> -7,  14-> +7
                 balance: int,  # 00 - left, 10 - center, 20 right
                 source: int,
                 keypad: bool):
        self.zone = zone
        self.pa = bool(pa)
        self.power = bool(power)
        self.mute = bool(mute)
        self.do_not_disturb = bool(do_not_disturb)
        self.volume = volume
        self.treble = treble
        self.bass = bass
        self.balance = balance
        self.source = source
        self.keypad = bool(keypad)

    @classmethod
    def from_string(cls, amp_type, string: str):
        if not string:
            return None
        pattern = _get_config(amp_type, 'zone_pattern')
        match = re.search(pattern, string)
        if not match:
            _LOGGER.debug("Could not pattern match zone status '%s' with '%s'", string, pattern)
            return None
        return ZoneStatus(*[int(m) for m in match.groups()])


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

def _format(amp_type: str, format_code: str, args = {}):
    eol = _get_config(amp_type, 'command_eol')
    command = RS232_COMMANDS[amp_type].get(format_code) + eol
    return command.format(args).encode()

def _zone_status_request_cmd(amp_type, zone: int) -> bytes:
    assert zone in _get_config(amp_type, 'zones')
    return _format(amp_type, 'zone_status', args = { 'zone': zone })

def _set_power_cmd(amp_type, zone: int, power: bool) -> bytes:
    assert zone in _get_config(amp_type, 'zones')
    if power:
        return _format(amp_type, 'power_on')
    else:
        return _format(amp_type, 'power_off')

def _set_mute_cmd(amp_type, zone: int, mute: bool) -> bytes:
    assert zone in _get_config(amp_type, 'zones')
    if mute:
        return _format(amp_type, 'mute_on')
    else:
        return _format(amp_type, 'mute_off')
    
def _set_volume_cmd(amp_type, zone: int, volume: int) -> bytes:
    assert zone in _get_config(amp_type, 'zones')
    volume = int(max(0, min(volume, MAX_VOLUME)))
    return _format(amp_type, 'set_volume', args = { 'zone': zone, 'volume': volume })

def _set_volume_cmd(amp_type, zone: int, volume: int) -> bytes:
    assert zone in _get_config(amp_type, 'zones')
    volume = int(max(0, min(volume, MAX_VOLUME)))
    return _format(amp_type, 'set_volume', args = { 'zone': zone, 'volume': volume })

def _set_treble_cmd(amp_type, zone: int, treble: int) -> bytes:
    assert zone in _get_config(amp_type, 'zones')
    treble = int(max(0, min(treble, MAX_TREBLE)))
    return _format(amp_type, 'set_treble', args = { 'zone': zone, 'treble': treble })

def _set_bass_cmd(amp_type, zone: int, bass: int) -> bytes:
    assert zone in _get_config(amp_type, 'zones')
    bass = int(max(0, min(bass, MAX_BASS)))
    return _format(amp_type, 'set_bass', args = { 'zone': zone, 'bass': bass })

def _set_balance_cmd(amp_type, zone: int, balance: int) -> bytes:
    assert zone in _get_config(amp_type, 'zones')
    balance = max(0, min(balance, MAX_BALANCE))
    return _format(amp_type, 'set_balance', args = { 'zone': zone, 'balance': balance })

def _set_source_cmd(amp_type, zone: int, source: int) -> bytes:
    assert zone in _get_config(amp_type, 'zones')
    assert source in _get_config(amp_type, 'sources')
    return _format(amp_type, 'set_source', args = { 'zone': zone, 'source': source })

# backwards compatible API
def get_monoprice(port_url):
    """
    Return synchronous version of amplifier control interface
    :param port_url: serial port, i.e. '/dev/ttyUSB0'
    :return: synchronous implementation of amplifier control interface
    """
    return get_amp_controller(MONOPRICE6, port_url)

def get_amp_controller(amp_type: str, port_url):
    """
    Return synchronous version of amplifier control interface
    :param port_url: serial port, i.e. '/dev/ttyUSB0'
    :return: synchronous implementation of amplifier control interface
    """

    # sanity check the provided amplifier type
    if amp_type not in SUPPORTED_AMP_TYPES:
        _LOGGER.error("Unsupported amplifier type '%s'", amp_type)
        return None

    lock = RLock()

    def synchronized(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with lock:
                return func(*args, **kwargs)
        return wrapper

    class AmpControlSync(AmpControlBase):
        def __init__(self, amp_type, port_url):
            self._amp_type = amp_type
            self._port = serial.serial_for_url(port_url, do_not_open=True, **SERIAL_INIT_ARGS)
            self._port.timeout = TIMEOUT
            self._port.write_timeout = TIMEOUT
            self._port.open()

        def _process_request(self, request: bytes, skip=0):
            """
            :param request: request that is sent to the xantech
            :param skip: number of bytes to skip for end of transmission decoding
            :return: ascii string returned by xantech
            """
            _LOGGER.debug('Sending "%s"', request)

            # clear
            self._port.reset_output_buffer()
            self._port.reset_input_buffer()

            # send
            self._port.write(request)
            self._port.flush()

            eol = _get_config(self._amp_type, 'protocol_eol')
            len_eol = len(eol)

            # receive
            result = bytearray()
            while True:
                c = self._port.read(1)
                if not c:
                    raise serial.SerialTimeoutException(
                        'Connection timed out! Last received bytes {}'.format([hex(a) for a in result]))
                result += c
                if len(result) > skip and result[-len_eol:] == EOL:
                    break

            ret = bytes(result)
            _LOGGER.debug('Received "%s"', ret)
            return ret.decode('ascii')

        @synchronized
        def zone_status(self, zone: int):
            # Ignore first 6 bytes as they will contain 3 byte command and 3 bytes of EOL
            response = self._process_request(_zone_status_cmd(self._amp_type, zone), skip=6)
            return ZoneStatus.from_string(self._amp_type, response)

        @synchronized
        def set_power(self, zone: int, power: bool):
            self._process_request(_set_power_cmd(self._amp_type, zone, power))

        @synchronized
        def set_mute(self, zone: int, mute: bool):
            self._process_request(_set_mute_cmd(self._amp_type, zone, mute))

        @synchronized
        def set_volume(self, zone: int, volume: int):
            self._process_request(_set_volume_cmd(self._amp_type, zone, volume))

        @synchronized
        def set_treble(self, zone: int, treble: int):
            self._process_request(_set_treble_cmd(self._amp_type, zone, treble))

        @synchronized
        def set_bass(self, zone: int, bass: int):
            self._process_request(_set_bass_cmd(self._amp_type, zone, bass))

        @synchronized
        def set_balance(self, zone: int, balance: int):
            self._process_request(_set_balance_cmd(self._amp_type, zone, balance))

        @synchronized
        def set_source(self, zone: int, source: int):
            self._process_request(_set_source_cmd(self._amp_type, zone, source))

        @synchronized
        def restore_zone(self, status: ZoneStatus):
            self.set_power(status.zone, status.power)
            self.set_mute(status.zone, status.mute)
            self.set_volume(status.zone, status.volume)
            self.set_treble(status.zone, status.treble)
            self.set_bass(status.zone, status.bass)
            self.set_balance(status.zone, status.balance)
            self.set_source(status.zone, status.source)

    return AmpControlSync(amp_type, port_url)


# backwards compatible API
@asyncio.coroutine
def get_async_monoprice(port_url, loop):
    """
    Return asynchronous version of amplifier control interface
    :param port_url: serial port, i.e. '/dev/ttyUSB0'
    :return: asynchronous implementation of amplifier control interface
    """
    return get_async_amp_controller(MONOPRICE6, port_url, loop)

@asyncio.coroutine
def get_async_amp_controller(amp_type, port_url, loop):
    """
    Return asynchronous version of amplifier control interface
    :param port_url: serial port, i.e. '/dev/ttyUSB0'
    :return: asynchronous implementation of amplifier control interface
    """
    from serial_asyncio import create_serial_connection

    # sanity check the provided amplifier type
    if amp_type not in SUPPORTED_AMP_TYPES:
        _LOGGER.error("Unsupported amplifier type '%s'", amp_type)
        return None

    lock = asyncio.Lock()

    def locked_coro(coro):
        @asyncio.coroutine
        @wraps(coro)
        def wrapper(*args, **kwargs):
            with (yield from lock):
                return (yield from coro(*args, **kwargs))
        return wrapper

    class AmpControlAsync(AmpControlBase):
        def __init__(self, amp_type, protocol):
            self._amp_type = amp_type
            self._protocol = protocol

        @locked_coro
        @asyncio.coroutine
        def zone_status(self, zone: int):
            # Ignore first 6 bytes as they will contain 3 byte command and 3 bytes of EOL
            string = yield from self._protocol.send(_zone_status_request_cmd(self._amp_type, zone), skip=6)
            return ZoneStatus.from_string(string)

        @locked_coro
        @asyncio.coroutine
        def set_power(self, zone: int, power: bool):
            yield from self._protocol.send(_set_power_cmd(self._amp_type, zone, power))

        @locked_coro
        @asyncio.coroutine
        def set_mute(self, zone: int, mute: bool):
            yield from self._protocol.send(_set_mute_cmd(self._amp_type, zone, mute))

        @locked_coro
        @asyncio.coroutine
        def set_volume(self, zone: int, volume: int):
            yield from self._protocol.send(_set_volume_cmd(self._amp_type, zone, volume))

        @locked_coro
        @asyncio.coroutine
        def set_treble(self, zone: int, treble: int):
            yield from self._protocol.send(_set_treble_cmd(self._amp_type, zone, treble))

        @locked_coro
        @asyncio.coroutine
        def set_bass(self, zone: int, bass: int):
            yield from self._protocol.send(_set_bass_cmd(self._amp_type, zone, bass))

        @locked_coro
        @asyncio.coroutine
        def set_balance(self, zone: int, balance: int):
            yield from self._protocol.send(_set_balance_cmd(self._amp_type, zone, balance))

        @locked_coro
        @asyncio.coroutine
        def set_source(self, zone: int, source: int):
            yield from self._protocol.send(_set_source_cmd(self._amp_type, zone, source))

        @locked_coro
        @asyncio.coroutine
        def restore_zone(self, status: ZoneStatus):
            yield from self._protocol.send(_set_power_cmd(self._amp_type, status.zone, status.power))
            yield from self._protocol.send(_set_mute_cmd(self._amp_type, status.zone, status.mute))
            yield from self._protocol.send(_set_volume_cmd(self._amp_type, status.zone, status.volume))
            yield from self._protocol.send(_set_treble_cmd(self._amp_type, status.zone, status.treble))
            yield from self._protocol.send(_set_bass_cmd(self._amp_type, status.zone, status.bass))
            yield from self._protocol.send(_set_balance_cmd(self._amp_type, status.zone, status.balance))
            yield from self._protocol.send(_set_source_cmd(self._amp_type, status.zone, status.source))

    class AmpControlProtocol(asyncio.Protocol):
        def __init__(self, config, loop):
            super().__init__()
            self._config = config
            self._loop = loop
            self._lock = asyncio.Lock()
            self._transport = None
            self._connected = asyncio.Event(loop=loop)
            self.q = asyncio.Queue(loop=loop)

        def connection_made(self, transport):
            self._transport = transport
            self._connected.set()
            _LOGGER.debug('port opened %s', self._transport)

        def data_received(self, data):
            asyncio.ensure_future(self.q.put(data), loop=self._loop)

        @asyncio.coroutine
        def send(self, request: bytes, skip=0):
            yield from self._connected.wait()
            result = bytearray()

            eol = self._config.get('protocol_eol')
            len_eol = len(eol)

            # Only one transaction at a time
            with (yield from self._lock):
                self._transport.serial.reset_output_buffer()
                self._transport.serial.reset_input_buffer()
                while not self.q.empty():
                    self.q.get_nowait()
                self._transport.write(request)
                try:
                    while True:
                        result += yield from asyncio.wait_for(self.q.get(), TIMEOUT, loop=self._loop)
                        if len(result) > skip and result[-len_eol:] == eol:
                            ret = bytes(result)
                            _LOGGER.debug('Received "%s"', ret)
                            return ret.decode('ascii')
                except asyncio.TimeoutError:
                    _LOGGER.error("Timeout during receiving response for command '%s', received='%s'", request, result)
                    raise

    _, protocol = yield from create_serial_connection(loop,
                                                      functools.partial(AmpControlProtocol, AMP_TYPE_CONFIG.get(amp_type), loop),
                                                      port_url,
                                                      **SERIAL_INIT_ARGS)
    return AmpControlAsync(amp_type, protocol)
