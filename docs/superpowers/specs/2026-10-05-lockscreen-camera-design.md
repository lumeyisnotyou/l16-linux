# Lock-screen camera (design)

Status: draft for review, 2026-10-05. Builds on the default-camera setting (commit 7129b93).

## Goal

From a locked L16, open the default camera in a moment, the way a camera should behave: a camera
button on the lock screen, or a press of the hardware shutter, even with the screen off. The device
stays locked. Nothing but the camera is reachable until it is closed, and then the lock is back.

## Decisions (from the user)

- **Scope while locked: shoot, and review this session's shots.** No gallery, no settings, no
  photo from before the lock screen camera opened.
- **Trigger: the on-screen lock-screen button and the hardware shutter button.**
- **The camera is the default camera** (`org.l16linux.camera default-camera`: Nebula or Viewfinder).
- **A switch to turn it off** in L16 Settings.
- **The cameras are discovered, not hardcoded:** a camera app declares itself in its desktop file
  (`X-L16-Camera=true`); L16 Settings lists whatever declares it (and is installed), so a third
  camera app needs no change to Settings or phosh.

## Not in scope

Full-quality review of locked shots, other apps over the lock, a quick-launch for anything but the
camera, and upstreaming to phosh.

## Background: how phosh 0.55 locks

- The lock screen is not a compositor session lock. `PhoshLockscreen` (`src/lockscreen.c`) and
  `PhoshLockshield` (`src/lockshield.c`, other outputs) are `OVERLAY`-layer layer-shell surfaces over
  the windows, and while locked the panels are moved to the overlay layer too (`src/shell.c`,
  `top_layer`).
- `PhoshLockscreenManager` owns the locked state and mirrors it into `PhoshShell:locked`.
- The stock `launcher-box` lock-screen plugin starts apps with `g_app_info_launch`
  (`plugins/launcher-box/launcher-box.c`), but their windows stay under the overlay, so it can't show
  a camera.
- Windows are tracked by `PhoshToplevelManager` (`toplevel-added`, `toplevel-changed`, `closed`;
  `phosh_toplevel_get_app_id`, `_is_activated`, `_is_fullscreen`).
- New D-Bus services follow `src/debug-control.c`: an XML interface in `src/dbus/`, a manager that
  calls `g_bus_own_name`.

So the camera can only be shown by the lock screen stepping aside, and everything that makes that
safe has to be done by phosh.

## Architecture

```
 hardware shutter ──► l16-shutter (user service) ──┐
 lock-screen button ──────────────────────────────┤  Open()
                                                   ▼
                          phosh: LockscreenCameraManager  (patch)
                           │ reads default-camera, lock-screen-camera (gsettings)
                           │ launches <camera>.desktop action "Locked"  ─► camera --locked
                           │ watches PhoshToplevelManager for that app's window
                           ▼
              locked state "camera up": lock overlay + panels hidden,
              gestures off; re-covers on any exit condition
```

### 1. Phosh patch (`pmaports/temp/phosh/lockscreen-camera.patch`, phosh r101)

New object `PhoshLockscreenCameraManager`, owner of the D-Bus name `org.l16linux.Shell.LockscreenCamera`
(object `/org/l16linux/Shell/LockscreenCamera`) with one method:

- `Open()` (no arguments). It never takes an app id: the app is always resolved by phosh from
  `default-camera`. For the locked path the desktop entry must also be **system-installed** (under
  `/usr/share/applications`, not a user-writable directory), declare `X-L16-Camera=true`, and have a
  `Locked` action; otherwise `Open()` does nothing while locked. A caller can only ask for "the camera".

`Open()` behavior:

- **Unlocked:** launch the default camera normally (its plain `Exec`), and wake the display if blank.
- **Locked, and `lock-screen-camera` on:** wake the display, launch the desktop action `Locked`
  (`<camera> --locked`), start a 5 s watch for that app's toplevel to be mapped, activated and
  fullscreen.
- **Locked, and the key off:** do nothing (the screen is only woken).

When the toplevel is up, enter the "camera over lock" state:

- the lock screen and lock shields are hidden, but `locked` stays TRUE;
- the top panel, the home bar and the overview are hidden, and the drag-surface gestures
  (`drag-surface.c`: home, overview, notification shade, quick settings) are disabled, so the camera
  can't be left for another app;
- the power key still blanks the screen as usual.

It re-covers (shows the lock screen and the panels again, restores the gestures) when any of these
happens:

- the toplevel unmaps (camera closed), loses activation, or leaves fullscreen;
- another toplevel becomes activated or mapped;
- the screen blanks (idle or power key), or the display is turned off;
- the 5 s launch watch expires without the window (stays locked: a failed launch is never a bypass);
- anything calls `lock` again.

