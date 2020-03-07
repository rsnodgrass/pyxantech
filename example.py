#!/usr/local/bin/python3
#
# Running:
#   ./example-async.py --help
#   ./example.py --tty /dev/tty.usbserial-A501SGSZ

import argparse                                                                                             
import time

from pyxantech import get_amp_controller, XANTECH8, MONOPRICE6

parser = argparse.ArgumentParser(description='Xantech RS232 client example')
parser.add_argument('--tty', help='/dev/tty to use (e.g. /dev/tty.usbserial-A501SGSZ)', required=True)
parser.add_argument('--model', default=XANTECH8, help=f"model (e.g. {XANTECH8}, {MONOPRICE6})" )
parser.add_argument('--baud',type=int,default=9600,help='baud rate (9600, 14400, 19200, 38400, 57600, 115200)')
args = parser.parse_args()

config = {                          
    'rs232': {
        'baudrate': args.baud
    }
}

zone = 1
amp = get_amp_controller(args.model, args.tty, config)

# save the status for all zones before modifying
zone_status = {}
for zone in range(1, 9):
    zone_status[zone] = amp.zone_status(zone) # save current status for all zones
    print(f"Zone {zone} status: {zone_status[zone]}")

amp.all_off()

for zone in range(1, 9):
    amp.set_power(zone, True)
    amp.set_mute(zone, False)
    print(f"Zone {zone} status: {amp.zone_status(zone)}")

source = 1
amp.set_source(1, source)

# restore zones back to their original states
for zone in range(1, 9):
    amp.restore_zone( zone_status[zone ])





def knight_rider(amp, number_of_times):
    for _ in range (1, number_of_times + 1):
        for zone in range(1, 9):
            amp.set_power(zone, True)
            amp.set_power(zone, False)

        for zone in range(-7, -1):
            amp.set_power(-1 * zone, True)
            amp.set_power(-1 * zone, False)
# knight_rider(amp, 2)