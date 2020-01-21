# Python interface for Xantech amplifiers

## Status
[![Build Status](https://travis-ci.org/etsinko/pyxantech.svg?branch=master)](https://travis-ci.org/etsinko/pyxantech)[![Coverage Status](https://coveralls.io/repos/github/etsinko/pyxantech/badge.svg)](https://coveralls.io/github/etsinko/pyxantech)

# pyxantech
Python3 interface implementation for Xantech 6 zone amplifier

## Notes
This is for use with [Home-Assistant](http://home-assistant.io)

## Usage
```python
from pyxantech import get_amp_controller

amp = get_amp_controller('xantech', '/dev/ttyUSB0')

# Turn off zone #11
amp.set_power(11, False)

# Mute zone #12
amp.set_mute(12, True)

# Set volume for zone #13
amp.set_volume(13, 15)

# Set source 1 for zone #14 
amp.set_source(14, 1)
```

See also [example.py](example.py) for a more complete example.

## Usage with asyncio

With `asyncio` flavor all methods of Xantech object are coroutines.

```python
import asyncio
from pyxantech import get_async_xantech

async def main(loop):
    xantech = await get_async_xantech('/dev/ttyUSB0', loop)
    zone_status = await xantech.zone_status(11)
    if zone_status.power:
        await xantech.set_power(zone_status.zone, False)

loop = asyncio.get_event_loop()
loop.run_until_complete(main(loop))

```