Failure rule: if the manager's state is ever inconsistent (the toplevel can't be found, a signal is
missed), it re-covers. The default is locked.

L16 additions to the lock screen: a camera button (`phosh-lockscreen-camera` CSS, bottom corner, shown only when
`lock-screen-camera` is on and a camera is installed) calling the same code path as `Open()`.

### 2. Shutter listener (`l16-shutter`, new small Rust package in this repo)

- A user service, autostarted with the session (like `light-lfc-rotate.desktop`).
- Reads the `gpio-keys` evdev device for `KEY_CAMERA` (212), as `nebula/src/input.rs` does (udev
  already gives the logged-in user access).
- On a press: if `$XDG_RUNTIME_DIR/l16-camera.front` exists (a camera app is in front and handles the
  key itself), ignore it; otherwise call `Open()` on the session bus. Phosh decides what that means
  when locked or not.
- It carries no security decision: a caller of `Open()` can only ever get the default camera.

### 3. Camera apps (`--locked`)

Both Nebula and Viewfinder add a `--locked` mode and a `Locked` desktop action:

- no gallery launch from the thumbnail, no settings, no system panel (but a close button);
- a strip of this session's shots: the preview frame kept at each shutter (not the processed photo,
  since LRI decoding is slow), held in memory and dropped on exit;
- the photos are saved as usual to `~/Pictures/L16`, so they appear in the gallery after unlock;
- exits when the screen blanks (they already stop their streams then; with `--locked` they close, so
  the lock comes back).

### 4. Settings and schema

- New key `org.l16linux.camera lock-screen-camera` (boolean, default true) in
  `l16-settings/org.l16linux.gschema.xml`.
- A switch "Camera on the lock screen" in L16 Settings' Camera group.
- The "Default camera" row is built from `gio::DesktopAppInfo::all()` filtered by `X-L16-Camera=true`
  (replacing the hardcoded two-entry `CAMERAS` array in `l16-settings/src/main.rs`); the chosen one
  stays listed even if its app has gone. The gallery's `default_camera()` already works with any id.
- Both camera apps' desktop files gain `X-L16-Camera=true` and `Actions=Locked;`.
- Phosh reads both keys through the schema source lookup used by the gallery (no abort when the
  schema is missing: the feature is then off).

## Security invariants (what must hold; each is tested)

1. While in "camera over lock", no window other than the camera's is visible or reachable.
2. No gesture, button or key combination leaves the camera for another app, the overview, the
   shade or the quick settings.
3. Any failure, timeout or ambiguity ends locked, with the lock screen shown.
4. The shown app is only ever the default camera, chosen by phosh and never by a caller.
5. The camera in locked mode cannot open the gallery or any previous photo.
   The exit gesture only closes the camera and re-covers; it can never open the overview.
6. Unlocking is still only through the keypad/biometrics: the feature never sets `locked` to FALSE.

## Leaving the camera (a way out, by gesture)

With the home and top gestures off, the camera still has to be closable without unlocking, and
closing it must land on the lock screen. Three ways out, all ending locked:

1. **Swipe up from the bottom edge** (the usual "go home" gesture). In "camera over lock" phosh shows
   its own thin exit strip instead of the home bar: a small `OVERLAY` layer surface anchored to the
   bottom edge, its input region only that strip, with a visible handle. An upward drag past a
   threshold asks the camera's toplevel to close (`phosh_toplevel_close`) and re-covers the screen at
   once, without waiting for the app. It is a separate surface, not the home surface, so the overview
   code is never involved and a swipe can't open it.
2. **A close button in the camera** (kept in `--locked` mode, where the system panel is otherwise
   gone): it quits the app, and phosh re-covers when the window unmaps.
3. **The power button**: blanks the screen, and phosh re-covers.

Rules: the lock screen is shown the moment the exit gesture completes, even if the camera is slow or
hung (it is covered, not exposed); phosh asks it to close, and if the window is still there after
3 s it signals the process. Shots in flight keep saving (the camera app holds its sleep inhibitor
until they are written), and the app exits after.

## How the gestures are shut off (the risky part, concretely)

What phosh 0.55 does, from the source:

- The **home surface** (`src/home.c`: the home bar and the overview/app grid, a bottom-edge drag
  surface) is normally unreachable when locked only because the lock screen is an exclusive overlay
  on top of it. With the lock overlay hidden, an upward swipe from the bottom edge would unfold the
  overview: every open window and the app grid. That is the main bypass to close.
- The **top panel** (`src/top-panel.c`) is moved to the overlay layer while locked and keeps a drag
  handle (the notification shade and quick settings). With the lock overlay hidden it would be
  draggable too.
