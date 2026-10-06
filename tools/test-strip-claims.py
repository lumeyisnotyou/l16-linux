#!/usr/bin/env python3
"""Tests for the touch strip's claims (light-lfc-strip-volume): an app that wants the strip
puts a file named for it, holding its PID, in $XDG_RUNTIME_DIR/l16-strip/, and the volume
service then leaves the strip alone. Run: python3 tools/test-strip-claims.py"""
import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "pmaports", "device", "testing", "device-light-lfc", "light-lfc-strip-volume")


def load():
    loader = importlib.machinery.SourceFileLoader("strip_volume", SCRIPT)
    spec = importlib.util.spec_from_loader("strip_volume", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def dead_pid():
    # a process that has finished and been reaped: its PID is free (and unlikely to be reused at once)
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


class Claims(unittest.TestCase):
    def setUp(self):
        self.sv = load()
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "l16-strip")
        os.makedirs(self.dir)
        # the service looks in /run/user/*/l16-strip/*; the tests point it at a temporary directory
        self.sv.CLAIMS = os.path.join(self.tmp.name, "l16-strip", "*")
        self.sv.camera_in_front = lambda: False  # the older marker is tested on its own

    def tearDown(self):
        self.tmp.cleanup()

    def claim(self, name, content):
        with open(os.path.join(self.dir, name), "w") as f:
            f.write(content)

    def test_no_claims_means_volume(self):
        self.assertFalse(self.sv.claimed())

    def test_a_live_claim_keeps_the_strip(self):
        self.claim("nebula", str(os.getpid()))
        self.assertTrue(self.sv.claimed())

    def test_a_claim_of_a_dead_process_does_not_count(self):
        self.claim("crashed", str(dead_pid()))
        self.assertFalse(self.sv.claimed())

    def test_garbage_in_a_claim_is_ignored(self):
        self.claim("junk", "not a pid")
        self.claim("empty", "")
        self.claim("negative", "-1")
        self.claim("zero", "0")
        self.assertFalse(self.sv.claimed())

    def test_one_live_claim_among_stale_ones_is_enough(self):
        self.claim("a-crashed", str(dead_pid()))
        self.claim("b-live", str(os.getpid()) + "\n")
        self.assertTrue(self.sv.claimed())

    def test_a_trailing_newline_or_name_after_the_pid_is_fine(self):
        self.claim("tidy", "%d some-app\n" % os.getpid())
        self.assertTrue(self.sv.claimed())

    def test_the_older_marker_still_counts(self):
        self.sv.camera_in_front = lambda: True
        self.assertTrue(self.sv.claimed())

    def test_importing_the_script_does_not_run_it(self):
        # (load() already did: a service loop on import would have hung this test)
        self.assertTrue(callable(self.sv.main))


class OlderMarker(unittest.TestCase):
    def test_both_camera_apps_count_as_cameras(self):
        sv = load()
        self.assertIn("l16-camera", sv.CAMERA_COMMS)
        self.assertIn("nebula", sv.CAMERA_COMMS)


if __name__ == "__main__":
    unittest.main()
