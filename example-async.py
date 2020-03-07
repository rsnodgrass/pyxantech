#! /usr/local/bin/python3
#
# Running:
#   ./example-async.py --tty /dev/tty.usbserial-A501SGSZ

import time
import asyncio
import argparse
import serial

from pyxantech import get_async_amp_controller, XANTECH8, MONOPRICE6

parser = argparse.ArgumentParser(description='Xantech RS232 client example (asynchronous)')
parser.add_argument('--tty', help='/dev/tty to use (e.g. /dev/tty.usbserial-A501SGSZ)', required=True)
parser.add_argument('--model', default=XANTECH8, help=f"model (e.g. {XANTECH8, MONOPRICE6})" )
parser.add_argument('--baud', type=int, default=9600, help='baud rate (9600, 14400, 19200, 38400, 57600, 115200)')
args = parser.parse_args()

config = {                          
    'rs232': {
        'baudrate': args.baud
    }
}

async def main():
    zone = 1

    amp = await get_async_amp_controller(XANTECH8, args.tty, config, asyncio.get_event_loop())
    amp.all_off()

#    print(f"Xantech amp version = {await amp.sendCommand('version')}")

    for zone in range(1, 8):
        
        await asyncio.sleep(0.5)
        await amp.set_power(zone, True)
        
        await asyncio.sleep(0.5)
        await amp.set_source(zone, 1)
        await amp.set_mute(zone, False)
        
        print(f"Zone {zone} status: {amp.zone_status(zone)}")

    exit()

    # Valid zones are 11-16 for main xantech amplifier
    # zone_status = await amp.zone_status(zone)

    # Set balance for zone #11
    #amp.set_balance(zone, 3)

    # Restore zone #11 to it's original state
    # amp.restore_zone(zone_status.dict)

    
asyncio.run(main())

