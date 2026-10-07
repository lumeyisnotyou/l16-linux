#!/usr/bin/env python3
"""Tests for the shutter listener (light-lfc-shutter): a press of the shutter button asks phosh for the
camera (Open() on the session bus) unless a camera app is already in front and takes the key itself.
Run: python3 tools/test-shutter.py"""
import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "pmaports", "device", "testing", "device-light-lfc", "light-lfc-shutter")


def load():
    loader = importlib.machinery.SourceFileLoader("shutter", SCRIPT)
    spec = importlib.util.spec_from_loader("shutter", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def dead_pid():
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


class Press(unittest.TestCase):
    def setUp(self):
        self.sh = load()
        self.tmp = tempfile.TemporaryDirectory()
        self.rd = self.tmp.name
        self.opened = 0
        self.sh.comm_running = lambda comms: False  # no camera app running unless a test says so

    def tearDown(self):
        self.tmp.cleanup()

    def opener(self):
        self.opened += 1

    def marker(self, content):
        with open(os.path.join(self.rd, "l16-camera.front"), "w") as f:
            f.write(content)

    def press(self, code=None, value=1, now=100.0):
        h = self.sh.Handler(self.rd, self.opener)
        return h.event(self.sh.KEY_CAMERA if code is None else code, value, now), h

    def test_a_press_with_no_camera_in_front_opens_the_camera(self):
        self.press()
        self.assertEqual(self.opened, 1)

    def test_other_keys_do_nothing(self):
        self.press(code=115)
        self.assertEqual(self.opened, 0)

    def test_the_release_and_the_repeat_do_nothing(self):
        self.press(value=0)
        self.press(value=2)
        self.assertEqual(self.opened, 0)

    def test_a_camera_in_front_takes_the_key_itself(self):
        self.marker(str(os.getpid()))
        self.press()
        self.assertEqual(self.opened, 0)

    def test_a_marker_of_a_dead_process_does_not_count(self):
        self.marker(str(dead_pid()))
        self.press()
        self.assertEqual(self.opened, 1)

    def test_a_marker_with_trailing_text_still_names_its_process(self):
        self.marker("%d nebula\n" % os.getpid())
        self.press()
        self.assertEqual(self.opened, 0)

    def test_an_older_marker_without_a_pid_counts_while_a_camera_app_runs(self):
        self.marker("")
        self.sh.comm_running = lambda comms: True
        self.press()
        self.assertEqual(self.opened, 0)

    def test_an_older_marker_without_a_pid_is_stale_when_no_camera_app_runs(self):
        self.marker("")
        self.press()
        self.assertEqual(self.opened, 1)

    def test_a_press_just_after_another_is_one_request(self):
        h = self.sh.Handler(self.rd, self.opener)
        h.event(self.sh.KEY_CAMERA, 1, 100.0)
        h.event(self.sh.KEY_CAMERA, 1, 100.4)
        h.event(self.sh.KEY_CAMERA, 1, 102.0)
        self.assertEqual(self.opened, 2)

    def test_a_failing_open_does_not_stop_the_listener(self):
        def boom():
            raise OSError("no gdbus")
        h = self.sh.Handler(self.rd, boom)
        h.event(self.sh.KEY_CAMERA, 1, 100.0)  # must not raise

    def test_importing_the_script_does_not_run_it(self):
        self.assertTrue(callable(self.sh.main))


if __name__ == "__main__":
    unittest.main()
