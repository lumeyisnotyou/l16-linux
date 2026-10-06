# The touch strip

The L16's touch strip is a long, thin touch input (the evdev device "Light L16 touch strip",
reported along the strip as `ABS_X` over 0 to 768). Two things use it:

- **`light-lfc-strip-volume`** (a service) turns swipes into volume keys, one key press per tenth
  of the strip, through a uinput device, so the desktop shows its volume on-screen display.
- **The camera apps** (Viewfinder, Nebula) read the device themselves and use it for zoom.

Both read the same device, so an app that wants the strip has to tell the service, or a swipe
would zoom and change the volume.

## Claiming the strip

An app that wants the strip creates a file named for the app in `l16-strip/` in its runtime
directory, containing its PID, and removes it when it no longer wants the strip:

```sh
mkdir -p "$XDG_RUNTIME_DIR/l16-strip"
echo $$ > "$XDG_RUNTIME_DIR/l16-strip/my-app"     # claim
rm "$XDG_RUNTIME_DIR/l16-strip/my-app"            # let go
```

- The service leaves the volume alone for as long as any claim exists whose process is still
  running. A claim left behind by a crash doesn't count (its PID is gone), so it can't hold the
  strip.
- The check is made when a touch starts: a touch that began before a claim finishes as volume, and
  one that began after it belongs to the app.
- Any app may claim, whatever it is; it needn't be a camera.

## Older apps

Viewfinder (and Nebula, for the older service) also write `l16-camera.front` in the runtime
directory. The service still honours it while a process called `l16-camera` or `nebula` runs, so an
older camera app keeps working.

## Tests

`python3 tools/test-strip-claims.py` tests the service's claim logic (it runs anywhere with Python:
the liveness check is `kill(pid, 0)`, not `/proc`).
