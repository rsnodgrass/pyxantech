#!/usr/local/bin/python3
#
# Running:
#   ./example-async.py -h
#   ./example.py --tty /dev/tty.usbserial-A501SGSZ

import argparse                                                                                             
import time

from pyxantech import get_amp_controller, XANTECH8, MONOPRICE6

parser = argparse.ArgumentParser(description='Xantech RS232 client example')
parser.add_argument('--tty', help='/dev/tty to use (e.g. /dev/tty.usbserial-A501SGSZ)', required=True)
parser.add_argument('--model', default=XANTECH8, help=f"model (e.g. {XANTECH8, MONOPRICE6})" )
parser.add_argument('--baud',type=int,default=9600,help='baud rate (9600, 14400, 19200, 38400, 57600, 115200)')
args = parser.parse_args()

config = {                          
    'rs232': {
        'baudrate': args.baud
    }
}

zone = 1
amp = get_amp_controller(args.model, args.tty, config)

amp.all_off()

for zone in range(1, 8):
#    amp.set_power(zone, True)
    amp.set_source(zone, 1)
    amp.set_mute(zone, False)
    print(f"Zone {zone} status: {amp.zone_status(zone)}")

exit()

# Valid zones are 11-16 for main xantech amplifier
zone_status = amp.zone_status(zone)

# Set balance for zone #11
#amp.set_balance(zone, 3)

# Restore zone #11 to it's original state
amp.restore_zone(zone_status.dict)
