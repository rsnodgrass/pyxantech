# Python RS232 API for Multi-Zone Amps

Library for RS232 serial communication to Xantech, Monoprice, Dayton Audio, Soundavo, and other multi-zone amps.
This supports any serial protocol for communicating with the amps, including RS232 ports,
USB serial ports, and possibly the RS232-over-IP interface for more recent Xantech amps. See below
for exactly which amplifier models are supported.

*GOAL: To eventually merge this with pymonoprice and get rid of a separate implementation.*

The Monoprice version was originally created by Egor Tsinko for use with [Home-Assistant](http://home-assistant.io).

![beta_badge](https://img.shields.io/badge/maturity-Beta-yellow.png)
[![PyPi](https://img.shields.io/pypi/v/pyxantech.svg)](https://pypi.python.org/pypi/pyxantech)
[![MIT license](http://img.shields.io/badge/license-MIT-brightgreen.svg)](http://opensource.org/licenses/MIT)
[![Build Status](https://github.com/rsnodgrass/pyxantech/actions/workflows/ci.yml/badge.svg)](https://github.com/rsnodgrass/pyxantech/actions/workflows/ci.yml)

## Support

Visit the [community support discussion thread](https://community.home-assistant.io/t/xantech-dayton-audio-sonance-multi-zone-amps/450908) for issues with this library.

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

For Xantech 8-zone amplifiers the following exmaple. In this case pyxantech is used to connect to an RS232 device exposed over the network (e.g. [IP2SL](https://github.com/rsnodgrass/virtual-ip2sl)):

```python
from pyxantech import get_amp_controller

zone = 12
amp = get_amp_controller('xantech8', 'socket://remote-host:4999/')

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

| Manufacturer | Model(s)                 | Zones | Supported  |   Series   | Notes                                            |
| ------------ | ------------------------ | :---: | :--------: | :--------: | ------------------------------------------------ |
| Xantech      | MRAUDIO8X8 / MRAUDIO8X8m |  6+2  |    YES     |  xantech8  | audio only; zones 7-8 are preamp outputs only    |
|              | MX88a / MX88ai           | **8** |    YES     |  xantech8  | audio only; ai = Ethernet support (MRIP)         |
|              | MRC88 / MRC88m           |  6+2  |    YES     |  xantech8  | audio + video; zones 7-8 are preamp outputs only |
|              | MX88 / MX88vi            | **8** |    YES     |  xantech8  | audio + video; vi = Ethernet support (MRIP)      |
|              | CM8X8 / CM8X8DR          |   8   | *UNTESTED* |  xantech8  | commercial rack mount matrix controller (BNC)    |
|              | ZPR68-10                 |   6   | *UNTESTED* |  zpr68-10  | 6-zone output; 8 source inputs                   |
|              | MRAUDIO4X4 / BXAUDIO4x4  |   4   |    *NO*    |    N/A     | audio only; only supports IR control             |
|              | MRC44 / MRC44CTL         |   4   |    *NO*    |    N/A     | audio + video; only supprots IR control          |
| Monoprice    | MPR-SG6Z / 10761         |   6   | *UNTESTED* | monoprice6 | audio only                                       |
| Dayton Audio | DAX66                    |   6   | *UNTESTED* | monoprice6 | audio only                                       |
|              | DAX88                    |  6+2  |    YES     |    dax88   | audio only                                       |
| Sonance      | C4630 SE (6-zone) / 875D MKII (4-zone) |  4-6   | *UNTESTED* | sonance6   | audio only                        |
| Soundavo     | WS66i                    |   6   | *UNTESTED* | monoprice6 | audio only; see [pyws66i](https://github.com/ssaenger/pyws66i); does not support telnet/IP control (yet) |

* The [Monoprice MPR-SG6Z](https://www.monoprice.com/product?p_id=10761) and
  [Dayton Audio DAX66](https://www.parts-express.com/dayton-audio-dax66-6-source-6-room-distributed-whole-house-audio-system-with-keypads-25-wpc--300-585)
  appear to have licensed or copied the serial interface from Xantech. Both Monoprice
  and Dayton Audio use a version of the Xantech multi-zone controller protocol.
* Soundavo WS66i is an updated version of the Monoprice 10761 which includes 2 wireless streamers, IP/telnet-based control, etc. It has not been tested with this, but should use the monoprice6 integration when RS232 controlled.

#### Xantech High-Density Cable Models

Some Xantech MX88/MX88ai models use high-density HD15 (or DE15) connectors for rear COM ports, thus requiring Xantech's "DB15 to DB9" adapter cable (PN 05913665). The front DB9 RS232 and USB COM ports cannot be used for device control on these models. Instead, use the rear COM ports which are already wired as a 'null modem' connection, so no use of null modem cable is required as the Transmit and Receive lines have already been interchanged.

##### MX88 RS232 Control Cable (Xantech Part 05913665)

Thanks to @skavan for figuring out the pinouts for the discontinued RS232 Control DB15 cable (PN 05913665) with incorrect pinouts listed in the Xantech manual. The following are the correct pinouts:

| HDB15 Male | Function | DB9 Female | DB9 Color | Function | Notes |
|:----------:|:--------:|:----------:| --------- | -------- | ----- |
|     13      | Tx  |     2     | Brown     | Rx    | |
|     12      | Rx  |     3     | White     | Tx    | |
|     4      | DSR |       4     | Green     | DTR      | |
|     6      | DTR |      6     | Red       | DSR      | |
|     9      | GND |     5     | Yellow    | GND      | Ground (see also pin 11) |
|     11      | GND |     5     | Yellow    | GND      | Ground (OPTIONAL) |

Example parts needed to build a custom Xantech MX88 style cable:

* [USB to DB9 RS232 Cable](https://amzn.com/dp/B0753HBT12?tag=carreramfi-20&tracking_id=carreramfi-20) or [IP/Ethernet to DB9 Adapter](https://amzn.com/dp/B0B8T95FV1?tag=carreramfi-20&tracking_id=carreramfi-20) or [Virtual IP2SL](https://github.com/rsnodgrass/virtual-ip2sl)

* [DB9 Female Connector with wires](https://amzn.com/dp/B0BG2BPVXV?tag=carreramfi-20&tracking_id=carreramfi-20) or [DB9 Female Connector](https://amzn.com/dp/B09L7K511Y?tag=carreramfi-20&tracking_id=carreramfi-20)

* [Xantech Male DB15 Connector](https://amzn.com/dp/B07P6R8DRJ?tag=carreramfi-20&tracking_id=carreramfi-20)

For help, [ask questions on the support forum](https://community.home-assistant.io/t/xantech-dayton-audio-sonance-multi-zone-amps/450908/80)

##### Expansion Port Cable (Xantech Part ???)

Pinouts as documented in the Xantech MX88 manual:

| HDB15 Male | Function | DB9 Female | DB9 Color | Function | Notes |
|:----------:|:--------:|:----------:| --------- | -------- | ----- |
|     2      | Tx  |     2     | Brown     | Rx    | |
|     3      | Rx  |      3     | White     | Tx    | |
|     4      | DSR |       4     | Green     | DTR      | |
|     5      | GND |     5     | Yellow    | GND      | Ground |
|     6      | DTR |      6     | Red       | DSR      | |

This may be the Xantech Null Modem Cable PN 05913560.


## See Also

* [Protocol Definitions - Xantech / Monoprice / Sonance (reusable in other projects)](pyxantech/protocols)
* [Hardware Specifications - Xantech / Monoprice / Sonance (reusable in other projects)](pyxantech/series)

#### Other

* [Home Assistant integration](https://www.home-assistant.io/integrations/monoprice/)
* [Monoprice RS232 serial protocol manual](doc/Monoprice-RS232-Manual.pdf)
* [Monoprice RS232 serial protocol control](doc/Monoprice-RS232-Control.pdf)
* [Xantech DIY System](https://www.audaud.com/xantech-multi-room-audio-system/)
* [Monoprice 6 ESP32 to RS232 custom hardware](https://github.com/jhenkens/monoprice-6ch-esphome)

#### Community Engagement

Sites with active community engagement around the Xantech, Monoprice, and Daytona AUdio
multi-zone amplifiers:

* [AVS Forum: Monoprice 6](https://www.avsforum.com/forum/36-home-v-distribution/1506842-any-experience-monoprice-6-zone-home-audio-multizone-controller-23.html)
* http://cocoontech.com/forums/topic/25893-monoprice-multi-zone-audio/
* [Home Assistant: Monoprice 6](https://community.home-assistant.io/t/monoprice-whole-home-audio-controller-10761-success/19734/67)
* [RS232 to USB cable](https://www.amazon.com/RS232-to-USB/dp/B0759HSLP1?tag=carreramfi-20)
