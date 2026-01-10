"""Test utilities for pyxantech tests."""

from __future__ import annotations

import os
import pty
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def create_dummy_port(responses: dict[bytes, bytes]) -> str:
    """Create a pseudo-terminal that simulates serial port responses.

    Args:
        responses: Dictionary mapping request bytes to response bytes.

    Returns:
        Path to the slave pseudo-terminal device.
    """

    def listener(port: int) -> None:
        while True:
            res = b''
            while not res.endswith(b'\r'):
                res += os.read(port, 1)

            if res in responses:
                resp = responses[res]
                del responses[res]
                os.write(port, resp)

    master, slave = pty.openpty()
    thread = threading.Thread(target=listener, args=[master], daemon=True)
    thread.start()
    return os.ttyname(slave)
