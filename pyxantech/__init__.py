import asyncio
import functools
import logging
import re
import serial
from functools import wraps
from serial_asyncio import create_serial_connection
from threading import RLock

_LOGGER = logging.getLogger(__name__)

TIMEOUT = 2  # Number of seconds before serial operation timeout

# Monoprice 6-zone amplifier
MONOPRICE6 = 'monoprice6'
MONOPRICE_ZONES = [ 11, 12, 13, 14, 15, 16,   # main amp
                    21, 22, 23, 24, 25, 26,   # linked amp 2
                    31, 32, 33, 34, 35, 36 ]  # linked amp 3

# Xantech 8-zone amplifier
XANTECH8 = 'xantech8'
XANTECH8_ZONES= [ 11, 12, 13, 14, 15, 16, 17, 18,   # main amp
                  21, 22, 23, 24, 25, 26, 27, 28,   # linked amp 2
                  31, 32, 33, 34, 35, 36, 37, 38 ]  # linked amp 3

ZONE_PATTERN = re.compile('#>(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)')
EOL = b'\r\n#'
LEN_EOL = len(EOL)

MAX_BALANCE = 20
MAX_BASS = 14
MAX_TREBLE = 14
MAX_VOLUME = 38

BAUD_RATE = 9600

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
    def from_string(cls, string: str):
        if not string:
            return None
        match = re.search(ZONE_PATTERN, string)
        if not match:
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
        Restores zone to it's previous state
        :param status: zone state to restore
        """
        raise NotImplemented()

FORMATS = {
    MONOPRICE6: {
        'zone_status':   '?{}',
        'power_on':      '<{}PR01',
        'power_off':     '<{}PR00',
        'mute_on':       '<{}MU01',
        'mute_off':      '<{}MU00',
        'set_volume':    '<{}VO{:02}',     # zone / 0-38
        'set_treble':    '<{}TR{:02}',     # zone / 0-14
        'set_bass':      '<{}BS{:02}',     # zone / 0-14
        'set_balance':   '<{}BL{:02}',     # zone / 0-20
        'set_source':    '<{}CH{:02}'      # zone / 0-6
    },

    XANTECH8: {
        'zone_details':  '?{}ZD+',       # zone details
        'power_on':      '!{}PR1+',
        'power_off':     '!{}PR0+',
        'all_zones_off': '!A0+',
        'mute_on':       '!{}MU1+',
        'mute_off':      '!{}MU0+',
        'volume_up':     '!{}VI+',
        'volume_down':   '!{}VD+',
        'set_volume':    '!{}VO{:02}+',  # zone / level 0-38
        'source_select': '!{}SS{}+',     # zone / source (no leading zeros)
        'balance_left':  '!{}BL+',
        'balance_right': '!{}BR+',
        'bass_up':       '!{}BI+',
        'bass_down':     '!{}BD+',
        'balance_left':  '!{}BL+',
        'balance_right': '!{}BR+',
        'treble_up':     '!{}TI+',
        'treble_down':   '!{}TD+',
        'disable_activity_updates': '!ZA0+',
        'disable_status_updates':   '!ZP0+',

        # FIXME: these aren't documented, do they work?
        'set_treble':    '!{}TR{:02}',     # zone / 0-14
        'set_bass':      '!{}BS{:02}',     # zone / 0-14
        'set_balance':   '!{}BL{:02}'      # zone / 0-20
    }
}

CONFIG ={
    MONOPRICE6: {
        'protocol_eol':    b'\r\n#',
        'command_eol':     b'\r',
        'zone_pattern':    re.compile('#>(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)'),
        'max_zones':       6,
        'max_linked_amps': 3,
        'zones':           MONOPRICE_ZONES
    },
    XANTECH8: {
        'protocol_eol':    b'\r\n#',
        'command_eol':     b'\r',
        'zone_pattern':    re.compile('#>(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)'),
        'max_zones':       8,
        'max_linked_amps': 3,
        'zones':           XANTECH8_ZONES
    }
}

def _format(amp_type: str, format_code: str):
    return FORMATS[amp_type].get(format_code) + CONFIG[amp_type].get('command_eol')

def _format_zone_status_request(amp_type, zone: int) -> bytes:
    return _format(amp_type, 'zone_status').format(zone).encode()

def _format_set_power(amp_type, zone: int, power: bool) -> bytes:
    if power:
        return _format(amp_type, 'power_on').encode()
    else:
        return _format(amp_type, 'power_off').encode()

def _format_set_mute(amp_type, zone: int, mute: bool) -> bytes:
    if mute:
        return _format(amp_type, 'mute_on').encode()
    else:
        return _format(amp_type, 'mute_off').encode()
    
def _format_set_volume(amp_type, zone: int, volume: int) -> bytes:
    volume = int(max(0, min(volume, MAX_VOLUME)))
    return _format(amp_type, 'set_volume').format(zone, volume).encode()

def _format_set_treble(amp_type, zone: int, treble: int) -> bytes:
    treble = int(max(0, min(treble, MAX_TREBLE)))
    return _format(amp_type, 'set_treble').format(zone, treble).encode()

def _format_set_bass(amp_type, zone: int, bass: int) -> bytes:
    bass = int(max(0, min(bass, MAX_BASS)))
    return _format(amp_type, 'set_bass').format(zone, bass).encode()

def _format_set_balance(amp_type, zone: int, balance: int) -> bytes:
    balance = max(0, min(balance, MAX_BALANCE))
    return _format(amp_type, 'set_balance').format(zone, balance).encode()

def _format_set_source(amp_type, zone: int, source: int) -> bytes:
    source = int(max(1, min(source, CONFIG[amp_type].get('max_source'))))
    return _format(amp_type, 'set_source').format(zone, source).encode()

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
    if amp_type not in FORMATS:
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
            self._port = serial.serial_for_url(port_url, do_not_open=True)
            self._port.baudrate = BAUD_RATE
            self._port.stopbits = serial.STOPBITS_ONE
            self._port.bytesize = serial.EIGHTBITS
            self._port.parity = serial.PARITY_NONE
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
            # receive
            result = bytearray()
            while True:
                c = self._port.read(1)
                if not c:
                    raise serial.SerialTimeoutException(
                        'Connection timed out! Last received bytes {}'.format([hex(a) for a in result]))
                result += c
                if len(result) > skip and result[-LEN_EOL:] == EOL:
                    break
            ret = bytes(result)
            _LOGGER.debug('Received "%s"', ret)
            return ret.decode('ascii')

        @synchronized
        def zone_status(self, zone: int):
            # Ignore first 6 bytes as they will contain 3 byte command and 3 bytes of EOL
            return ZoneStatus.from_string(self._process_request(_format_zone_status_request(zone), skip=6))

        @synchronized
        def set_power(self, zone: int, power: bool):
            self._process_request(_format_set_power(self._amp_type, zone, power))

        @synchronized
        def set_mute(self, zone: int, mute: bool):
            self._process_request(_format_set_mute(self._amp_type, zone, mute))

        @synchronized
        def set_volume(self, zone: int, volume: int):
            self._process_request(_format_set_volume(self._amp_type, zone, volume))

        @synchronized
        def set_treble(self, zone: int, treble: int):
            self._process_request(_format_set_treble(self._amp_type, zone, treble))

        @synchronized
        def set_bass(self, zone: int, bass: int):
            self._process_request(_format_set_bass(self._amp_type, zone, bass))

        @synchronized
        def set_balance(self, zone: int, balance: int):
            self._process_request(_format_set_balance(self._amp_type, zone, balance))

        @synchronized
        def set_source(self, zone: int, source: int):
            self._process_request(_format_set_source(self._amp_type, zone, source))

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

    # sanity check the provided amplifier type
    if amp_type not in FORMATS:
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
        def __init__(self, amp_type, xantech_protocol):
            self._amp_type = amp_type
            self._protocol = xantech_protocol

        @locked_coro
        @asyncio.coroutine
        def zone_status(self, zone: int):
            # Ignore first 6 bytes as they will contain 3 byte command and 3 bytes of EOL
            string = yield from self._protocol.send(_format_zone_status_request(self._amp_type, zone), skip=6)
            return ZoneStatus.from_string(string)

        @locked_coro
        @asyncio.coroutine
        def set_power(self, zone: int, power: bool):
            yield from self._protocol.send(_format_set_power(self._amp_type,zone, power))

        @locked_coro
        @asyncio.coroutine
        def set_mute(self, zone: int, mute: bool):
            yield from self._protocol.send(_format_set_mute(self._amp_type,zone, mute))

        @locked_coro
        @asyncio.coroutine
        def set_volume(self, zone: int, volume: int):
            yield from self._protocol.send(_format_set_volume(self._amp_type,zone, volume))

        @locked_coro
        @asyncio.coroutine
        def set_treble(self, zone: int, treble: int):
            yield from self._protocol.send(_format_set_treble(self._amp_type,zone, treble))

        @locked_coro
        @asyncio.coroutine
        def set_bass(self, zone: int, bass: int):
            yield from self._protocol.send(_format_set_bass(self._amp_type,zone, bass))

        @locked_coro
        @asyncio.coroutine
        def set_balance(self, zone: int, balance: int):
            yield from self._protocol.send(_format_set_balance(self._amp_type,zone, balance))

        @locked_coro
        @asyncio.coroutine
        def set_source(self, zone: int, source: int):
            yield from self._protocol.send(_format_set_source(self._amp_type,zone, source))

        @locked_coro
        @asyncio.coroutine
        def restore_zone(self, status: ZoneStatus):
            yield from self._protocol.send(_format_set_power(self._amp_type,status.zone, status.power))
            yield from self._protocol.send(_format_set_mute(self._amp_type,status.zone, status.mute))
            yield from self._protocol.send(_format_set_volume(self._amp_type,status.zone, status.volume))
            yield from self._protocol.send(_format_set_treble(self._amp_type,status.zone, status.treble))
            yield from self._protocol.send(_format_set_bass(self._amp_type,status.zone, status.bass))
            yield from self._protocol.send(_format_set_balance(self._amp_type,status.zone, status.balance))
            yield from self._protocol.send(_format_set_source(self._amp_type,status.zone, status.source))

    class AmpControlProtocol(asyncio.Protocol):
        def __init__(self, loop):
            super().__init__()
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
                        if len(result) > skip and result[-LEN_EOL:] == EOL:
                            ret = bytes(result)
                            _LOGGER.debug('Received "%s"', ret)
                            return ret.decode('ascii')
                except asyncio.TimeoutError:
                    _LOGGER.error("Timeout during receiving response for command '%s', received='%s'", request, result)
                    raise

    _, protocol = yield from create_serial_connection(loop, functools.partial(AmpControlProtocol, loop),
                                                      port_url, baudrate=BAUD_RATE)
    return AmpControlAsync(amp_type, protocol)
