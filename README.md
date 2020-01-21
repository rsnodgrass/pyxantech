# Python interface for Xantech amplifiers

This was originally created for use with [Home-Assistant](http://home-assistant.io), but can be
used in other contexts as well. It supports both the 6-zone Monoprice and 8-zone Xantech amplifiers.

## Status

[![Build Status](https://travis-ci.org/etsinko/pyxantech.svg?branch=master)](https://travis-ci.org/etsinko/pyxantech)[![Coverage Status](https://coveralls.io/repos/github/etsinko/pyxantech/badge.svg)](https://coveralls.io/github/etsinko/pyxantech)

## Usage

For Monoprice 6-zone amplifier:

```python
from pyxantech import get_amp_controller, get_monoprice

# amp = get_monoprice('/dev/ttyUSB0')  # old style
amp = get_amp_controller('monoprice', '/dev/ttyUSB0')

# Turn off zone #11
amp.set_power(11, False)

# Mute zone #12
amp.set_mute(12, True)

# Set volume for zone #13
amp.set_volume(13, 15)

# Set source 1 for zone #14 
amp.set_source(14, 1)
```

For Xantech 8-zone amplifier:

```python
from pyxantech import get_amp_controller

amp = get_amp_controller('xantech8', '/dev/ttyUSB0')
```

See also [example.py](example.py) for a more complete example.

## Usage with asyncio

With `asyncio` flavor all methods of Xantech object are coroutines.

```python
import asyncio
from pyxantech import get_async_amp_controller

async def main(loop):
    amp = await get_async_amp_controller('monoprice', '/dev/ttyUSB0', loop)
    zone_status = await amp.zone_status(11)
    if zone_status.power:
        await amp.set_power(zone_status.zone, False)

loop = asyncio.get_event_loop()
loop.run_until_complete(main(loop))

```

## See Also

* [Home Assistant integration](https://www.home-assistant.io/integrations/monoprice/)