- Guards that already follow `PhoshShell:locked` stay in force, because the design never clears it:
  notification banners are suppressed (`shell.c`: `!priv->locked`), and shortcuts run in
  the lock-screen action mode (`gnome-shell-manager.c`: `get_action_mode`).

So "gestures off" is two switches plus a fail-safe, applied when entering "camera over lock" and
undone when re-covering:

1. Home: set its drag mode to none (`phosh_drag_surface_set_drag_mode`) and hide its surface, so
   the home bar and overview can't be reached. The bottom edge is instead the exit strip above.
2. Top panel: the same for the top edge (no shade, no quick settings, no power menu from it).
3. Fail-safe: any state change not listed above (a new layer surface mapping, a toplevel other than
   the camera activating) re-covers instead of trying to handle it.

Not yet known, and checked before anything else is built: whether phosh creates other surfaces that
take edge touches (the on-screen keyboard, the emergency menu, modal prompts), and how phoc stacks
and focuses windows with the overlay hidden. The plan starts with a stand-in app to find out.

## Risks

- **A missed surface or gesture** is the main risk: one edge that still reaches something other than
  the camera is a lock bypass. Mitigation is the test method below, run for every edge and every
  surface phosh creates.
- **A phosh patch** can break the lock screen; the session can be left unable to unlock. Mitigation:
  the whole behavior sits behind `lock-screen-camera`, I build and test with an SSH session open, and
  the device can go back to phosh r100 with `apk add phosh=0.55.0-r100`.
- **The shutter** is read as a raw evdev device by two programs at once (the listener and the camera
  app). Both only read; the front marker keeps them from both acting.

## Test plan

**Method, so that it doesn't rest on my say-so:** with the camera over the lock, synthesise touches
through `/dev/uinput` (a swipe from each of the four edges, long presses, two-finger and corner
touches) and take a whole-output screenshot with `grim` (wlr-screencopy, from the phosh session) before
and after each. A pass is a screenshot that still shows only the camera, then the keypad after
re-cover. The same script is run with the camera closed (must show the lock screen) and with an app
open behind (must never show). `apk add grim` and a small uinput script are the only extra tools.

On the device, with SSH open: the exit swipe from the bottom edge (closes the camera, lock screen
shows, a shot taken just before it still saves), the close button, the power button, a hung camera
(lock screen still shows at once); shutter from a blanked locked screen; the lock-screen button; all
four edge swipes; the power key; the back/close paths; a camera that fails to start (stays locked);
killing the camera (re-locks); another window open behind (must never show); the switch off; an
unlocked shutter press; and the full unlock with the keypad after a locked shoot.

## Build order

1. Schema key and Settings switch (smallest, no phosh).
2. Phosh patch, with a stand-in camera, tested on the device (the risky half).
3. Camera apps' `--locked` mode.
4. `l16-shutter`, and the lock-screen button.

## As built (deviations from the design above, and why)

- **Shutter listener:** a Python user service in `device-light-lfc` (`light-lfc-shutter`), not a Rust
  package: one package fewer to build and vet. It asks logind (the display session's `LockedHint`)
  whether the session is locked: locked, every press goes to phosh (a camera app left open behind the
  lock is asleep and throws presses away); unlocked, a camera app in front (a live claim in
  `$XDG_RUNTIME_DIR/l16-strip/`, or the older empty `l16-camera.front` while a camera app runs) takes
  the key itself.
- **Launch watch:** 15 s, not 5 s (a camera's cold start is 4-6 s, and a camera app left open is closed
  first, a few seconds more). A camera that turns up after the watch is terminated.
- **A camera app left open:** when the lock screen camera is opened, any window of the camera's app id
  that is already open is asked to close first, and the locked camera starts when it has (two instances
  can't hold the camera); those windows are never mistaken for the locked camera.
- **Lock screen button:** top right of the clock page (the bottom hangs off a 540 px display), made in
  C, not the template (binding it there made GTK stop assigning the template's children).
- **This session's shots:** a review page opened from the thumbnail (back, previous/next, swipe), the
  last 50 preview frames held in RAM (not a strip), in both camera apps. Over the lock, Nebula has no
  close button: the exit is phosh's swipe up from the bottom edge.
- **Not implemented:** re-covering when anything calls `lock` again (the shell stays locked: not a
  bypass), and re-covering when a new layer surface maps (phosh can't see other clients' layer
  surfaces); every other window or focus change re-covers.
- **The passcode page** is laid out side by side on a landscape display (text and Unlock left, the
  keypad right), placed by the display's real height, with a tint that deepens as the swipe goes up.

