import asyncio
import logging
import re
import time
import serial

from functools import wraps
from threading import RLock

from .config import (DEVICE_CONFIG, PROTOCOL_CONFIG, RS232_RESPONSE_PATTERNS, get_with_log, pattern_to_dictionary)
from .protocol import async_get_rs232_protocol, CONF_RESPONSE_EOL, CONF_COMMAND_EOL, CONF_COMMAND_SEPARATOR

LOG = logging.getLogger(__name__)

MONOPRICE6 = "monoprice6" # hardcoded for backwards compatibility
BAUD_RATES = [ 9600, 14400, 19200, 38400, 57600, 115200 ]

SUPPORTED_AMP_TYPES = DEVICE_CONFIG.keys()

CONF_SERIAL_CONFIG='rs232'

def get_device_config(amp_type, key):
    return get_with_log(amp_type, DEVICE_CONFIG[amp_type], key)

def get_protocol_config(amp_type, key):
    protocol = get_device_config(amp_type, 'protocol')
    return PROTOCOL_CONFIG[protocol].get(key)

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
    def from_string(cls, amp_type: str, string: str):
        if not string:
            return None

        protocol_type = get_device_config(amp_type, 'protocol')
        pattern = RS232_RESPONSE_PATTERNS[protocol_type].get('zone_status')
        status_translation = get_protocol_config(amp_type, 'status_translation')
        match = re.search(pattern, string)
        match_dict = match.groupdict()

        if (status_translation is not None):
            for key in match_dict:
                if key in status_translation:
                    if match_dict[key] in status_translation[key]:
                        match_dict[key] = status_translation[key][match_dict[key]]


        if not match:
            LOG.debug("Could not pattern match zone status '%s' with '%s'", string, pattern)
            return None

        return ZoneStatus(match_dict)

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

def _command(amp_type: str, format_code: str, args = {}):
    cmd_eol = get_protocol_config(amp_type, CONF_COMMAND_EOL)
    cmd_separator = get_protocol_config(amp_type, CONF_COMMAND_SEPARATOR)

    rs232_commands = get_protocol_config(amp_type, 'commands')
    command = rs232_commands.get(format_code) + cmd_separator + cmd_eol

    return command.format(**args).encode('ascii')

def _zone_status_cmd(amp_type, zone: int) -> bytes:
    assert zone in get_device_config(amp_type, 'zones')
    return _command(amp_type, 'zone_status', args = { 'zone': zone })

def _set_power_cmd(amp_type, zone: int, power: bool) -> bytes:
    assert zone in get_device_config(amp_type, 'zones')
    if power:
        LOG.info(f"Powering on {amp_type} zone {zone}")
        return _command(amp_type, 'power_on', { 'zone': zone })
    else:
        LOG.info(f"Powering off {amp_type} zone {zone}")
        return _command(amp_type, 'power_off', { 'zone': zone })

def _set_mute_cmd(amp_type, zone: int, mute: bool) -> bytes:
    assert zone in get_device_config(amp_type, 'zones')
    if mute:
        LOG.info(f"Muting {amp_type} zone {zone}")
        return _command(amp_type, 'mute_on', { 'zone': zone })
    else:
        LOG.info(f"Turning off mute {amp_type} zone {zone}")
        return _command(amp_type, 'mute_off', { 'zone': zone })
    
def _set_volume_cmd(amp_type, zone: int, volume: int) -> bytes:
    assert zone in get_device_config(amp_type, 'zones')
    max_volume = get_device_config(amp_type, 'max_volume')
    volume = int(max(0, min(volume, max_volume)))
    LOG.info(f"Setting volume {amp_type} zone {zone} to {volume}")
    return _command(amp_type, 'set_volume', args = { 'zone': zone, 'volume': volume })

def _set_treble_cmd(amp_type, zone: int, treble: int) -> bytes:
    assert zone in get_device_config(amp_type, 'zones')
    max_treble = get_device_config(amp_type, 'max_treble')
    treble = int(max(0, min(treble, max_treble)))
    LOG.info(f"Setting treble {amp_type} zone {zone} to {treble}")
    return _command(amp_type, 'set_treble', args = { 'zone': zone, 'treble': treble })

def _set_bass_cmd(amp_type, zone: int, bass: int) -> bytes:
    assert zone in get_device_config(amp_type, 'zones')
    max_bass = get_device_config(amp_type, 'max_bass')
    bass = int(max(0, min(bass, max_bass)))
    LOG.info(f"Setting bass {amp_type} zone {zone} to {bass}")
    return _command(amp_type, 'set_bass', args = { 'zone': zone, 'bass': bass })

