#!/usr/bin/env python3
"""Fake touch gestures on a uinput touchscreen, to test the lock screen camera.

Run on the device as root:
  lockcam-touch.py edges                    a swipe in from each of the four edges (the bottom one last)
  lockcam-touch.py swipe X1 Y1 X2 Y2 [ms]   one swipe
  lockcam-touch.py tap X Y                  a tap
  lockcam-touch.py longpress X Y [ms]       a long press
  lockcam-touch.py corners                  a tap in each corner
Coordinates are 0-1000 on both axes, of the display as it is held (landscape).
The compositor maps a touch device that belongs to no output over the whole layout.
"""
import fcntl, os, struct, sys, time

UI_SET_EVBIT, UI_SET_KEYBIT, UI_SET_ABSBIT, UI_SET_PROPBIT = 0x40045564, 0x40045565, 0x40045567, 0x4004556e
UI_DEV_CREATE, UI_DEV_DESTROY = 0x5501, 0x5502
EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
BTN_TOUCH = 0x14a
ABS_X, ABS_Y, ABS_MT_SLOT, ABS_MT_POSITION_X, ABS_MT_POSITION_Y, ABS_MT_TRACKING_ID = 0, 1, 0x2f, 0x35, 0x36, 0x39
INPUT_PROP_DIRECT = 1
MAXV = 1000


class Touch:
    def __init__(self):
        self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        for ev in (EV_KEY, EV_ABS, EV_SYN):
            fcntl.ioctl(self.fd, UI_SET_EVBIT, ev)
        fcntl.ioctl(self.fd, UI_SET_KEYBIT, BTN_TOUCH)
        fcntl.ioctl(self.fd, UI_SET_PROPBIT, INPUT_PROP_DIRECT)
        absmax = [0] * 64
        for a in (ABS_X, ABS_Y, ABS_MT_POSITION_X, ABS_MT_POSITION_Y):
            fcntl.ioctl(self.fd, UI_SET_ABSBIT, a)
            absmax[a] = MAXV
        for a, m in ((ABS_MT_SLOT, 9), (ABS_MT_TRACKING_ID, 65535)):
            fcntl.ioctl(self.fd, UI_SET_ABSBIT, a)
            absmax[a] = m
        name = b"lockcam-test-touch".ljust(80, b"\0")
        dev = name + struct.pack("<HHHHi", 3, 0x1234, 0x5678, 1, 0)
        dev += struct.pack("<64i", *absmax) + struct.pack("<64i", *([0] * 64))
        dev += struct.pack("<64i", *([0] * 64)) + struct.pack("<64i", *([0] * 64))
        os.write(self.fd, dev)
        fcntl.ioctl(self.fd, UI_DEV_CREATE)
        time.sleep(1.5)  # let libinput and the compositor pick it up
        self.tid = 100

    def ev(self, t, c, v):
        now = time.time()
        os.write(self.fd, struct.pack("<qqHHi", int(now), int((now % 1) * 1e6), t, c, v))  # 24 bytes: 64-bit time ("<l" is only 4 bytes)

    def syn(self):
        self.ev(EV_SYN, 0, 0)

    # the camera is held in landscape, but a touch device with no output of its own is taken to be
    # in the panel's native (portrait) orientation, so the compositor turns it by the panel's 270:
    # a landscape (x, y) is sent as (MAXV - y, x)
    @staticmethod
    def native(x, y):
        return MAXV - y, x

    def down(self, x, y):
        self.tid += 1
        self.ev(EV_ABS, ABS_MT_SLOT, 0)
        self.ev(EV_ABS, ABS_MT_TRACKING_ID, self.tid)
        self.move(x, y)
        self.ev(EV_KEY, BTN_TOUCH, 1)
        self.syn()

    def move(self, x, y):
        x, y = self.native(x, y)
        self.ev(EV_ABS, ABS_MT_POSITION_X, int(x))
        self.ev(EV_ABS, ABS_MT_POSITION_Y, int(y))
        self.ev(EV_ABS, ABS_X, int(x))
        self.ev(EV_ABS, ABS_Y, int(y))
        self.syn()

    def up(self):
        self.ev(EV_ABS, ABS_MT_SLOT, 0)
        self.ev(EV_ABS, ABS_MT_TRACKING_ID, -1)
        self.ev(EV_KEY, BTN_TOUCH, 0)
        self.syn()

    def swipe(self, x1, y1, x2, y2, ms=300, steps=20):
        self.down(x1, y1)
        for i in range(1, steps + 1):
            time.sleep(ms / 1000 / steps)
            self.move(x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps)
        self.up()
        time.sleep(0.4)

    def tap(self, x, y):
        self.swipe(x, y, x, y, ms=60, steps=2)

    def longpress(self, x, y, ms=1200):
        self.swipe(x, y, x, y, ms=ms, steps=4)

    def close(self):
        fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        os.close(self.fd)


def main(argv):
    if not argv:
        sys.exit(__doc__)
    t = Touch()
    try:
        cmd, a = argv[0], [float(v) for v in argv[1:]]
        if cmd == "edges":
            t.swipe(500, 5, 500, 400)     # down from the top edge
            t.swipe(5, 500, 400, 500)     # in from the left edge
            t.swipe(995, 500, 600, 500)   # in from the right edge
            t.swipe(500, 995, 500, 600)   # up from the bottom edge (last: with the exit strip it leaves the camera)
        elif cmd == "swipe":
            t.swipe(*a[:4], ms=a[4] if len(a) > 4 else 300)
        elif cmd == "tap":
            t.tap(*a[:2])
        elif cmd == "longpress":
            t.longpress(*a[:2], ms=a[2] if len(a) > 2 else 1200)
        elif cmd == "corners":
            for x, y in ((8, 8), (992, 8), (8, 992), (992, 992)):
                t.tap(x, y)
        else:
            sys.exit(__doc__)
        time.sleep(0.5)
    finally:
        t.close()


main(sys.argv[1:])
