# Python RS232 API for Xantech/Monoprice multi-zone amps

Library for RS232 serial communication to Xantech, Monoprice and Dayton Audio multi-zone amps.
This supports any serial protocol for communicating with the amps, including DB9/DB15 RS232 ports,
USB serial ports, and possibly the RS232-over-IP interface for more recent Xantech amps. See below
for exactly which amplifier models are supported.

*GOAL: To eventually merge this with pymonoprice and get rid of a separate implementation.*

The Monoprice version was originally created by Egor Tsinko for use with [Home-Assistant](http://home-assistant.io).

![beta_badge](https://img.shields.io/badge/maturity-Beta-yellow.png)
[![MIT license](http://img.shields.io/badge/license-MIT-brightgreen.svg)](http://opensource.org/licenses/MIT)

## Usage

For Monoprice and Dayton Audio 6-zone amplifiers:

```python
from pyxantech import get_amp_controller

zone = 11 # (11 = amp 1/destination 1)
amp = get_amp_controller('monoprice6', '/dev/ttyUSB0')

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
from pyxantech import get_amp_controller

zone = 12
amp = get_amp_controller('xantech8', '/dev/ttyUSB0')

amp.set_source(zone, 3) # select source 3
```

See also [example.py](example.py) for a more complete example.

## Usage with asyncio

With the `asyncio` flavor, all methods of the controller objects are coroutines:

```python
import asyncio
from pyxantech import async_get_amp_controller

async def main(loop):
    amp = await async)get_amp_controller('monoprice6', '/dev/ttyUSB0', loop)
    zone_status = await amp.zone_status(11)
    if zone_status.power:
        await amp.set_power(zone_status.zone, False)

loop = asyncio.get_event_loop()
loop.run_until_complete(main(loop))
```

## Supported Multi-Zone Amps

| Manufacturer | Model(s)                 | Zones | Supported  | Series     | Notes |
| ------------ | ------------------------ |:-----:|:----------:|:----------:| ----- |
| Xantech      | MRAUDIO8X8 / MRAUDIO8X8m | 6+2   | YES        | xantech8   | audio only; zones 7-8 are preamp outputs only |
|              | MX88a / MX88ai           | **8** | YES        | xantech8   | audio only; ai = Ethernet support (MRIP) |
|              | MRC88 / MRC88m           | 6+2   | YES        | xantech8   | audio + video; zones 7-8 are preamp outputs only |
|              | MX88 / MX88vi            | **8** | YES        | xantech8   | audio + video; vi = Ethernet support (MRIP) |
|              | MRAUDIO4X4 / BXAUDIO4x4  | 4     | *NO*       | xantech4   | audio only; uses [ZPR68 protocol which needs to be edited](pyxantech/protocols/zpr68.yaml) |
|              | MRC44 / MRC44CTL         | 4     | *NO*       | xantech4   | audio + video; uses [ZPR68 protocol which needs to be edited](pyxantech/protocols/zpr68.yaml) |
|              | CM8X8 / CM8X8DR          | 8     | *UNTESTED* | xantech8   |  commercial rack mount matrix controller (BNC) |
|              | ZPR68-10                 | 6     | *UNTESTED* | zpr68-10   | 6-zone output; 8 source inputs | 
| Monoprice    | MPR-SG6Z / 10761         | 6     | *UNTESTED* | monoprice6 | audio only |
| Dayton Audio | DAX66                    | 6     | *UNTESTED* | monoprice6 | audio only |

* The [Monoprice MPR-SG6Z](https://www.monoprice.com/product?p_id=10761) and
  [Dayton Audio DAX66](https://www.parts-express.com/dayton-audio-dax66-6-source-6-room-distributed-whole-house-audio-system-with-keypads-25-wpc--300-585)
  appear to have licensed or copied the serial interface from Xantech. Both Monoprice
  and Dayton Audio use a version of the Xantech multi-zone controller protocol.

* Some Xantech MX88 models use DB15 outputs on the rear, requiring a DB15 to DB9 adapter cable (PN 05913665), with the pinouts documented in some Xantech manuals. These Xantech models have a DB9 RS232 port on the front which can also be used.

## See Also

* [Home Assistant integration](https://www.home-assistant.io/integrations/monoprice/)
* [Monoprice RS232 serial protocol manual](doc/Monoprice-RS232-Manual.pdf)
* [Monoprice RS232 serial protocol control](doc/Monoprice-RS232-Control.pdf)

#### Community Engagement

Sites with active community engagement around the Xantech, Monoprice, and Daytona AUdio
multi-zone amplifiers:

* [AVS Forum: Monoprice 6](https://www.avsforum.com/forum/36-home-v-distribution/1506842-any-experience-monoprice-6-zone-home-audio-multizone-controller-23.html)
* http://cocoontech.com/forums/topic/25893-monoprice-multi-zone-audio/
* [Home Assistant: Monoprice 6](https://community.home-assistant.io/t/monoprice-whole-home-audio-controller-10761-success/19734/67)