def _set_balance_cmd(amp_type, zone: int, balance: int) -> bytes:
    assert zone in get_device_config(amp_type, 'zones')
    max_balance = get_device_config(amp_type, 'max_balance')
    balance = max(0, min(balance, max_balance))
    LOG.info(f"Setting balance {amp_type} zone {zone} to {balance}")
    return _command(amp_type, 'set_balance', args = { 'zone': zone, 'balance': balance })

def _set_source_cmd(amp_type, zone: int, source: int) -> bytes:
    assert zone in get_device_config(amp_type, 'zones')
    assert source in get_device_config(amp_type, 'sources')
    LOG.info(f"Setting source {amp_type} zone {zone} to {source}")
    return _command(amp_type, 'set_source', args = { 'zone': zone, 'source': source })

def get_amp_controller(amp_type: str, port_url, serial_config_overrides={}):
    """
    Return synchronous version of amplifier control interface
    :param port_url: serial port, i.e. '/dev/ttyUSB0'
    :param serial_config_overrides: dictionary of serial port configuration overrides (e.g. baudrate)
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
        def __init__(self, amp_type, port_url, serial_config_overrides):
            self._amp_type = amp_type
            config = DEVICE_CONFIG[amp_type]

            # allow overriding the default serial port configuration, in case the user has changed
            # settings on their amplifier (e.g. increased the default baudrate)
            serial_config = get_device_config(amp_type, CONF_SERIAL_CONFIG)
            if serial_config_overrides:
                LOG.debug(f"Overiding serial port config for {port_url}: {serial_config_overrides}")
                serial_config.update(serial_config_overrides)

            self._port = serial.serial_for_url(port_url, **serial_config)

        def _send_request(self, request: bytes, skip=0):
            """
            :param request: request that is sent to the xantech
            :param skip: number of bytes to skip for end of transmission decoding
            :return: ascii string returned by xantech
            """
            # clear
            self._port.reset_output_buffer()
            self._port.reset_input_buffer()

            #print(f"Sending:  {request}")
            LOG.debug(f"Sending:  {request}")

            # send
            self._port.write(request)
            self._port.flush()

            response_eol = get_protocol_config(amp_type, CONF_RESPONSE_EOL)
            len_eol = len(response_eol)

            # receive
            result = bytearray()
            while True:
                c = self._port.read(1)
                #print(c)
                if not c:
                    ret = bytes(result)
                    LOG.info(result)
                    raise serial.SerialTimeoutException(
                        'Connection timed out! Last received bytes {}'.format([hex(a) for a in result]))
                result += c
                if len(result) > skip and result[-len_eol:] == response_eol.encode('ascii'):
                    break

            ret = bytes(result)
            LOG.debug('Received "%s"', ret)
#            print(f"Received: {ret}")
            return ret.decode('ascii')


        @synchronized
        def _zone_status_manual(self, zone: int):
            status = {}
            responses = get_protocol_config(self._amp_type, 'responses')

            # send all the commands necessary to restore the various status settings to the amp
            for command in get_protocol_config(amp_type, 'zone_status_commands'):
                pattern = responses[command]
                result = self._send_request( _zone_status_cmd(self._amp_type, command) )

                # parse the result into status dictionary
                LOG.info(f"Received zone stats {result}, matching to {pattern}")
                match = re.search(pattern, result)
                if match:
                    status.copy(match.groupdict())
                else:
                    LOG.warning("Could not pattern match zone status '%s' with '%s'", result, pattern)
                time.sleep(0.1) # pause 100 ms

            return status

        @synchronized
        def zone_status(self, zone: int):
            # if there is a list of zone status commands, execute that (some don't have a single command for status)
            #if get_protocol_config(amp_type, 'zone_status_commands'):
            #    return self._zone_status_manual(zone)

            skip = get_device_config(amp_type, 'zone_status_skip') or 0
            response = self._send_request(_zone_status_cmd(self._amp_type, zone), skip)
            status = ZoneStatus.from_string(self._amp_type, response)
            LOG.debug("Status: %s (string: %s)", status, response)
            if status:
                return status.dict
            else:
                return None

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
            success = get_protocol_config(amp_type, 'restore_success')
            #LOG.debug(f"Restoring amp {amp_type} zone {zone} from {status}")

            # FIXME: fetch current status first and only call those that changed

            # send all the commands necessary to restore the various status settings to the amp
            restore_commands = get_protocol_config(amp_type, 'restore_zone')
            for command in restore_commands:
                result = self._send_request( _command(amp_type, command, status) )
                if result != success:
                    LOG.warning(f"Failed restoring zone {zone} command {command}")
                time.sleep(0.1) # pause 100 ms

    return AmpControlSync(amp_type, port_url, serial_config_overrides)


# backwards compatible API
async def get_async_monoprice(port_url, loop):
    """
    *DEPRECATED* For backwards compatibility only.
    Return asynchronous version of amplifier control interface
    :param port_url: serial port, i.e. '/dev/ttyUSB0'
    :return: asynchronous implementation of amplifier control interface
    """
    return async_get_amp_controller(MONOPRICE6, port_url, loop)

async def async_get_amp_controller(amp_type, port_url, loop, serial_config_overrides={}):
    """
    Return asynchronous version of amplifier control interface
    :param port_url: serial port, i.e. '/dev/ttyUSB0'
    :return: asynchronous implementation of amplifier control interface
    """

    # sanity check the provided amplifier type
    if amp_type not in SUPPORTED_AMP_TYPES:
        LOG.error("Unsupported amplifier type '%s'", amp_type)
        return None

    lock = asyncio.Lock()

    def locked_coro(coro):
        @wraps(coro)
        async def wrapper(*args, **kwargs):
            async with lock:
                return (await coro(*args, **kwargs))
        return wrapper

    class AmpControlAsync(AmpControlBase):
        def __init__(self, amp_type, serial_config, protocol):
            self._amp_type = amp_type
            self._serial_config = serial_config
            self._protocol = protocol

        @locked_coro
        async def _zone_status_manual(self, zone: int):
            status = {}
            responses = get_protocol_config(amp_type, 'responses')

            # send all the commands necessary to restore the various status settings to the amp
            for command in get_protocol_config(amp_type, 'zone_status_commands'):
                pattern = responses[command]
                result = await self._protocol._send( _command(amp_type, command) )

                # parse the result into status dictionary
                LOG.info(f"Received zone stats {result}, matching to {pattern}")
                match = re.search(pattern, result)
                if match:
                    status.copy(match.groupdict())
                else:
                    LOG.warning("Could not pattern match zone status '%s' with '%s'", result, pattern)
                await asyncio.sleep(0.1) # pause 100 ms

            return status

        @locked_coro
        async def zone_status(self, zone: int):
            # FIXME: this has nothing to do with amp_type?  protocol!     
       
            # if there is a list of zone status commands, execute that (some don't have a single command for status)
            #if get_protocol_config(amp_type, 'zone_status_commands'):
            #    return await self._zone_status_manual(zone)

            cmd = _zone_status_cmd(self._amp_type, zone)
            skip = get_device_config(amp_type, 'zone_status_skip') or 0
            status_string = await self._protocol.send(cmd, skip=skip)

            status = ZoneStatus.from_string(self._amp_type, status_string)
            LOG.debug("Status: %s (string: %s)", status, status_string)
            if status:
                return status.dict
            else:
                return None

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
            await self._protocol.send(_command(self._amp_type, 'all_zones_off'))

        @locked_coro
        async def restore_zone(self, status: dict):
            zone = status['zone']
            amp_type = self._amp_type
            success = get_protocol_config(amp_type, 'restore_success')
            #LOG.debug(f"Restoring amp {amp_type} zone {zone} from {status}")

            # send all the commands necessary to restore the various status settings to the amp
            restore_commands = get_protocol_config(amp_type, 'restore_zone')
            for command in restore_commands:
                result = await self._protocol._send( _command(amp_type, command, status) )
                if result != success:
                    LOG.warning(f"Failed restoring zone {zone} command {command}")
                await asyncio.sleep(0.1) # pause 100 ms

    protocol = get_device_config(amp_type, 'protocol')
    protocol_config = PROTOCOL_CONFIG[protocol]

    # allow overriding the default serial port configuration, in case the user has changed
    # settings on their amplifier (e.g. increased the default baudrate)
    serial_config = get_device_config(amp_type, CONF_SERIAL_CONFIG)
    if serial_config_overrides:
        LOG.debug(f"Overiding serial port config for {port_url}: {serial_config_overrides}")
        serial_config.update(serial_config_overrides)


    LOG.debug(f"Loading amp {amp_type}/{protocol}: {serial_config}, {protocol_config}")
    protocol = await async_get_rs232_protocol(port_url, DEVICE_CONFIG[amp_type], serial_config, protocol_config, loop)
    return AmpControlAsync(amp_type, serial_config, protocol)
