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

amp.all_off()

for zone in range(1, 8):
#    amp.set_power(zone, True)
    amp.set_source(zone, 1)
    amp.set_mute(zone, False)
    print(amp.zone_status(zone).dict)

exit()

# Valid zones are 11-16 for main xantech amplifier
zone_status = amp.zone_status(zone)

# Set balance for zone #11
#amp.set_balance(zone, 3)

# Restore zone #11 to it's original state
amp.restore_zone(zone_status.dict)