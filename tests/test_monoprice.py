import unittest

import serial

from pyxantech import get_xantech, get_async_xantech, ZoneStatus
from tests import create_dummy_port
import asyncio


class TestZoneStatus(unittest.TestCase):
    def test_zone_status_broken(self):
        self.assertIsNone(ZoneStatus.from_string(None))
        self.assertIsNone(ZoneStatus.from_string("\r\n#>110001000010111210040\r\n#"))
        self.assertIsNone(ZoneStatus.from_string("\r\n#>a100010000101112100401\r\n#"))
        self.assertIsNone(ZoneStatus.from_string("\r\n#>a1000100dfsf112100401\r\n#"))
        self.assertIsNone(ZoneStatus.from_string("\r\n#>\r\n#"))


class TestMonoprice(unittest.TestCase):
    def setUp(self):
        self.responses = {}
        self.xantech = get_xantech(create_dummy_port(self.responses))

    def test_zone_status(self):
        self.responses[b"?1\r"] = b"\r\n#>1100010000131112100401\r\n#"
        status = self.xantech.zone_status(1)
        self.assertEqual(11, status.zone)
        self.assertFalse(status.pa)
        self.assertTrue(status.power)
        self.assertFalse(status.mute)
        self.assertFalse(status.do_not_disturb)
        self.assertEqual(13, status.volume)
        self.assertEqual(11, status.treble)
        self.assertEqual(12, status.bass)
        self.assertEqual(10, status.balance)
        self.assertEqual(4, status.source)
        self.assertTrue(status.keypad)
        self.assertEqual(0, len(self.responses))

    def test_set_power(self):
        self.responses[b"<13PR01\r"] = b"\r\n#"
        self.xantech.set_power(13, True)
        self.responses[b"<13PR01\r"] = b"\r\n#"
        self.xantech.set_power(13, "True")
        self.responses[b"<13PR01\r"] = b"\r\n#"
        self.xantech.set_power(13, 1)
        self.responses[b"<13PR00\r"] = b"\r\n#"
        self.xantech.set_power(13, False)
        self.responses[b"<13PR00\r"] = b"\r\n#"
        self.xantech.set_power(13, None)
        self.responses[b"<13PR00\r"] = b"\r\n#"
        self.xantech.set_power(13, 0)
        self.responses[b"<13PR00\r"] = b"\r\n#"
        self.xantech.set_power(13, "")
        self.assertEqual(0, len(self.responses))

    def test_set_mute(self):
        self.responses[b"<13MU01\r"] = b"\r\n#"
        self.xantech.set_mute(13, True)
        self.responses[b"<13MU01\r"] = b"\r\n#"
        self.xantech.set_mute(13, "True")
        self.responses[b"<13MU01\r"] = b"\r\n#"
        self.xantech.set_mute(13, 1)
        self.responses[b"<13MU00\r"] = b"\r\n#"
        self.xantech.set_mute(13, False)
        self.responses[b"<13MU00\r"] = b"\r\n#"
        self.xantech.set_mute(13, None)
        self.responses[b"<13MU00\r"] = b"\r\n#"
        self.xantech.set_mute(13, 0)
        self.responses[b"<13MU00\r"] = b"\r\n#"
        self.xantech.set_mute(13, "")
        self.assertEqual(0, len(self.responses))

    def test_set_volume(self):
        self.responses[b"<13VO01\r"] = b"\r\n#"
        self.xantech.set_volume(13, 1)
        self.responses[b"<13VO38\r"] = b"\r\n#"
        self.xantech.set_volume(13, 100)
        self.responses[b"<13VO00\r"] = b"\r\n#"
        self.xantech.set_volume(13, -100)
        self.responses[b"<13VO20\r"] = b"\r\n#"
        self.xantech.set_volume(13, 20)
        self.assertEqual(0, len(self.responses))

    def test_set_treble(self):
        self.responses[b"<13TR01\r"] = b"\r\n#"
        self.xantech.set_treble(13, 1)
        self.responses[b"<13TR14\r"] = b"\r\n#"
        self.xantech.set_treble(13, 100)
        self.responses[b"<13TR00\r"] = b"\r\n#"
        self.xantech.set_treble(13, -100)
        self.responses[b"<13TR13\r"] = b"\r\n#"
        self.xantech.set_treble(13, 13)
        self.assertEqual(0, len(self.responses))

    def test_set_bass(self):
        self.responses[b"<13BS01\r"] = b"\r\n#"
        self.xantech.set_bass(13, 1)
        self.responses[b"<13BS14\r"] = b"\r\n#"
        self.xantech.set_bass(13, 100)
        self.responses[b"<13BS00\r"] = b"\r\n#"
        self.xantech.set_bass(13, -100)
        self.responses[b"<13BS13\r"] = b"\r\n#"
        self.xantech.set_bass(13, 13)
        self.assertEqual(0, len(self.responses))

    def test_set_balance(self):
        self.responses[b"<13BL01\r"] = b"\r\n#"
        self.xantech.set_balance(13, 1)
        self.responses[b"<13BL20\r"] = b"\r\n#"
        self.xantech.set_balance(13, 100)
        self.responses[b"<13BL00\r"] = b"\r\n#"
        self.xantech.set_balance(13, -100)
        self.responses[b"<13BL13\r"] = b"\r\n#"
        self.xantech.set_balance(13, 13)
        self.assertEqual(0, len(self.responses))

    def test_set_source(self):
        self.responses[b"<13CH01\r"] = b"\r\n#"
        self.xantech.set_source(13, 1)
        self.responses[b"<13CH06\r"] = b"\r\n#"
        self.xantech.set_source(13, 100)
        self.responses[b"<13CH01\r"] = b"\r\n#"
        self.xantech.set_source(13, -100)
        self.responses[b"<13CH03\r"] = b"\r\n#"
        self.xantech.set_source(13, 3)
        self.assertEqual(0, len(self.responses))

    def test_restore_zone(self):
        zone = ZoneStatus.from_string("\r\n#>1100010000131112100401\r\n#")
        self.responses[b"<11PR01\r"] = b"\r\n#"
        self.responses[b"<11MU00\r"] = b"\r\n#"
        self.responses[b"<11VO13\r"] = b"\r\n#"
        self.responses[b"<11TR11\r"] = b"\r\n#"
        self.responses[b"<11BS12\r"] = b"\r\n#"
        self.responses[b"<11BL10\r"] = b"\r\n#"
        self.responses[b"<11CH04\r"] = b"\r\n#"
        self.xantech.restore_zone(zone)
        self.assertEqual(0, len(self.responses))

    def test_timeout(self):
        with self.assertRaises(serial.SerialTimeoutException):
            self.xantech.set_source(3, 3)


class TestAsyncMonoprice(TestMonoprice):
    def setUp(self):
        self.responses = {}
        loop = asyncio.get_event_loop()
        xantech = loop.run_until_complete(
            get_async_xantech(create_dummy_port(self.responses), loop)
        )

        # Dummy xantech that converts async to sync
        class DummyMonoprice:
            def __getattribute__(self, item):
                def f(*args, **kwargs):
                    return loop.run_until_complete(
                        xantech.__getattribute__(item)(*args, **kwargs)
                    )

                return f

        self.xantech = DummyMonoprice()

    def test_timeout(self):
        with self.assertRaises(asyncio.TimeoutError):
            self.xantech.set_source(3, 3)


if __name__ == "__main__":
    unittest.main()
