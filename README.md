# Python RS232 API for Monoprice/Xantech/Dayton Audio multi-zone amps

Library for communicating via RS232 serial to Monoprice, Xantech and Dayton Audio multi-zone amps.
This supports any serial protocol for communicating with the amps, including DB9/DB15 RS232 ports,
USB serial ports, and possibly the RS232-over-IP interface for more recent Xantech amps. See below
for exactly which amplifier models are supported.

This was originally created by Egor Tsinko for use with [Home-Assistant](http://home-assistant.io).

## Status

[![Build Status](https://travis-ci.org/etsinko/pyxantech.svg?branch=master)](https://travis-ci.org/etsinko/pyxantech)[![Coverage Status](https://coveralls.io/repos/github/etsinko/pyxantech/badge.svg)](https://coveralls.io/github/etsinko/pyxantech)

## Usage

For Monoprice and Dayton Audio 6-zone amplifiers:

```python
from pyxantech import get_amp_controller, MONOPRICE6

zone = 11 # (11 = amp 1/destination 1)
amp = get_amp_controller(MONOPRICE6, '/dev/ttyUSB0')

# Turn off zone 
amp.set_power(zone, False)

# Mute zone
amp.set_mute(zone, True)

# Set volume for zone
amp.set_volume(zone, 15)

# Set source 1 for zone
amp.set_source(zone, 1)
```

For Xantech 8-zone amplifiers:

```python
from pyxantech import get_amp_controller, XANTECH8

zone = 12
amp = get_amp_controller(XANTECH8, '/dev/ttyUSB0')
amp.set_source(zone, 3) # select source 3
```

See also [example.py](example.py) for a more complete example.

## Usage with asyncio

With the `asyncio` flavor, all methods of the controller objects are coroutines:

```python
import asyncio
from pyxantech import get_async_amp_controller, MONOPRICE6

async def main(loop):
    amp = await get_async_amp_controller(MONOPRICE6, '/dev/ttyUSB0', loop)
    zone_status = await amp.zone_status(11)
    if zone_status.power:
        await amp.set_power(zone_status.zone, False)

loop = asyncio.get_event_loop()
loop.run_until_complete(main(loop))
```

## Supported Multi-Zone Amps

| Manufacturer | Model(s)                 | Zones | Supported | Notes |
| ------------ | ------------------------ |:-----:|:---------:| ----- |
| Monoprice    | MPR-SG6Z / 10761         | 6     | YES       | audio only; mid-fi version of Xantech |
| Dayton Audio | DAX66                    | 6     | YES       | audio only; mid-fi version of Xantech |
| Xantech      | MRAUDIO8X8 / MRAUDIO8X8m | 6+2   | YES       | audio only; zones 7-8 are preamp outputs only |
|              | MX88a / MX88ai           | **8** | YES       | audio only; ai = Ethernet support (MRIP) |
|              | MRC88 / MRC88m           | 6+2   | YES       | audio + video; zones 7-8 are preamp outputs only |
|              | MX88 / MX88vi            | **8** | YES       | audio + video; vi = Ethernet support (MRIP) |
|              | MRAUDIO4X4 / BXAUDIO4x4  | 4     | *NO*      | audio only; 4-zone uses different protocol |
|              | MRC44 / MRC44CTL         | 4     | *NO*      | audio + video; 4-zone uses different protocol |
|              | CM8X8 / CM8X8DR          | 8     | *MAYBE*   | commercial rack mount matrix controller (BNC) |

* The [Monoprice MPR-SG6Z](https://www.monoprice.com/product?p_id=10761) and
  [Dayton Audio DAX66](https://www.parts-express.com/dayton-audio-dax66-6-source-6-room-distributed-whole-house-audio-system-with-keypads-25-wpc--300-585)
  appear to have licensed or copies the serial interface from Xantech. Both Monoprice
  and Dayton Audio use a version of the Xantech multi-zone controller protocol.

* Some Xantech MX88 models use DB15 outputs on the rear, requiring a DB15 to DB9 adapter cable (PN 05913665). The pinouts of 05913665 are not currently documented ([possibly DB15-DB9 modem cable](https://www.aggsoft.com/rs232-pinout-cable/modem-db9-to-db15.htm)). These Xantech models have a DB9 RS232 port on the front which can also be used.

## See Also

* [Home Assistant integration](https://www.home-assistant.io/integrations/monoprice/)
* [Monoprice RS232 serial protocol manual](doc/Monoprice-RS232-Manual.pdf)
* [Monoprice RS232 serial protocol control](doc/Monoprice-RS232-Control.pdf)

#### Community Engagement

Sites with active community engagement around the Xantech, Monoprice, and Daytona AUdio
multi-zone amplifiers:

* (https://www.avsforum.com/forum/36-home-v-distribution/1506842-any-experience-monoprice-6-zone-home-audio-multizone-controller-23.html)
* (http://cocoontech.com/forums/topic/25893-monoprice-multi-zone-audio/)
* (https://community.home-assistant.io/t/monoprice-whole-home-audio-controller-10761-success/19734/67)
