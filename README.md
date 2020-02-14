# Python interface for Monoprice, Xantech, and Dayton Audio amplifiers

This was originally created for use with [Home-Assistant](http://home-assistant.io), but can be
used in other contexts as well. It supports both the 6-zone Monoprice and 8-zone Xantech amplifiers,
as well as 6-zone Dayton Audio DAX66 amplifiers.

## Status

[![Build Status](https://travis-ci.org/etsinko/pyxantech.svg?branch=master)](https://travis-ci.org/etsinko/pyxantech)[![Coverage Status](https://coveralls.io/repos/github/etsinko/pyxantech/badge.svg)](https://coveralls.io/github/etsinko/pyxantech)

## Usage

For Monoprice and Dayton Audio 6-zone amplifiers:

```python
from pymonoprice import get_amp_controller, get_monoprice, MONOPRICE6

amp = get_amp_controller(MONOPRICE6, '/dev/ttyUSB0')
# amp = get_monoprice('/dev/ttyUSB0') # DEPRECATED STYLE

# Turn off zone #12 (amplifier 1 / zone 1)
amp.set_power(12, False)

# Mute zone #11
amp.set_mute(11, True)

# Set volume for zone #13
amp.set_volume(13, 15)

# Set source 1 for zone #14 
amp.set_source(14, 1)
```

For Xantech 8-zone amplifiers:

```python
from pyxantech import get_amp_controller, XANTECH8

amp = get_amp_controller(XANTECH8, '/dev/ttyUSB0')
amp.set_source(12, 3)
```

See also [example.py](example.py) for a more complete example.

## Usage with asyncio

With the `asyncio` flavor, all methods of the controller objects are coroutines:

```python
import asyncio
from pymonoprice import get_async_amp_controller, MONOPRICE6

async def main(loop):
    amp = await get_async_amp_controller(MONOPRICE6, '/dev/ttyUSB0', loop)
    zone_status = await amp.zone_status(11)
    if zone_status.power:
        await amp.set_power(zone_status.zone, False)

loop = asyncio.get_event_loop()
loop.run_until_complete(main(loop))
```

## See Also

* [Home Assistant integration](https://www.home-assistant.io/integrations/monoprice/)
