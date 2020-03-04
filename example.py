#!/usr/local/bin/python3

import argparse                                                                                             
import time

from pymonoprice import get_amp_controller, XANTECH8

parser = argparse.ArgumentParser(description='Anthem RS232 client example')
parser.add_argument('--tty', help='/dev/tty to use (e.g. /dev/tty.usbserial-A501SGSZ)', required=True)
parser.add_argument('--baud',type=int,default=9600,help='baud rate (9600, 14400, 19200, 38400, 57600, 115200)')
args = parser.parse_args()

config = {                          
    'rs232': {
        'baudrate': args.baud
    }
}

zone = 1
amp = get_amp_controller(XANTECH8, args.tty, config)

#amp.all_off()
#amp.set_source(zone, 1)

#time.sleep(1)

#amp.set_power(zone, True)
#amp.set_mute(zone, True)

for zone in range(1, 8):
    print(amp.zone_status(zone).dict)

exit()

# Valid zones are 11-16 for main xantech amplifier
zone_status = amp.zone_status(11)

# Print zone status
print('Zone Number = {}'.format(zone_status.zone))
print('Power is {}'.format('On' if zone_status.power else 'Off'))
print('Mute is {}'.format('On' if zone_status.mute else 'Off'))
print('Public Anouncement Mode is {}'.format('On' if zone_status.pa else 'Off'))
print('Do Not Disturb Mode is {}'.format('On' if zone_status.do_not_disturb else 'Off'))
print('Volume = {}'.format(zone_status.volume))
print('Treble = {}'.format(zone_status.treble))
print('Bass = {}'.format(zone_status.bass))
print('Balance = {}'.format(zone_status.balance))
print('Source = {}'.format(zone_status.source))
print('Keypad is {}'.format('connected' if zone_status.keypad else 'disconnected'))

# Turn off zone #11
amp.set_power(11, False)

# Mute zone #12
amp.set_mute(12, True)

# Set volume for zone #13
amp.set_volume(13, 15)

# Set source 1 for zone #14 
amp.set_source(14, 1)

# Set treble for zone #15
amp.set_treble(15, 10)

# Set bass for zone #16
amp.set_bass(16, 7)

# Set balance for zone #11
amp.set_balance(11, 3)

# Restore zone #11 to it's original state
amp.restore_zone(zone_status)
