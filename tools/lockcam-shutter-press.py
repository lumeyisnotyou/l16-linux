#!/usr/bin/env python3
"""A fake shutter button on a uinput device, to test light-lfc-shutter on the camera (run as root).
It creates the device "lockcam-shutter" (KEY_CAMERA), prints its /dev/input node, then reads
commands from stdin: "press" sends a press and a release, "quit" ends.
  mkfifo /tmp/sp; python3 lockcam-shutter-press.py < /tmp/sp &  exec 3>/tmp/sp;  echo press >&3"""
import fcntl, os, struct, sys, time, glob

UI_SET_EVBIT, UI_SET_KEYBIT, UI_DEV_CREATE, UI_DEV_DESTROY = 0x40045564, 0x40045565, 0x5501, 0x5502
EV_SYN, EV_KEY = 0, 1
KEY_CAMERA = 212


def main():
    fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
    for ev in (EV_KEY, EV_SYN):
        fcntl.ioctl(fd, UI_SET_EVBIT, ev)
    fcntl.ioctl(fd, UI_SET_KEYBIT, KEY_CAMERA)
    name = b"lockcam-shutter".ljust(80, b"\0")
    dev = name + struct.pack("<HHHHi", 3, 0x1234, 0x5679, 1, 0) + struct.pack("<256i", *([0] * 256))
    os.write(fd, dev)
    fcntl.ioctl(fd, UI_DEV_CREATE)
    time.sleep(1.5)
    node = None
    for n in glob.glob("/sys/class/input/event*/device/name"):
        if open(n).read().strip() == "lockcam-shutter":
            node = "/dev/input/" + n.split("/")[4]
    if node:
        os.chmod(node, 0o666)  # the listener runs as the user
    print(node, flush=True)

    def send(t, c, v):
        now = time.time()
        os.write(fd, struct.pack("<qqHHi", int(now), int((now % 1) * 1e6), t, c, v))

    for line in sys.stdin:
        cmd = line.strip()
        if cmd == "press":
            send(EV_KEY, KEY_CAMERA, 1); send(EV_SYN, 0, 0)
            time.sleep(0.12)
            send(EV_KEY, KEY_CAMERA, 0); send(EV_SYN, 0, 0)
        elif cmd == "quit":
            break
    fcntl.ioctl(fd, UI_DEV_DESTROY)


main()
