# Lock-Screen Camera: the Phosh Patch (plan B)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** From a locked L16, a lock-screen button (and a D-Bus `Open()` that the shutter listener will call in plan D) opens the default camera over the lock screen; the phone stays locked; a swipe up from the bottom edge, the power button, or the camera closing puts the lock screen back.

**Architecture:** One downstream phosh patch (`pmaports/temp/phosh/lockscreen-camera.patch`, phosh 0.55.0 r101): a new `PhoshLockscreenCameraManager` owns the D-Bus name `org.l16linux.Shell.LockscreenCamera` and a small state machine (idle → launching → over-lock) driven by `PhoshToplevelManager`; `PhoshShell` gets `phosh_shell_set_camera_over_lock()` which hides the lock screen (never clearing `locked`), hides the top panel, switches the home drag off and shows a new `PhoshExitStrip` along the bottom edge; the lock screen gets a camera button. The default camera comes from our gsettings key; the camera's `Locked` desktop action starts it (plan C makes the apps understand it).

**Tech Stack:** C, GTK3 + libhandy (phosh 0.55.0), meson, gdbus-codegen, GSettings, wlr-layer-shell, Alpine APKBUILD patches, pmbootstrap (cross build on the VM), Python 3 (uinput test tool), `grim`.

**Spec:** `docs/superpowers/specs/2026-10-05-lockscreen-camera-design.md` (sections "Architecture", "Leaving the camera", "How the gestures are shut off", "Security invariants", "Test plan"). Plan A (`2026-10-05-camera-discovery.md`) is done.

## Global Constraints

- The shell stays locked while the camera is over the lock: **nothing in this patch may set `PhoshShell:locked` / `PhoshLockscreenManager:locked` to FALSE** (spec invariant 6). Only the keypad/unlock path does that.
- `Open()` takes no arguments; the app is always `default-camera` from gsettings `org.l16linux.camera` (spec invariant 4). For the locked path it must be **system-installed** (`/usr/share/applications/` or `/usr/local/share/applications/`), have `X-L16-Camera=true` and a `Locked` action; otherwise nothing is shown over the lock.
- D-Bus: name `org.l16linux.Shell.LockscreenCamera`, object `/org/l16linux/Shell/LockscreenCamera`, interface `org.l16linux.Shell.LockscreenCamera`, method `Open()` (no args, no reply value).
- The whole behavior is off when gsettings `org.l16linux.camera lock-screen-camera` is false, or when the schema is not installed (then `Open()` only launches the camera when unlocked and wakes the screen when locked).
- Timings: launch watch 5 s; close grace 3 s; a camera window must become activated within 2 s of entering over-lock; exit swipe threshold 30 logical px upward; exit strip height 40 logical px.
- Fail-safe: any unexpected state change re-covers (the default is locked).
- Phosh is built **only** through pmaports: `pmaports/temp/phosh/APKBUILD` lists the patches, `pkgrel=101`; patch checksums are sha512 of the patch files; the other three patches stay unchanged and in their order.
- Commits are authored as `lumey <46928172+lumeyisnotyou@users.noreply.github.com>` (repo-local config) and end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Do not push without being asked. Packages built on the VM: `lumey@192.168.1.6`; device: `root@192.168.1.191`.
- **The phone's session restarts to load a new phosh** (`rc-service greetd restart` logs the user out and back to the login screen). Ask the user first, every time, and tell them they will need their PIN. Never restart it while they may be using it. Keep an SSH session open while testing.
- Rollback is always: `apk add --allow-untrusted /tmp/phosh-r100.apk` (the baseline apk saved in Task 2) then `rc-service greetd restart`, or `apk add phosh=0.55.0-r100` from the repository.
- Windows opened on the phone for tests are the user's screen: close the ones you opened. Don't close the user's own apps without asking.

## Review Focus

1. **A way past the exit via another surface:** the on-screen keyboard, a notification banner, a modal system prompt, the emergency-call menu, or the power menu appearing over the camera while locked. Expected: none shows over the lock screen camera, or if one does, it leads nowhere but back to locked. (Task 4 scenario list, Task 7 final run.)
2. **The camera never shows its window (crash, slow start, no `Locked` action):** after the 5 s watch the screen is the lock screen, not a blank or stuck state; a second `Open()` still works. (Task 3 steps, Task 4.)
3. **`Open()` when already open, spammed, or called while unlocked:** no second camera, no state stuck in launching, unlocked = a plain launch. (Task 3.)
4. **The screen blanks / the power button is pressed while the camera is over the lock:** after waking, the lock screen is shown, not the camera. (Task 4.)
5. **The camera closes itself (user taps close, it crashes) while over the lock:** the lock screen returns at once and the panels work again after unlocking (top panel visible, home gesture restored). (Task 3, Task 4.)
6. **A shot in flight when the exit swipe happens:** the camera still saves it (this plan only closes the window; the app keeps its sleep inhibitor, plan C). (Task 5 notes it for plan C's test.)

---

## File Structure

New files in the phosh source (all become part of `lockscreen-camera.patch`):
- `src/dbus/org.l16linux.Shell.LockscreenCamera.xml`: the D-Bus interface.
- `src/lockscreen-camera-manager.c` / `.h`: D-Bus service, default-camera lookup, launch, the state machine.
- `src/exit-strip.c` / `.h`: the bottom-edge exit swipe surface.

Modified in the phosh source: `src/dbus/meson.build`, `src/meson.build`, `src/shell.c`, `src/shell-priv.h`, `src/lockscreen-manager.c` / `.h`, `src/lockscreen.c`, `src/ui/lockscreen.ui`, `src/stylesheet/common.css`.

In this repository:
- Create: `tools/phosh-build.sh` (patch from the work tree, build on the VM), `tools/lockcam-touch.py` (fake touch swipes through uinput), `tools/lockcam-test.sh` (scenario runner).
- Modify: `pmaports/temp/phosh/APKBUILD`, create `pmaports/temp/phosh/lockscreen-camera.patch`; `l16-settings/org.l16linux.gschema.xml`, `l16-settings/src/main.rs`, `pmaports/main/l16-settings/APKBUILD`.

The phosh work tree lives **outside** the repository at `~/src/phosh-work/phosh-0.55.0` (a git repo with the tarball and the three existing patches committed as tag `base`); only the generated patch goes into the repository.

---

### Task 1: The `lock-screen-camera` key and its Settings switch

**Files:**
- Modify: `l16-settings/org.l16linux.gschema.xml`
- Modify: `l16-settings/src/main.rs`
- Modify: `pmaports/main/l16-settings/APKBUILD` (checksum only; `pkgrel` stays `1`, because r1 was never built or published)

**Interfaces:**
- Produces: gsettings `org.l16linux.camera` key `lock-screen-camera` (boolean, default true), read by phosh (Task 3); a switch row "Camera on the lock screen" in L16 Settings.

- [ ] **Step 1: Add the key and refresh the `default-camera` description**

Replace `l16-settings/org.l16linux.gschema.xml` with:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<schemalist>
  <schema id="org.l16linux.camera" path="/org/l16linux/camera/">
    <key name="default-camera" type="s">
      <default>'org.l16linux.Camera.desktop'</default>
      <summary>Default camera app</summary>
      <description>The desktop id of the camera app that the gallery and the lock screen open. Any installed app whose desktop file declares X-L16-Camera=true can be chosen (Viewfinder is org.l16linux.Camera.desktop, Nebula org.l16linux.Nebula.desktop).</description>
    </key>
    <key name="lock-screen-camera" type="b">
      <default>true</default>
      <summary>Camera on the lock screen</summary>
      <description>Whether the lock screen offers the default camera (a button on the lock screen, and the shutter button) without unlocking the phone. While it is open the phone stays locked, and the camera can only take photos and review the ones it took then.</description>
    </key>
  </schema>
</schemalist>
```

- [ ] **Step 2: Validate the schema**

Run: `cd /Users/lumey/src/l16-linux && glib-compile-schemas --strict --dry-run l16-settings && echo schema-ok`
Expected: `schema-ok`, no error output.

- [ ] **Step 3: Add the switch row**

In `l16-settings/src/main.rs`, in `camera_group()`, clone the settings handle before the `if cams.is_empty()` branch moves it into the closure, and add the row after `group.add(&row);`. Change the function so its tail reads:

```rust
    let switch_settings = settings.clone();
    // (the combo's handler below takes `settings`)
```
placed right after `let settings = gio::Settings::new(SCHEMA);`, and replace the end of the function (`group.add(&row);\n    group\n}`) with:

```rust
    group.add(&row);

    // the lock screen camera on or off (phosh reads the same key)
    let lock_row = adw::SwitchRow::builder()
        .title("Camera on the lock screen")
        .subtitle("Open the camera without unlocking the phone")
        .build();
    switch_settings.bind("lock-screen-camera", &lock_row, "active").build();
    group.add(&lock_row);
    group
}
```

- [ ] **Step 4: Build and check on the device**

Run (device builds; the Mac has no libadwaita):
```bash
cd /Users/lumey/src/l16-linux && tar --exclude=target -cf - l16-settings | ssh root@192.168.1.191 'su user -c "cd ~/build/gtree && tar xf -"' && ssh root@192.168.1.191 'su user -c "cd ~/build/gtree/l16-settings && cargo build --release --target-dir ~/build/l16-camera/target 2>&1 | tail -6"'
```
Expected: `Finished release profile`, no `error`. If `SwitchRow` or `bind` is unresolved, check `adw::prelude::*` is imported and the crate feature is `v1_5` (it already is).

Install the schema and binary and look at it:
```bash
scp -q l16-settings/org.l16linux.gschema.xml root@192.168.1.191:/usr/share/glib-2.0/schemas/ && ssh root@192.168.1.191 'glib-compile-schemas /usr/share/glib-2.0/schemas 2>&1 | grep -v -i "deprecated\|^$"; install -m755 /home/user/build/l16-camera/target/release/l16-settings /usr/local/bin/l16-settings; kill $(ps | awk "/[b]in\/l16-settings/ {print \$1}") 2>/dev/null; P0=$(ps | awk "/[l]ibexec\/phosh$/ {print \$1; exit}"); B=$(tr "\0" "\n" < /proc/$P0/environ | grep ^DBUS_SESSION_BUS_ADDRESS= | cut -d= -f2-); echo "default for the switch: $(su user -c "env XDG_RUNTIME_DIR=/run/user/10000 DBUS_SESSION_BUS_ADDRESS=$B gsettings get org.l16linux.camera lock-screen-camera")"; su user -c "env XDG_RUNTIME_DIR=/run/user/10000 WAYLAND_DISPLAY=wayland-0 DBUS_SESSION_BUS_ADDRESS=$B gtk-launch org.l16linux.Settings >/tmp/set.log 2>&1 &"; sleep 5; echo "log: [$(cat /tmp/set.log)]"'
```
Expected: `default for the switch: true`, empty log. Ask the user to look: the Camera group shows the switch "Camera on the lock screen", on. Ask them to flip it off, then check:
```bash
ssh root@192.168.1.191 'P0=$(ps | awk "/[l]ibexec\/phosh$/ {print \$1; exit}"); B=$(tr "\0" "\n" < /proc/$P0/environ | grep ^DBUS_SESSION_BUS_ADDRESS= | cut -d= -f2-); su user -c "env XDG_RUNTIME_DIR=/run/user/10000 DBUS_SESSION_BUS_ADDRESS=$B gsettings get org.l16linux.camera lock-screen-camera"'
```
Expected: `false`. Then ask them to flip it back on (`true`) and close Settings. If they can't, set it back with `gsettings set … true` and close the window yourself.

- [ ] **Step 5: Commit the source, then make the checksum on the VM**

```bash
cd /Users/lumey/src/l16-linux
git add l16-settings/org.l16linux.gschema.xml l16-settings/src/main.rs
git commit -m "l16-settings: a switch for the lock screen camera (lock-screen-camera key)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git archive HEAD | ssh lumey@192.168.1.6 'rm -rf ~/src/l16-sync && mkdir -p ~/src/l16-sync && tar xf - -C ~/src/l16-sync && cd ~/src/l16-sync && PATH=$HOME/.local/bin:$PATH bash pmaports/sync.sh >/dev/null 2>&1; cd ~/.local/var/pmbootstrap/cache_git/pmaports/main && sha512sum l16-settings/l16-settings-src.tar.gz'
```
Expected: one sha512 line. Write it into the `sha512sums` line ending `  l16-settings-src.tar.gz` in `pmaports/main/l16-settings/APKBUILD`, then:
```bash
git add pmaports/main/l16-settings/APKBUILD
git commit -m "Checksum for l16-settings with the lock screen camera switch

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
(The VM is the CI-faithful toolchain: it reproduces the author's `l16-camera` 56ffc9 and `l16-gallery` 539708 at 910a27e. Never make these checksums on the phone or the Mac.)

---

### Task 2: The phosh work tree, the patch/build script, and a baseline build

**Files:**
- Create: `tools/phosh-build.sh`
- Modify: `pmaports/temp/phosh/APKBUILD` (add the patch to `source=` and `sha512sums=`, `pkgrel=101`) in Task 3 when the first patch exists; this task builds the **unchanged** r100.

**Interfaces:**
- Produces: `~/src/phosh-work/phosh-0.55.0` (git repo, tag `base`); `tools/phosh-build.sh` (writes `pmaports/temp/phosh/lockscreen-camera.patch`, fixes its checksum, builds on the VM, prints the apk path); the baseline apk `~/phosh-r100.apk` on the Mac and `/tmp/phosh-r100.apk` on the device (rollback).

- [ ] **Step 1: Make the work tree**

```bash
mkdir -p ~/src/phosh-work && cd ~/src/phosh-work
curl -sL -o phosh-0.55.0.tar.xz https://sources.phosh.mobi/releases/phosh/phosh-0.55.0.tar.xz
echo "42bddb9a24ae3a4227732200bdce9d11a1643341ea16590dfa18098794325fabc678568f4c9cc67891f126003c3219a5087ea412005e89a1c6843ad3ce3f9d79  phosh-0.55.0.tar.xz" | shasum -a 512 -c -
rm -rf phosh-0.55.0 && tar xf phosh-0.55.0.tar.xz && cd phosh-0.55.0
for p in use-after-free-fix extend-timeout-with-pid lockscreen-compact-keypad; do patch -p1 -s < /Users/lumey/src/l16-linux/pmaports/temp/phosh/$p.patch || echo "PATCH $p FAILED"; done
git init -q && git add -A && git -c user.name=lumey -c user.email=lumey@example.invalid commit -qm base && git tag base && git log --oneline | head -1
```
Expected: `phosh-0.55.0.tar.xz: OK`, no `FAILED`, one commit `base`.

- [ ] **Step 2: Write `tools/phosh-build.sh`**

```sh
#!/bin/sh
# Make the lock screen camera patch from the phosh work tree and build phosh on the build VM.
# The work tree is a git repo (tag `base` = the tarball with our other three patches applied).
# usage: tools/phosh-build.sh        (the apk comes back to ~/phosh-build/)
set -eu
WORK=${PHOSH_WORK:-$HOME/src/phosh-work/phosh-0.55.0}
VM=${BUILD_VM:-lumey@192.168.1.6}
REPO=$(cd "$(dirname "$0")/.." && pwd)
PKG=$REPO/pmaports/temp/phosh
PATCH=$PKG/lockscreen-camera.patch

git -C "$WORK" add -A
git -C "$WORK" diff --cached base > "$PATCH"
[ -s "$PATCH" ] || { echo "no changes against base: nothing to build" >&2; exit 1; }
H=$(shasum -a 512 "$PATCH" | cut -d' ' -f1)
python3 - "$PKG/APKBUILD" "$H" <<'EOF'
import re, sys
p, h = sys.argv[1], sys.argv[2]
s = open(p).read()
if "lockscreen-camera.patch" not in s:
    sys.exit("APKBUILD doesn't list lockscreen-camera.patch yet")
s, n = re.subn(r"(?m)^[0-9a-f]{128}(  lockscreen-camera\.patch)$", h + r"\1", s)
if n != 1:
    sys.exit("no sha512 line for lockscreen-camera.patch")
open(p, "w").write(s)
EOF
scp -q "$PKG"/APKBUILD "$PKG"/*.patch "$PKG"/phosh.trigger \
  "$VM":.local/var/pmbootstrap/cache_git/pmaports/temp/phosh/
ssh "$VM" 'PATH=$HOME/.local/bin:$PATH pmbootstrap -y build --arch aarch64 phosh' 2>&1 | tail -25
mkdir -p "$HOME/phosh-build"
scp -q "$VM":.local/var/pmbootstrap/packages/v26.06/aarch64/phosh-0.55.0-*.apk "$HOME/phosh-build/"
ls -la "$HOME/phosh-build/"
```
Run: `chmod +x tools/phosh-build.sh`.

- [ ] **Step 3: Baseline build of the unchanged r100 (this warms the VM's chroot and ccache)**

The script needs a patch, so for the baseline run the build directly:
```bash
cd /Users/lumey/src/l16-linux && scp -q pmaports/temp/phosh/APKBUILD pmaports/temp/phosh/*.patch pmaports/temp/phosh/phosh.trigger lumey@192.168.1.6:.local/var/pmbootstrap/cache_git/pmaports/temp/phosh/ && ssh lumey@192.168.1.6 'PATH=$HOME/.local/bin:$PATH nohup pmbootstrap -y build --arch aarch64 phosh > ~/pmb-phosh-base.log 2>&1 < /dev/null &' ; sleep 5; echo started
```
This takes a while (the first time it installs phosh's build dependencies into the cross chroot): wait for it with
`until ! ssh lumey@192.168.1.6 'ps aux | grep -q "[p]mbootstrap -y build"'; do sleep 60; done; ssh lumey@192.168.1.6 'tail -5 ~/pmb-phosh-base.log'`.
Expected: the log ends `Finished building packages` / `DONE!`. If a dependency fails to install, record the error in the ledger as a Ruling with what you changed (the chroot is the VM's, not the repository's).

- [ ] **Step 4: Keep the baseline apk as the rollback and put a copy on the device**

```bash
mkdir -p ~/phosh-build && scp -q lumey@192.168.1.6:.local/var/pmbootstrap/packages/v26.06/aarch64/phosh-0.55.0-r100.apk ~/phosh-r100.apk && ls -la ~/phosh-r100.apk && scp -q ~/phosh-r100.apk root@192.168.1.191:/tmp/phosh-r100.apk && ssh root@192.168.1.191 'ls -la /tmp/phosh-r100.apk; apk info -v phosh'
```
Expected: the apk exists (several MB); device shows `phosh-0.55.0-r100` installed. (Note `/tmp` on the phone is a tmpfs: it is gone after a reboot. If a reboot happens, copy it again from `~/phosh-r100.apk` before installing anything.)

- [ ] **Step 5: Commit the script**

```bash
cd /Users/lumey/src/l16-linux
git add tools/phosh-build.sh
git commit -m "tools/phosh-build.sh: make the phosh patch from the work tree and build it on the VM

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The camera manager and the step-aside mechanics

**Files (all in the phosh work tree `~/src/phosh-work/phosh-0.55.0`):**
- Create: `src/dbus/org.l16linux.Shell.LockscreenCamera.xml`, `src/lockscreen-camera-manager.c`, `src/lockscreen-camera-manager.h`
- Modify: `src/dbus/meson.build`, `src/meson.build`, `src/lockscreen-manager.c`, `src/lockscreen-manager.h`, `src/shell.c`, `src/shell-priv.h`
- Modify (repo): `pmaports/temp/phosh/APKBUILD`

**Interfaces:**
- Produces:
  - `PhoshLockscreenCameraManager *phosh_lockscreen_camera_manager_new (void);` (owns the bus name)
  - `void phosh_lockscreen_camera_manager_open (PhoshLockscreenCameraManager *self);`
  - `gboolean phosh_lockscreen_camera_manager_available (PhoshLockscreenCameraManager *self);` (feature on and the default camera fit for the lock screen)
  - `void phosh_lockscreen_camera_manager_close_camera (PhoshLockscreenCameraManager *self);` (exit gesture, used in Task 5)
  - `PhoshLockscreenCameraManager *phosh_shell_get_lockscreen_camera_manager (PhoshShell *self);`
  - `void phosh_shell_set_camera_over_lock (PhoshShell *self, gboolean over);`
  - `void phosh_lockscreen_manager_set_stepped_aside (PhoshLockscreenManager *self, gboolean aside);` and `void phosh_lockscreen_manager_wakeup (PhoshLockscreenManager *self);`

- [ ] **Step 1: The D-Bus interface and its build wiring**

Create `src/dbus/org.l16linux.Shell.LockscreenCamera.xml`:
```xml
<!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
"http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
<node xmlns:doc="http://www.freedesktop.org/dbus/1.0/doc.dtd">

  <!--
      org.l16linux.Shell.LockscreenCamera:

      Opens the default camera: normally when unlocked, over the lock screen
      (the phone stays locked) when locked.
  -->
  <interface name="org.l16linux.Shell.LockscreenCamera">
    <!--
        Open:

        Takes no arguments: the camera is always the user's default camera.
    -->
    <method name="Open"/>
  </interface>
</node>
```

In `src/dbus/meson.build`, add to `dbus_server_protos` (after the `phosh-dbus-debug-control` entry):
```meson
  [
    'phosh-dbus-lockscreen-camera',
    'org.l16linux.Shell.LockscreenCamera.xml',
    'org.l16linux.Shell',
    false,
    false,
  ],
```
In `src/meson.build`, add `'lockscreen-camera-manager.h',` after `'lockscreen-bg.h',` in the headers list and `'lockscreen-camera-manager.c',` after `'lockscreen-bg.c',` in the sources list (find them with `grep -n "lockscreen-bg" src/meson.build`).

- [ ] **Step 2: The manager header**

Create `src/lockscreen-camera-manager.h`:
```c
/*
 * Copyright (C) 2026 lumey
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#pragma once

#include "phosh-dbus-lockscreen-camera.h"

#include <glib-object.h>

G_BEGIN_DECLS

#define PHOSH_TYPE_LOCKSCREEN_CAMERA_MANAGER (phosh_lockscreen_camera_manager_get_type ())

G_DECLARE_FINAL_TYPE (PhoshLockscreenCameraManager, phosh_lockscreen_camera_manager, PHOSH,
                      LOCKSCREEN_CAMERA_MANAGER, PhoshDBusLockscreenCameraSkeleton)

PhoshLockscreenCameraManager *phosh_lockscreen_camera_manager_new          (void);
void                          phosh_lockscreen_camera_manager_open         (PhoshLockscreenCameraManager *self);
gboolean                      phosh_lockscreen_camera_manager_available    (PhoshLockscreenCameraManager *self);
void                          phosh_lockscreen_camera_manager_close_camera (PhoshLockscreenCameraManager *self);

G_END_DECLS
```

- [ ] **Step 3: The manager**

Create `src/lockscreen-camera-manager.c`:
```c
/*
 * Copyright (C) 2026 lumey
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#define G_LOG_DOMAIN "phosh-lockscreen-camera-manager"

#include "phosh-config.h"

#include "lockscreen-camera-manager.h"
#include "lockscreen-manager.h"
#include "shell-priv.h"
#include "toplevel-manager.h"
#include "toplevel.h"

#include <gio/gdesktopappinfo.h>
#include <signal.h>

/**
 * PhoshLockscreenCameraManager:
 *
 * (L16 downstream) Opens the default camera: normally when the phone is unlocked, and over
 * the lock screen when it is locked. The shell stays locked the whole time; the lock screen
 * only steps aside while the camera's fullscreen window is up, and comes back the moment the
 * camera closes, loses the front, another window appears, or the screen blanks.
 * Whatever goes wrong, the result is the lock screen.
 */

#define LOCKSCREEN_CAMERA_DBUS_PATH "/org/l16linux/Shell/LockscreenCamera"
#define LOCKSCREEN_CAMERA_DBUS_NAME "org.l16linux.Shell.LockscreenCamera"

#define SCHEMA_ID "org.l16linux.camera"
#define DEFAULT_CAMERA "org.l16linux.Camera.desktop"
#define CAMERA_KEY "X-L16-Camera"
#define LOCKED_ACTION "Locked"

#define LAUNCH_TIMEOUT_SECONDS 5
#define ACTIVATE_TIMEOUT_SECONDS 2
#define CLOSE_GRACE_SECONDS 3

typedef enum {
  STATE_IDLE,       /* no lock screen camera */
  STATE_LAUNCHING,  /* started, waiting for its fullscreen window */
  STATE_OVER_LOCK,  /* its window is up and the lock screen stepped aside */
} State;

struct _PhoshLockscreenCameraManager {
  PhoshDBusLockscreenCameraSkeleton parent;

  GSettings     *settings;            /* NULL without the schema: the feature is off */
  guint          dbus_name_id;
  gboolean       connected;           /* signals of the toplevel manager and the shell */

  State          state;
  char          *app_id;              /* the camera's Wayland app id (its desktop id, no ".desktop") */
  PhoshToplevel *toplevel;            /* its window while OVER_LOCK (weak) */
  gboolean       was_activated;       /* it had the focus since stepping aside */
  GPid           pid;                 /* its process, 0 if unknown */
  guint          launch_timeout_id;
  guint          activate_timeout_id;
  guint          kill_timeout_id;
};

static void phosh_dbus_lockscreen_camera_iface_init (PhoshDBusLockscreenCameraIface *iface);

G_DEFINE_TYPE_WITH_CODE (PhoshLockscreenCameraManager, phosh_lockscreen_camera_manager,
                         PHOSH_DBUS_TYPE_LOCKSCREEN_CAMERA_SKELETON,
                         G_IMPLEMENT_INTERFACE (PHOSH_DBUS_TYPE_LOCKSCREEN_CAMERA,
                                                phosh_dbus_lockscreen_camera_iface_init))


static gboolean
lock_screen_camera_enabled (PhoshLockscreenCameraManager *self)
{
  return self->settings && g_settings_get_boolean (self->settings, "lock-screen-camera");
}


/* The user's default camera (our gsettings key), or NULL if there is none to open */
static GDesktopAppInfo *
default_camera (PhoshLockscreenCameraManager *self)
{
  g_autofree char *id = NULL;
  GDesktopAppInfo *info;

  if (self->settings)
    id = g_settings_get_string (self->settings, "default-camera");
  if (id == NULL || id[0] == '\0') {
    g_free (id);
    id = g_strdup (DEFAULT_CAMERA);
  }

  info = g_desktop_app_info_new (id);
  if (info == NULL)
    g_debug ("Default camera '%s' is not installed", id);
  return info;
}


/* Fit to be shown over the lock screen: a system-installed desktop file (not a user-writable
 * one), declaring itself a camera, with a Locked action */
static gboolean
fit_for_lock_screen (GDesktopAppInfo *info)
{
  const char *file = g_desktop_app_info_get_filename (info);
  const char * const *actions = g_desktop_app_info_list_actions (info);

  if (file == NULL ||
      !(g_str_has_prefix (file, "/usr/share/applications/") ||
        g_str_has_prefix (file, "/usr/local/share/applications/"))) {
    g_debug ("%s is not a system-installed desktop file", file ? file : "(null)");
    return FALSE;
  }
  if (!g_desktop_app_info_get_boolean (info, CAMERA_KEY)) {
    g_debug ("%s doesn't declare %s", file, CAMERA_KEY);
    return FALSE;
  }
  if (actions == NULL || !g_strv_contains (actions, LOCKED_ACTION)) {
    g_debug ("%s has no %s action", file, LOCKED_ACTION);
    return FALSE;
  }
  return TRUE;
}


static gboolean
is_camera (PhoshLockscreenCameraManager *self, PhoshToplevel *toplevel)
{
  return self->app_id && g_strcmp0 (phosh_toplevel_get_app_id (toplevel), self->app_id) == 0;
}


/* Is the camera's window still there? (looks through all toplevels) */
static gboolean
camera_window_present (PhoshLockscreenCameraManager *self)
{
  PhoshToplevelManager *manager = phosh_shell_get_toplevel_manager (phosh_shell_get_default ());
  guint num = phosh_toplevel_manager_get_num_toplevels (manager);

  for (guint i = 0; i < num; i++) {
    if (is_camera (self, phosh_toplevel_manager_get_toplevel (manager, i)))
      return TRUE;
  }
  return FALSE;
}


static gboolean
on_kill_timeout (gpointer data)
{
  PhoshLockscreenCameraManager *self = data;

  self->kill_timeout_id = 0;
  /* only if the window is still there: the pid could belong to something else by now */
  if (self->pid > 0 && camera_window_present (self)) {
    g_message ("Lock screen camera didn't close: terminating %d", self->pid);
    kill (self->pid, SIGTERM);
  }
  self->pid = 0;
  return G_SOURCE_REMOVE;
}


/* Put the lock screen back, then ask the camera to go (and make sure it does) */
static void
recover (PhoshLockscreenCameraManager *self, const char *why)
{
  PhoshShell *shell = phosh_shell_get_default ();
  gboolean was_over = self->state == STATE_OVER_LOCK;

  if (self->state == STATE_IDLE)
    return;

  g_debug ("Lock screen camera: covering again (%s)", why);
  self->state = STATE_IDLE;
  g_clear_handle_id (&self->launch_timeout_id, g_source_remove);
  g_clear_handle_id (&self->activate_timeout_id, g_source_remove);

  /* cover first: the lock screen is back before anything else happens */
  if (was_over)
    phosh_shell_set_camera_over_lock (shell, FALSE);

  if (self->toplevel) {
    g_signal_handlers_disconnect_by_data (self->toplevel, self);
    phosh_toplevel_close (self->toplevel);
    g_clear_weak_pointer (&self->toplevel);
  }
  if (self->pid > 0 && !self->kill_timeout_id)
    self->kill_timeout_id = g_timeout_add_seconds (CLOSE_GRACE_SECONDS, on_kill_timeout, self);
}


static gboolean
on_launch_timeout (gpointer data)
{
  PhoshLockscreenCameraManager *self = data;

  self->launch_timeout_id = 0;
  if (self->state == STATE_LAUNCHING)
    recover (self, "no window in time");
  return G_SOURCE_REMOVE;
}


static gboolean
on_activate_timeout (gpointer data)
{
  PhoshLockscreenCameraManager *self = data;

  self->activate_timeout_id = 0;
  if (self->state == STATE_OVER_LOCK && !self->was_activated)
    recover (self, "camera never got the focus");
  return G_SOURCE_REMOVE;
}


static void
on_toplevel_closed (PhoshLockscreenCameraManager *self)
{
  recover (self, "camera closed");
}


static void
enter_over_lock (PhoshLockscreenCameraManager *self, PhoshToplevel *toplevel)
{
  g_debug ("Lock screen camera: window up, stepping the lock screen aside");
  self->state = STATE_OVER_LOCK;
  g_clear_handle_id (&self->launch_timeout_id, g_source_remove);

  g_set_weak_pointer (&self->toplevel, toplevel);
  g_signal_connect_swapped (toplevel, "closed", G_CALLBACK (on_toplevel_closed), self);

  /* The camera gets the keyboard focus (and so "activated") only once the lock screen, which
   * holds it, is gone: it must have it within a moment, else something is wrong */
  self->was_activated = phosh_toplevel_is_activated (toplevel);
  phosh_shell_set_camera_over_lock (phosh_shell_get_default (), TRUE);
  if (!self->was_activated)
    self->activate_timeout_id = g_timeout_add_seconds (ACTIVATE_TIMEOUT_SECONDS,
                                                       on_activate_timeout, self);
}


/* A change of the camera's window (or its first appearance) */
static void
check_camera_window (PhoshLockscreenCameraManager *self, PhoshToplevel *toplevel)
{
  if (self->state == STATE_LAUNCHING) {
    if (phosh_toplevel_is_fullscreen (toplevel))
      enter_over_lock (self, toplevel);
    return;
  }

  if (phosh_toplevel_is_activated (toplevel)) {
    self->was_activated = TRUE;
    g_clear_handle_id (&self->activate_timeout_id, g_source_remove);
  }
  if (!phosh_toplevel_is_fullscreen (toplevel) ||
      (self->was_activated && !phosh_toplevel_is_activated (toplevel)))
    recover (self, "camera left the front");
}


static void
on_toplevel_added (PhoshLockscreenCameraManager *self,
                   PhoshToplevel                *toplevel,
                   PhoshToplevelManager         *manager)
{
  if (self->state == STATE_IDLE)
    return;

  if (is_camera (self, toplevel))
    check_camera_window (self, toplevel);
  else if (self->state == STATE_OVER_LOCK)
    recover (self, "another window appeared");
}


static void
on_toplevel_changed (PhoshLockscreenCameraManager *self,
                     PhoshToplevel                *toplevel,
                     PhoshToplevelManager         *manager)
{
  if (self->state == STATE_IDLE)
    return;

  if (is_camera (self, toplevel))
    check_camera_window (self, toplevel);
  else if (self->state == STATE_OVER_LOCK && phosh_toplevel_is_activated (toplevel))
    recover (self, "another window got the focus");
}


static void
on_shell_state_changed (PhoshLockscreenCameraManager *self, GParamSpec *pspec, PhoshShell *shell)
{
  if (self->state != STATE_OVER_LOCK)
    return;

  if (phosh_shell_get_blanked (shell))
    recover (self, "screen blanked");
  else if (!phosh_shell_get_locked (shell))
    recover (self, "unlocked");
}


/* Connect to the toplevels and the shell the first time they're needed (the toplevel manager
 * is created early, but not necessarily before this one) */
static void
ensure_connected (PhoshLockscreenCameraManager *self)
{
  PhoshShell *shell = phosh_shell_get_default ();
  PhoshToplevelManager *manager = phosh_shell_get_toplevel_manager (shell);

  if (self->connected)
    return;
  self->connected = TRUE;

  g_signal_connect_object (manager, "toplevel-added", G_CALLBACK (on_toplevel_added),
                           self, G_CONNECT_SWAPPED);
  g_signal_connect_object (manager, "toplevel-changed", G_CALLBACK (on_toplevel_changed),
                           self, G_CONNECT_SWAPPED);
  g_signal_connect_object (shell, "notify::shell-state", G_CALLBACK (on_shell_state_changed),
                           self, G_CONNECT_SWAPPED);
  g_signal_connect_object (shell, "notify::locked", G_CALLBACK (on_shell_state_changed),
                           self, G_CONNECT_SWAPPED);
}


static void
on_launched (GAppLaunchContext *context, GAppInfo *info, GVariant *platform_data, gpointer data)
{
  PhoshLockscreenCameraManager *self = data;
  gint32 pid = 0;

  if (platform_data && g_variant_lookup (platform_data, "pid", "i", &pid))
    self->pid = pid;
}


static void
launch_camera (PhoshLockscreenCameraManager *self, GDesktopAppInfo *info, gboolean locked)
{
  GdkAppLaunchContext *context = phosh_shell_get_app_launch_context (phosh_shell_get_default ());
  g_autoptr (GError) err = NULL;
  gulong id;

  self->pid = 0;
  id = g_signal_connect (context, "launched", G_CALLBACK (on_launched), self);

  if (locked) {
    g_desktop_app_info_launch_action (info, LOCKED_ACTION, G_APP_LAUNCH_CONTEXT (context));
  } else if (!g_app_info_launch (G_APP_INFO (info), NULL, G_APP_LAUNCH_CONTEXT (context), &err)) {
    g_warning ("Failed to launch the camera: %s", err->message);
  }

  g_signal_handler_disconnect (context, id);
}


/**
 * phosh_lockscreen_camera_manager_open:
 * @self: The manager
 *
 * Opens the default camera: a plain launch when unlocked; when locked, the lock screen camera
 * (if it's on and the camera is fit for it), else only waking the screen.
 */
void
phosh_lockscreen_camera_manager_open (PhoshLockscreenCameraManager *self)
{
  PhoshShell *shell = phosh_shell_get_default ();
  g_autoptr (GDesktopAppInfo) info = NULL;
  const char *id;

  g_return_if_fail (PHOSH_IS_LOCKSCREEN_CAMERA_MANAGER (self));

  info = default_camera (self);
  if (info == NULL) {
    g_message ("No default camera to open");
    return;
  }

  if (!phosh_shell_get_locked (shell)) {
    launch_camera (self, info, FALSE);
    return;
  }

  /* locked: at least wake the screen, so the lock screen shows */
  phosh_lockscreen_manager_wakeup (phosh_shell_get_lockscreen_manager (shell));

  if (!lock_screen_camera_enabled (self) || !fit_for_lock_screen (info))
    return;
  if (self->state != STATE_IDLE) {
    g_debug ("Lock screen camera is already open");
    return;
  }

  ensure_connected (self);

  id = g_app_info_get_id (G_APP_INFO (info));
  g_free (self->app_id);
  self->app_id = g_str_has_suffix (id, ".desktop") ? g_strndup (id, strlen (id) - 8) : g_strdup (id);
  self->state = STATE_LAUNCHING;
  self->launch_timeout_id = g_timeout_add_seconds (LAUNCH_TIMEOUT_SECONDS, on_launch_timeout, self);
  launch_camera (self, info, TRUE);
}


/**
 * phosh_lockscreen_camera_manager_available:
 * @self: The manager
 *
 * Returns: %TRUE if the lock screen camera is on and the default camera is fit for it
 */
gboolean
phosh_lockscreen_camera_manager_available (PhoshLockscreenCameraManager *self)
{
  g_autoptr (GDesktopAppInfo) info = NULL;

  g_return_val_if_fail (PHOSH_IS_LOCKSCREEN_CAMERA_MANAGER (self), FALSE);

  if (!lock_screen_camera_enabled (self))
    return FALSE;
  info = default_camera (self);
  return info != NULL && fit_for_lock_screen (info);
}


/**
 * phosh_lockscreen_camera_manager_close_camera:
 * @self: The manager
 *
 * The exit gesture: close the camera and put the lock screen back
 */
void
phosh_lockscreen_camera_manager_close_camera (PhoshLockscreenCameraManager *self)
{
  g_return_if_fail (PHOSH_IS_LOCKSCREEN_CAMERA_MANAGER (self));

  recover (self, "exit gesture");
}


static gboolean
handle_open (PhoshDBusLockscreenCamera *skeleton, GDBusMethodInvocation *invocation)
{
  phosh_lockscreen_camera_manager_open (PHOSH_LOCKSCREEN_CAMERA_MANAGER (skeleton));
  phosh_dbus_lockscreen_camera_complete_open (skeleton, invocation);
  return TRUE;
}


static void
phosh_dbus_lockscreen_camera_iface_init (PhoshDBusLockscreenCameraIface *iface)
{
  iface->handle_open = handle_open;
}


static void
on_bus_acquired (GDBusConnection *connection, const char *name, gpointer user_data)
{
  PhoshLockscreenCameraManager *self = user_data;
  g_autoptr (GError) err = NULL;

  if (!g_dbus_interface_skeleton_export (G_DBUS_INTERFACE_SKELETON (self), connection,
                                         LOCKSCREEN_CAMERA_DBUS_PATH, &err))
    g_warning ("Failed to export on %s: %s", LOCKSCREEN_CAMERA_DBUS_NAME, err->message);
}


static void
phosh_lockscreen_camera_manager_dispose (GObject *object)
{
  PhoshLockscreenCameraManager *self = PHOSH_LOCKSCREEN_CAMERA_MANAGER (object);

  g_clear_handle_id (&self->launch_timeout_id, g_source_remove);
  g_clear_handle_id (&self->activate_timeout_id, g_source_remove);
  g_clear_handle_id (&self->kill_timeout_id, g_source_remove);
  g_clear_weak_pointer (&self->toplevel);
  if (g_dbus_interface_skeleton_get_connection (G_DBUS_INTERFACE_SKELETON (self)))
    g_dbus_interface_skeleton_unexport (G_DBUS_INTERFACE_SKELETON (self));
  g_clear_handle_id (&self->dbus_name_id, g_bus_unown_name);
  g_clear_object (&self->settings);
  g_clear_pointer (&self->app_id, g_free);

  G_OBJECT_CLASS (phosh_lockscreen_camera_manager_parent_class)->dispose (object);
}


static void
phosh_lockscreen_camera_manager_class_init (PhoshLockscreenCameraManagerClass *klass)
{
  GObjectClass *object_class = G_OBJECT_CLASS (klass);

  object_class->dispose = phosh_lockscreen_camera_manager_dispose;
}


static void
phosh_lockscreen_camera_manager_init (PhoshLockscreenCameraManager *self)
{
  GSettingsSchemaSource *source = g_settings_schema_source_get_default ();
  g_autoptr (GSettingsSchema) schema = NULL;

  /* Settings::new aborts without its schema: without it the feature is simply off */
  if (source)
    schema = g_settings_schema_source_lookup (source, SCHEMA_ID, TRUE);
  if (schema)
    self->settings = g_settings_new (SCHEMA_ID);
  else
    g_message ("Schema %s isn't installed: no lock screen camera", SCHEMA_ID);

  self->dbus_name_id = g_bus_own_name (G_BUS_TYPE_SESSION,
                                       LOCKSCREEN_CAMERA_DBUS_NAME,
                                       G_BUS_NAME_OWNER_FLAGS_ALLOW_REPLACEMENT |
                                       G_BUS_NAME_OWNER_FLAGS_REPLACE,
                                       on_bus_acquired, NULL, NULL, self, NULL);
}


PhoshLockscreenCameraManager *
phosh_lockscreen_camera_manager_new (void)
{
  return g_object_new (PHOSH_TYPE_LOCKSCREEN_CAMERA_MANAGER, NULL);
}
```

- [ ] **Step 4: The lock screen manager's two helpers**

In `src/lockscreen-manager.h`, add before `G_END_DECLS`:
```c
void phosh_lockscreen_manager_set_stepped_aside (PhoshLockscreenManager *self, gboolean aside);
void phosh_lockscreen_manager_wakeup            (PhoshLockscreenManager *self);
```
In `src/lockscreen-manager.c`, add after `phosh_lockscreen_manager_set_locked ()` (find it with `grep -n "phosh_lockscreen_manager_set_locked" src/lockscreen-manager.c`):
```c
/**
 * phosh_lockscreen_manager_set_stepped_aside:
 * @self: The lock screen manager
 * @aside: %TRUE to hide the lock screen and the shields, %FALSE to show them again
 *
 * (L16 downstream) For the lock screen camera: only the surfaces step aside. The shell stays
 * locked (self->locked is never touched here), and showing the lock screen again goes back to
 * its info page, not the keypad.
 */
void
phosh_lockscreen_manager_set_stepped_aside (PhoshLockscreenManager *self, gboolean aside)
{
  g_return_if_fail (PHOSH_IS_LOCKSCREEN_MANAGER (self));

  if (self->lockscreen) {
    /* its background layer surface follows ("visible" is bound to it) */
    gtk_widget_set_visible (GTK_WIDGET (self->lockscreen), !aside);
    if (!aside)
      phosh_lockscreen_set_page (self->lockscreen, PHOSH_LOCKSCREEN_PAGE_INFO);
  }

  for (guint i = 0; self->shields && i < self->shields->len; i++)
    gtk_widget_set_visible (GTK_WIDGET (g_ptr_array_index (self->shields, i)), !aside);
}


/**
 * phosh_lockscreen_manager_wakeup:
 * @self: The lock screen manager
 *
 * Wake the screen up (the same request the lock screen makes on a touch)
 */
void
phosh_lockscreen_manager_wakeup (PhoshLockscreenManager *self)
{
  g_return_if_fail (PHOSH_IS_LOCKSCREEN_MANAGER (self));

  g_signal_emit (self, signals[WAKEUP_OUTPUTS], 0);
}
```

- [ ] **Step 5: The shell: the camera over the lock (without the exit strip yet)**

In `src/shell-priv.h` add `#include "lockscreen-camera-manager.h"` with the other manager includes, and these declarations after `phosh_shell_get_emergency_calls_manager`:
```c
PhoshLockscreenCameraManager *phosh_shell_get_lockscreen_camera_manager (PhoshShell *self);
void                          phosh_shell_set_camera_over_lock (PhoshShell *self, gboolean over);
```
In `src/shell.c`:
1. Add `#include "lockscreen-camera-manager.h"` after `#include "debug-control.h"`.
2. In the private struct, after `PhoshDebugControl          *debug_control;` add:
```c
  PhoshLockscreenCameraManager *lockscreen_camera_manager;
  PhoshDragSurfaceDragMode    saved_home_drag_mode; /* while the camera is over the lock */
  gboolean                    camera_over_lock;
```
3. In `phosh_shell_dispose` after `g_clear_object (&priv->debug_control);` add `g_clear_object (&priv->lockscreen_camera_manager);`.
4. In `setup_idle_cb`, after the `priv->screen_saver_manager = ...` statement and its `g_signal_connect_swapped (...)` block (the ones commented "Screen saver manager needs lock screen manager"), add:
```c
  priv->lockscreen_camera_manager = phosh_lockscreen_camera_manager_new ();
```
5. Add the accessor and the over-lock function after `phosh_shell_get_lockscreen_manager ()`:
```c
/**
 * phosh_shell_get_lockscreen_camera_manager:
 * @self: The shell
 *
 * Returns: (transfer none): The lock screen camera manager (NULL before startup finished)
 */
PhoshLockscreenCameraManager *
phosh_shell_get_lockscreen_camera_manager (PhoshShell *self)
{
  PhoshShellPrivate *priv;

  g_return_val_if_fail (PHOSH_IS_SHELL (self), NULL);
  priv = phosh_shell_get_instance_private (self);
  return priv->lockscreen_camera_manager;
}


/**
 * phosh_shell_set_camera_over_lock:
 * @self: The shell
 * @over: %TRUE to show the lock screen camera over the lock screen, %FALSE to put the lock
 *        screen back
 *
 * (L16 downstream) Steps the lock screen aside with the top panel hidden and the home drag
 * off, or puts everything back. The shell stays locked either way.
 */
void
phosh_shell_set_camera_over_lock (PhoshShell *self, gboolean over)
{
  PhoshShellPrivate *priv;

  g_return_if_fail (PHOSH_IS_SHELL (self));
  priv = phosh_shell_get_instance_private (self);

  if (over == priv->camera_over_lock)
    return;

  if (over) {
    g_return_if_fail (priv->locked);

    if (priv->home) {
      phosh_home_set_state (PHOSH_HOME (priv->home), PHOSH_HOME_STATE_FOLDED);
      priv->saved_home_drag_mode = phosh_drag_surface_get_drag_mode (priv->home);
      phosh_drag_surface_set_drag_mode (priv->home, PHOSH_DRAG_SURFACE_DRAG_MODE_NONE);
    }
    if (priv->top_panel)
      gtk_widget_set_visible (GTK_WIDGET (priv->top_panel), FALSE);
    priv->camera_over_lock = TRUE;
    phosh_lockscreen_manager_set_stepped_aside (priv->lockscreen_manager, TRUE);
  } else {
    /* the lock screen first */
    phosh_lockscreen_manager_set_stepped_aside (priv->lockscreen_manager, FALSE);
    priv->camera_over_lock = FALSE;
    if (priv->top_panel)
      gtk_widget_set_visible (GTK_WIDGET (priv->top_panel), TRUE);
    if (priv->home)
      phosh_drag_surface_set_drag_mode (priv->home, priv->saved_home_drag_mode);
  }
}
```

- [ ] **Step 6: List the patch in the APKBUILD and build**

In `pmaports/temp/phosh/APKBUILD`: set `pkgrel=101`; add the line `lockscreen-camera.patch` after `lockscreen-compact-keypad.patch` in `source=`; add a `sha512sums` line `0000…(128 zeros)  lockscreen-camera.patch` after the `lockscreen-compact-keypad.patch` one (the script replaces it); update the comment at the top of the file to mention the lock screen camera patch.

Run: `cd /Users/lumey/src/l16-linux && tools/phosh-build.sh 2>&1 | tail -30`
Expected: the build finishes with `phosh-0.55.0-r101.apk` listed in `~/phosh-build/`. A compile error is a defect in the code of the previous steps: fix it in the work tree against the real phosh headers (e.g. a misremembered getter name), re-run, and record each non-trivial fix as `Ruling:`. Warnings about unused variables are fine.

- [ ] **Step 7: Prepare the device test (the temporary `Locked` action on Nebula), then ask the user**

Put a temporary action on the manually-installed Nebula desktop entry (`/usr/share/applications/org.l16linux.Nebula.desktop`, owned by no package) that starts Nebula normally: Nebula is fullscreen already, so it stands in for the locked camera until plan C:
```bash
ssh root@192.168.1.191 'cp /usr/share/applications/org.l16linux.Nebula.desktop /root/Nebula.desktop.orig && printf "Actions=Locked;\n\n[Desktop Action Locked]\nName=Locked camera\nExec=nebula\n" >> /usr/share/applications/org.l16linux.Nebula.desktop && cat /usr/share/applications/org.l16linux.Nebula.desktop'
```
Expected: the file ends with the `[Desktop Action Locked]` group, `X-L16-Camera=true` present. (Plan C replaces this with the real `nebula --locked`; Task 7 here restores the original.)

Then **ask the user** (they will need their PIN): "I'm going to install a test phosh and restart your session; you'll be taken to the login screen. OK?" Only after a yes:
```bash
scp -q ~/phosh-build/phosh-0.55.0-r101.apk root@192.168.1.191:/tmp/ && ssh root@192.168.1.191 'apk add --allow-untrusted /tmp/phosh-0.55.0-r101.apk 2>&1 | tail -3; apk info -v phosh; rc-service greetd restart 2>&1 | tail -2'
```
Expected: `phosh-0.55.0-r101` installed; greetd restarts. The user logs in again. If the phone never comes back to a login screen: `apk add --allow-untrusted /tmp/phosh-r100.apk && rc-service greetd restart` (rollback), and stop to report.

- [ ] **Step 8: First device test of the mechanics (a screenshot proves what is on screen)**

Install `grim` once: `ssh root@192.168.1.191 'apk add grim 2>&1 | tail -1'`. Set up a helper for the session environment (the user session is the one whose bus address is in phosh's environment; re-read it after every session restart):
```bash
S='P0=$(ps | awk "/[l]ibexec\/phosh$/ {print \$1; exit}"); B=$(tr "\0" "\n" < /proc/$P0/environ | grep ^DBUS_SESSION_BUS_ADDRESS= | cut -d= -f2-); E="XDG_RUNTIME_DIR=/run/user/10000 WAYLAND_DISPLAY=wayland-0 DBUS_SESSION_BUS_ADDRESS=$B"'
```
Check the service is on the bus, and the unlocked path:
```bash
ssh root@192.168.1.191 "$S; su user -c \"env \$E gdbus introspect --session --dest org.l16linux.Shell.LockscreenCamera --object-path /org/l16linux/Shell/LockscreenCamera | head -8\""
```
Expected: an interface `org.l16linux.Shell.LockscreenCamera` with `methods: Open();`. If the name isn't owned, read phosh's log for the reason (`tail -40 ~user/.cache/phosh.log` or `logread`); a missing generated header is a meson wiring defect in Step 1.

Now the locked path. Lock, open, screenshot, restore:
```bash
ssh root@192.168.1.191 "$S; su user -c \"env \$E gdbus call --session --dest org.gnome.ScreenSaver --object-path /org/gnome/ScreenSaver --method org.gnome.ScreenSaver.Lock\"; sleep 3; su user -c \"env \$E grim /tmp/lock0.png\"; su user -c \"env \$E gdbus call --session --dest org.l16linux.Shell.LockscreenCamera --object-path /org/l16linux/Shell/LockscreenCamera --method org.l16linux.Shell.LockscreenCamera.Open\"; sleep 8; su user -c \"env \$E grim /tmp/lock1.png\"; ps | grep -c '[b]in/nebula'" && scp -q root@192.168.1.191:/tmp/lock0.png root@192.168.1.191:/tmp/lock1.png /tmp/
```
View `/tmp/lock0.png` (Read it): expected the lock screen (clock, "Slide up to unlock"). View `/tmp/lock1.png`: expected **Nebula's camera UI and no lock screen, no top panel**. `ps` count `1`. Check the shell is **still locked**: `gdbus call --session --dest org.gnome.ScreenSaver --object-path /org/gnome/ScreenSaver --method org.gnome.ScreenSaver.GetActive` must print `(true,)`.

- [ ] **Step 9: Re-cover paths that need no tool: close the camera, then confirm everything is back**

Close Nebula the way the app does (SIGTERM, as the earlier tests did) and screenshot:
```bash
ssh root@192.168.1.191 "$S; PID=\$(ps | awk '/[b]in\/nebula/ {print \$1; exit}'); su user -c \"kill \$PID\"; sleep 4; su user -c \"env \$E grim /tmp/lock2.png\"; su user -c \"env \$E gdbus call --session --dest org.gnome.ScreenSaver --object-path /org/gnome/ScreenSaver --method org.gnome.ScreenSaver.GetActive\"" && scp -q root@192.168.1.191:/tmp/lock2.png /tmp/
```
Expected: `/tmp/lock2.png` is the lock screen again (info page: clock, not the keypad) and `GetActive` prints `(true,)`. Now ask the user to unlock with their PIN and confirm the **top bar is back and the home bar swipe works**: that is the restore of `top_panel` visibility and the home drag mode (Review Focus 5). If either is missing, that is a defect in `phosh_shell_set_camera_over_lock (FALSE)`; fix before continuing.

- [ ] **Step 10: The 5 s watch and spamming `Open()` (Review Focus 2 and 3)**

With the phone locked again (lock it as in Step 8), call `Open()` **three times in a row** and screenshot:
```bash
ssh root@192.168.1.191 "$S; su user -c \"env \$E gdbus call --session --dest org.gnome.ScreenSaver --object-path /org/gnome/ScreenSaver --method org.gnome.ScreenSaver.Lock\"; sleep 2; for i in 1 2 3; do su user -c \"env \$E gdbus call --session --dest org.l16linux.Shell.LockscreenCamera --object-path /org/l16linux/Shell/LockscreenCamera --method org.l16linux.Shell.LockscreenCamera.Open\" >/dev/null; done; sleep 8; ps | grep -c '[b]in/nebula'; su user -c \"env \$E grim /tmp/lock3.png\"" && scp -q root@192.168.1.191:/tmp/lock3.png /tmp/
```
Expected: exactly one `nebula` process (`1`), and the camera over the lock (as in `lock1.png`). Then close it as in Step 9. Next, a camera that never shows a window: swap the temporary action for one that starts a process with no window, lock, `Open()`, wait 8 s, screenshot:
```bash
ssh root@192.168.1.191 'cp /root/Nebula.desktop.orig /usr/share/applications/org.l16linux.Nebula.desktop && printf "Actions=Locked;\n\n[Desktop Action Locked]\nName=Locked camera\nExec=sleep 30\n" >> /usr/share/applications/org.l16linux.Nebula.desktop'
ssh root@192.168.1.191 "$S; su user -c \"env \$E gdbus call --session --dest org.gnome.ScreenSaver --object-path /org/gnome/ScreenSaver --method org.gnome.ScreenSaver.Lock\"; sleep 2; su user -c \"env \$E gdbus call --session --dest org.l16linux.Shell.LockscreenCamera --object-path /org/l16linux/Shell/LockscreenCamera --method org.l16linux.Shell.LockscreenCamera.Open\" >/dev/null; sleep 8; su user -c \"env \$E grim /tmp/lock4.png\"" && scp -q root@192.168.1.191:/tmp/lock4.png /tmp/
```
**Expected the lock screen** (never the camera, no stuck state). Then put the working test action back (the one with `Exec=nebula`, as in Step 7) and check a later `Open()` still opens the camera over the lock (Review Focus 2). Record the outcome in the ledger.

- [ ] **Step 11: Commit the work in the repository**

The patch file and APKBUILD are produced by `tools/phosh-build.sh`; commit them:
```bash
cd /Users/lumey/src/l16-linux
git add pmaports/temp/phosh/APKBUILD pmaports/temp/phosh/lockscreen-camera.patch
git commit -m "phosh: the lock screen camera manager and stepping the lock screen aside (phosh r101)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The leak tests: fake touches, screenshots, and the scenario list

**Files:**
- Create: `tools/lockcam-touch.py` (fake multi-touch gestures through `/dev/uinput`)
- Create: `tools/lockcam-test.sh` (the scenarios, run on the Mac against the device)

**Interfaces:**
- Consumes: Task 3's phosh on the device and its `Open()`.
- Produces: `tools/lockcam-touch.py edges|swipe X1 Y1 X2 Y2 [ms]|tap X Y|longpress X Y [ms]` (coordinates 0–1000 on both axes of the display as it is held); `tools/lockcam-test.sh` prints the scenario screenshots into `/tmp/lockcam/`.

- [ ] **Step 1: Write the touch tool**

Create `tools/lockcam-touch.py`:
```python
#!/usr/bin/env python3
"""Fake touch gestures on a uinput touchscreen, to test the lock screen camera.

Run on the phone as root:
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
        os.write(self.fd, struct.pack("<llHHi", int(now), int((now % 1) * 1e6), t, c, v))

    def syn(self):
        self.ev(EV_SYN, 0, 0)

    def down(self, x, y):
        self.tid += 1
        self.ev(EV_ABS, ABS_MT_SLOT, 0)
        self.ev(EV_ABS, ABS_MT_TRACKING_ID, self.tid)
        self.move(x, y)
        self.ev(EV_KEY, BTN_TOUCH, 1)
        self.syn()

    def move(self, x, y):
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
```
Run: `chmod +x tools/lockcam-touch.py && python3 -c "import ast,sys; ast.parse(open('tools/lockcam-touch.py').read()); print('syntax ok')"`
Expected: `syntax ok`.

- [ ] **Step 2: Write the scenario runner**

Create `tools/lockcam-test.sh`:
```sh
#!/bin/sh
# Lock screen camera: leak tests against the phone (run on the Mac).
# For each scenario it lights the lock screen camera, throws touches at the screen, takes a
# whole-display screenshot with grim, and saves it in /tmp/lockcam/ for a person to look at:
# a pass is a screenshot that shows only the camera (or only the lock screen where noted).
# usage: tools/lockcam-test.sh [scenario...]   (default: all)
set -eu
DEV=${DEVICE:-root@192.168.1.191}
OUT=/tmp/lockcam
mkdir -p "$OUT"
TOUCH=$(dirname "$0")/lockcam-touch.py
scp -q "$TOUCH" "$DEV":/tmp/lockcam-touch.py

# the user session's environment (re-read: it changes with every session restart)
sess='P0=$(ps | awk "/[l]ibexec\/phosh$/ {print \$1; exit}"); B=$(tr "\0" "\n" < /proc/$P0/environ | grep ^DBUS_SESSION_BUS_ADDRESS= | cut -d= -f2-); E="XDG_RUNTIME_DIR=/run/user/10000 WAYLAND_DISPLAY=wayland-0 DBUS_SESSION_BUS_ADDRESS=$B"'
as_user() { ssh "$DEV" "$sess; su user -c \"env \$E $1\""; }
bus='gdbus call --session'
lock()  { as_user "$bus --dest org.gnome.ScreenSaver --object-path /org/gnome/ScreenSaver --method org.gnome.ScreenSaver.Lock" >/dev/null; sleep 2; }
open_cam() { as_user "$bus --dest org.l16linux.Shell.LockscreenCamera --object-path /org/l16linux/Shell/LockscreenCamera --method org.l16linux.Shell.LockscreenCamera.Open" >/dev/null; sleep 6; }
shot()  { as_user "grim /tmp/lc.png"; scp -q "$DEV":/tmp/lc.png "$OUT/$1.png"; echo "  saved $OUT/$1.png  ($2)"; }
active(){ as_user "$bus --dest org.gnome.ScreenSaver --object-path /org/gnome/ScreenSaver --method org.gnome.ScreenSaver.GetActive"; }
poke()  { ssh "$DEV" "python3 /tmp/lockcam-touch.py $*"; sleep 1.5; }
camera_up() { lock; open_cam; }
close_cam() { ssh "$DEV" 'kill $(ps | awk "/[b]in\/nebula/ {print \$1}") 2>/dev/null; sleep 4' || true; }

run() { case " ${SCENARIOS:-all} " in *" all "*|*" $1 "*) echo "== $1: $2"; "$1";; esac; }
SCENARIOS="${*:-all}"

edges()    { camera_up; poke edges; shot edges "before the exit strip exists (Task 4): camera only after 4 edge swipes. With it (Task 5+): the last swipe, up from the bottom, exits: LOCK SCREEN"; echo "  locked: $(active)"; close_cam; }
corners()  { camera_up; poke corners; shot corners "camera only"; close_cam; }
longpress(){ camera_up; poke longpress 500 990; poke longpress 500 10; shot longpress "camera only: no menu or keyboard"; close_cam; }
power()    { camera_up; as_user "$bus --dest org.gnome.ScreenSaver --object-path /org/gnome/ScreenSaver --method org.gnome.ScreenSaver.SetActive true" >/dev/null; sleep 3; shot power-blank "screen blank"; as_user "$bus --dest org.gnome.ScreenSaver --object-path /org/gnome/ScreenSaver --method org.gnome.ScreenSaver.SetActive false" >/dev/null; sleep 3; shot power-wake "LOCK SCREEN, not the camera"; echo "  locked: $(active)"; close_cam; }
selfclose(){ camera_up; close_cam; shot selfclose "LOCK SCREEN straight away"; echo "  locked: $(active)"; }
behind()   { # another app open behind: it must never show
  as_user "gtk-launch org.l16linux.Settings >/dev/null 2>&1 &"; sleep 4
  camera_up; poke edges; shot behind "Settings must not show (camera only, or the lock screen after the bottom swipe)"; close_cam; shot behind-closed "LOCK SCREEN: Settings must not show"
  ssh "$DEV" 'kill $(ps | awk "/[b]in\/l16-settings/ {print \$1}") 2>/dev/null' || true; }
other()    { camera_up; as_user "gtk-launch org.l16linux.Gallery >/dev/null 2>&1 &"; sleep 4; shot other-window "LOCK SCREEN: a new window ends the camera"; echo "  locked: $(active)"
  ssh "$DEV" 'kill $(ps | awk "/[b]in\/l16-gallery/ {print \$1}") 2>/dev/null' || true; close_cam; }
switchoff(){ as_user "gsettings set org.l16linux.camera lock-screen-camera false"; lock; open_cam; shot switch-off "LOCK SCREEN: the switch is off"; as_user "gsettings set org.l16linux.camera lock-screen-camera true"; }

run edges "four edge swipes with the camera over the lock"
run corners "corner taps"
run longpress "long presses on the bottom and top edges"
run power "the power button blanks, then wakes"
run selfclose "the camera closes itself"
run behind "an app open behind the camera"
run other "another window opens over the camera"
run switchoff "the switch is off"
echo "done: look at the screenshots in $OUT"
```
Run: `chmod +x tools/lockcam-test.sh && sh -n tools/lockcam-test.sh && echo syntax-ok`
Expected: `syntax-ok`.

- [ ] **Step 3: Run the suite against Task 3's phosh**

`ssh root@192.168.1.191 'apk add python3 2>&1 | tail -1; ls /dev/uinput'` must show the device node (if not: `modprobe uinput`). Then:
Run: `cd /Users/lumey/src/l16-linux && tools/lockcam-test.sh 2>&1 | tail -40`
Expected: the lines `saved /tmp/lockcam/….png` for every scenario and `locked: (true,)` after each that prints it. **Look at every screenshot** (Read each PNG):
- `edges`, `corners`, `longpress`, `behind`: Nebula's UI only: **no** overview, app grid, shade, quick settings, power menu, keyboard, top bar, home bar or other window.
- `power-wake`, `selfclose`, `behind-closed`, `other-window`, `switch-off`: the lock screen.

- [ ] **Step 4: Fix every leak the screenshots show**

For each screenshot that shows something it should not, write the failing scenario into the ledger, find the cause in the phosh source (the surface that appeared), and fix it in the work tree: hide or disable that surface in `phosh_shell_set_camera_over_lock ()` (as done for the top panel and the home drag) or re-cover in the manager, whichever the spec's invariants require; rebuild with `tools/phosh-build.sh`, ask the user for the session restart, and re-run **only the failing scenario** until its screenshot is right, then the whole suite once. Record each as `Ruling:` with what leaked and what closed it. A leak that can't be closed with the design in the spec is a stop: report it, because the spec's invariants then need revisiting.

- [ ] **Step 5: Commit**

```bash
cd /Users/lumey/src/l16-linux
git add tools/lockcam-touch.py tools/lockcam-test.sh pmaports/temp/phosh/lockscreen-camera.patch pmaports/temp/phosh/APKBUILD
git commit -m "tools: fake touches and the lock screen camera's leak scenarios (and the fixes they found)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The exit strip (swipe up closes the camera and re-locks)

**Files (phosh work tree):**
- Create: `src/exit-strip.c`, `src/exit-strip.h`
- Modify: `src/meson.build`, `src/shell.c`, `src/stylesheet/common.css`
- Modify (repo): `tools/lockcam-test.sh` (add the `exit` scenario)

**Interfaces:**
- Consumes: `phosh_lockscreen_camera_manager_close_camera ()` (Task 3), `phosh_shell_set_camera_over_lock ()` (Task 3).
- Produces: `GtkWidget *phosh_exit_strip_new (struct zwlr_layer_shell_v1 *layer_shell, struct wl_output *wl_output);` and the signal `exit-requested` on `PhoshExitStrip`.

- [ ] **Step 1: The exit strip surface**

Create `src/exit-strip.h`:
```c
/*
 * Copyright (C) 2026 lumey
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#pragma once

#include "layersurface.h"

G_BEGIN_DECLS

#define PHOSH_TYPE_EXIT_STRIP (phosh_exit_strip_get_type ())

G_DECLARE_FINAL_TYPE (PhoshExitStrip, phosh_exit_strip, PHOSH, EXIT_STRIP, PhoshLayerSurface)

GtkWidget *phosh_exit_strip_new (struct zwlr_layer_shell_v1 *layer_shell,
                                 struct wl_output           *wl_output);

G_END_DECLS
```
Create `src/exit-strip.c`:
```c
/*
 * Copyright (C) 2026 lumey
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#define G_LOG_DOMAIN "phosh-exit-strip"

#include "phosh-config.h"

#include "exit-strip.h"

#define EXIT_STRIP_HEIGHT 40   /* logical px: more than the home bar it covers */
#define EXIT_SWIPE_MIN 30      /* logical px upward */

/**
 * PhoshExitStrip:
 *
 * (L16 downstream) A thin overlay surface along the bottom edge while the lock screen camera is
 * up: it takes the place of the home bar, so a swipe up there means "leave the camera" (and
 * so lock again) instead of opening the overview. Emits ::exit-requested.
 */
enum {
  EXIT_REQUESTED,
  N_SIGNALS
};
static guint signals[N_SIGNALS] = { 0 };

struct _PhoshExitStrip {
  PhoshLayerSurface parent;

  GtkGesture       *drag;
};

G_DEFINE_TYPE (PhoshExitStrip, phosh_exit_strip, PHOSH_TYPE_LAYER_SURFACE)


static void
on_drag_end (PhoshExitStrip *self, double offset_x, double offset_y, GtkGestureDrag *gesture)
{
  if (offset_y < -EXIT_SWIPE_MIN)
    g_signal_emit (self, signals[EXIT_REQUESTED], 0);
}


static void
phosh_exit_strip_constructed (GObject *object)
{
  PhoshExitStrip *self = PHOSH_EXIT_STRIP (object);
  GtkWidget *handle;

  G_OBJECT_CLASS (phosh_exit_strip_parent_class)->constructed (object);

  gtk_style_context_add_class (gtk_widget_get_style_context (GTK_WIDGET (self)),
                               "phosh-exit-strip");

  handle = gtk_box_new (GTK_ORIENTATION_HORIZONTAL, 0);
  gtk_widget_set_halign (handle, GTK_ALIGN_CENTER);
  gtk_widget_set_valign (handle, GTK_ALIGN_CENTER);
  gtk_style_context_add_class (gtk_widget_get_style_context (handle), "phosh-exit-strip-handle");
  gtk_widget_set_visible (handle, TRUE);
  gtk_container_add (GTK_CONTAINER (self), handle);

  self->drag = gtk_gesture_drag_new (GTK_WIDGET (self));
  gtk_gesture_single_set_touch_only (GTK_GESTURE_SINGLE (self->drag), FALSE);
  g_signal_connect_swapped (self->drag, "drag-end", G_CALLBACK (on_drag_end), self);
}


static void
phosh_exit_strip_finalize (GObject *object)
{
  PhoshExitStrip *self = PHOSH_EXIT_STRIP (object);

  g_clear_object (&self->drag);

  G_OBJECT_CLASS (phosh_exit_strip_parent_class)->finalize (object);
}


static void
phosh_exit_strip_class_init (PhoshExitStripClass *klass)
{
  GObjectClass *object_class = G_OBJECT_CLASS (klass);

  object_class->constructed = phosh_exit_strip_constructed;
  object_class->finalize = phosh_exit_strip_finalize;

  /**
   * PhoshExitStrip::exit-requested:
   *
   * The user swiped up on the strip
   */
  signals[EXIT_REQUESTED] = g_signal_new ("exit-requested",
                                          G_TYPE_FROM_CLASS (klass),
                                          G_SIGNAL_RUN_LAST,
                                          0, NULL, NULL, NULL,
                                          G_TYPE_NONE, 0);
}


static void
phosh_exit_strip_init (PhoshExitStrip *self)
{
}


GtkWidget *
phosh_exit_strip_new (struct zwlr_layer_shell_v1 *layer_shell, struct wl_output *wl_output)
{
  return g_object_new (PHOSH_TYPE_EXIT_STRIP,
                       "layer-shell", layer_shell,
                       "wl-output", wl_output,
                       "anchor", ZWLR_LAYER_SURFACE_V1_ANCHOR_BOTTOM |
                                 ZWLR_LAYER_SURFACE_V1_ANCHOR_LEFT |
                                 ZWLR_LAYER_SURFACE_V1_ANCHOR_RIGHT,
                       "layer", ZWLR_LAYER_SHELL_V1_LAYER_OVERLAY,
                       "kbd-interactivity", FALSE,
                       "exclusive-zone", -1,
                       "height", EXIT_STRIP_HEIGHT,
                       "namespace", "phosh exit strip",
                       NULL);
}
```
In `src/meson.build` add `'exit-strip.h',` and `'exit-strip.c',` to the header and source lists (after `'emergency-menu.h'` / `'emergency-menu.c'`, keeping alphabetical order).

- [ ] **Step 2: The strip's look**

Append to `src/stylesheet/common.css`:
```css
/* L16: the exit strip of the lock screen camera */
.phosh-exit-strip {
  background-color: transparent;
}

.phosh-exit-strip-handle {
  min-width: 120px;
  min-height: 4px;
  border-radius: 2px;
  background-color: rgba(255, 255, 255, 0.6);
  margin-top: 12px;
  margin-bottom: 12px;
}
```

- [ ] **Step 3: Show it while the camera is over the lock**

In `src/shell.c`: add `#include "exit-strip.h"` after `#include "lockscreen-camera-manager.h"`; add `PhoshExitStrip *exit_strip;` to the private struct next to `camera_over_lock`; add this callback before `phosh_shell_set_camera_over_lock ()`:
```c
static void
on_exit_requested (PhoshShell *self)
{
  PhoshShellPrivate *priv = phosh_shell_get_instance_private (self);

  g_debug ("Lock screen camera: exit swipe");
  phosh_lockscreen_camera_manager_close_camera (priv->lockscreen_camera_manager);
}
```
and in `phosh_shell_set_camera_over_lock ()`: in the `over` branch, **before** `priv->camera_over_lock = TRUE;`, add:
```c
    priv->exit_strip = PHOSH_EXIT_STRIP (phosh_exit_strip_new (
                                           phosh_wayland_get_zwlr_layer_shell_v1 (phosh_wayland_get_default ()),
                                           priv->primary_monitor->wl_output));
    g_signal_connect_swapped (priv->exit_strip, "exit-requested", G_CALLBACK (on_exit_requested), self);
    gtk_widget_set_visible (GTK_WIDGET (priv->exit_strip), TRUE);
```
and in the other branch, **after** `phosh_lockscreen_manager_set_stepped_aside (priv->lockscreen_manager, FALSE);`, add:
```c
    g_clear_pointer (&priv->exit_strip, phosh_cp_widget_destroy);
```

- [ ] **Step 4: Add the `exit` scenario and build**

Append this function and `run` line to `tools/lockcam-test.sh` (before `echo "done: …"`):
```sh
exitswipe(){ camera_up; shot exit-before "camera over the lock, handle at the bottom"; poke swipe 500 995 500 700 250; sleep 2; shot exit-after "LOCK SCREEN straight after the swipe"; echo "  locked: $(active)"; echo "  camera processes still running: $(ssh "$DEV" 'ps | grep -c "[b]in/nebula"')"; sleep 4; echo "  after the grace: $(ssh "$DEV" 'ps | grep -c "[b]in/nebula"')"; }
run exitswipe "the exit swipe from the bottom edge"
```
Run: `cd /Users/lumey/src/l16-linux && sh -n tools/lockcam-test.sh && tools/phosh-build.sh 2>&1 | tail -15`
Expected: `syntax ok` (no output) and a new `phosh-0.55.0-r101.apk` in `~/phosh-build/`. Fix compile errors in the work tree; record each as `Ruling:`.

- [ ] **Step 5: Deploy (ask the user first) and test the exit**

Ask the user for the session restart (PIN), then:
```bash
scp -q ~/phosh-build/phosh-0.55.0-r101.apk root@192.168.1.191:/tmp/ && ssh root@192.168.1.191 'apk add --allow-untrusted /tmp/phosh-0.55.0-r101.apk 2>&1 | tail -2; rc-service greetd restart 2>&1 | tail -1'
```
After the user logs in: `tools/lockcam-test.sh exitswipe 2>&1 | tail -10`.
Expected: `exit-before.png` shows Nebula with a thin white pill centred along the bottom; `exit-after.png` is the **lock screen**; `locked: (true,)`; `camera processes still running` may be `1` at that moment (the camera is asked to close), and `after the grace` is `0`: the window closed or phosh ended it after 3 s. If the swipe does nothing, look at the touch tool first (`lockcam-touch.py tap 500 985` on the strip's area) before suspecting the gesture code; and check that the strip is mapped with `gdbus`-free means: grim's screenshot shows the pill.
Then re-run the full suite once (`tools/lockcam-test.sh`) and look at every screenshot again: the strip must not have opened any new way out. `edges` swipes top, left and right first and the bottom last: the camera must survive the first three, and the last one now **exits** to the lock screen (the scenario's comment says so).

- [ ] **Step 6: Commit**

```bash
cd /Users/lumey/src/l16-linux
git add tools/lockcam-test.sh pmaports/temp/phosh/lockscreen-camera.patch pmaports/temp/phosh/APKBUILD
git commit -m "phosh: the exit strip: a swipe up from the bottom edge closes the lock screen camera

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
Note for plan C's tests: with a shot in flight, the exit swipe only closes the window; the camera app must keep saving (its sleep inhibitor) before exiting.

---

### Task 6: The lock screen's camera button

**Files (phosh work tree):**
- Modify: `src/ui/lockscreen.ui`, `src/lockscreen.c`, `src/stylesheet/common.css`

**Interfaces:**
- Consumes: `phosh_shell_get_lockscreen_camera_manager ()`, `phosh_lockscreen_camera_manager_open ()`, `phosh_lockscreen_camera_manager_available ()` (Task 3).
- Produces: a camera button at the bottom-right of the lock screen's info page, shown only when the lock screen camera is on and the default camera is fit for it.

- [ ] **Step 1: The button in the UI file**

In `src/ui/lockscreen.ui`, inside `box_info`, right after the `</child>` that closes the first child (the GtkBox with the arrow and "Slide up to unlock", whose `<packing>` is `pack-type end`) and before `<child type="center">`, add:
```xml
                <child>
                  <object class="GtkButton" id="btn_camera">
                    <property name="visible">0</property>
                    <property name="halign">end</property>
                    <property name="valign">end</property>
                    <property name="margin">12</property>
                    <signal name="clicked" handler="on_camera_clicked" swapped="yes"/>
                    <child>
                      <object class="GtkImage">
                        <property name="visible">1</property>
                        <property name="icon-name">camera-photo-symbolic</property>
                        <property name="pixel-size">32</property>
                      </object>
                    </child>
                    <style>
                      <class name="phosh-lockscreen-camera"/>
                      <class name="circular"/>
                    </style>
                    <child internal-child="accessible">
                      <object class="AtkObject">
                        <property name="AtkObject::accessible-name" translatable="yes">Camera</property>
                      </object>
                    </child>
                  </object>
                  <packing>
                    <property name="pack-type">end</property>
                  </packing>
                </child>
```

- [ ] **Step 2: The code in `lockscreen.c`**

1. Add `#include "lockscreen-camera-manager.h"` with the other includes (`grep -n '^#include' src/lockscreen.c`).
2. In the `PhoshLockscreenPrivate` struct, after `GtkWidget *btn_keyboard;`, add `GtkWidget *btn_camera;`.
3. Add the handler before `phosh_lockscreen_map ()`:
```c
static void
on_camera_clicked (PhoshLockscreen *self)
{
  PhoshLockscreenCameraManager *manager;

  manager = phosh_shell_get_lockscreen_camera_manager (phosh_shell_get_default ());
  if (manager)
    phosh_lockscreen_camera_manager_open (manager);
}
```
4. In `phosh_lockscreen_map ()`, after the `set_stacked_below` call, add:
```c
  /* the camera button only when the lock screen camera is on and the camera fit for it */
  {
    PhoshLockscreenCameraManager *manager;

    manager = phosh_shell_get_lockscreen_camera_manager (phosh_shell_get_default ());
    gtk_widget_set_visible (priv->btn_camera,
                            manager && phosh_lockscreen_camera_manager_available (manager));
  }
```
5. In the class init, after `gtk_widget_class_bind_template_child_private (widget_class, PhoshLockscreen, btn_keyboard);` add:
```c
  gtk_widget_class_bind_template_child_private (widget_class, PhoshLockscreen, btn_camera);
  gtk_widget_class_bind_template_callback (widget_class, on_camera_clicked);
```
(`phosh_shell_get_lockscreen_camera_manager` is declared in `shell-priv.h`: make sure `lockscreen.c` includes it: `grep -n 'shell-priv.h' src/lockscreen.c`.)

- [ ] **Step 3: The button's look**

Append to `src/stylesheet/common.css`:
```css
/* L16: the camera button on the lock screen */
.phosh-lockscreen-camera {
  min-width: 56px;
  min-height: 56px;
  padding: 0;
  border-radius: 28px;
}
```

- [ ] **Step 4: Build, deploy (ask the user first), and test**

Run: `cd /Users/lumey/src/l16-linux && tools/phosh-build.sh 2>&1 | tail -15`
Expected: a new r101 apk; fix compile or template errors (a template error shows at runtime in phosh's log: check `ssh root@192.168.1.191 'logread | tail -30'` after the restart).
Ask the user for the session restart, install as in Task 5 Step 5, then lock the phone and look:
```bash
ssh root@192.168.1.191 "$S; su user -c \"env \$E gdbus call --session --dest org.gnome.ScreenSaver --object-path /org/gnome/ScreenSaver --method org.gnome.ScreenSaver.Lock\"; sleep 3; su user -c \"env \$E grim /tmp/btn.png\"" && scp -q root@192.168.1.191:/tmp/btn.png /tmp/btn.png
```
(`$S` as defined in Task 3 Step 8.) View it: expected a round camera button in the bottom-right of the lock screen. Ask the user to **tap the button**: the camera opens over the lock; swipe up from the bottom (the pill) and the lock screen returns. Then in Settings turn the switch off, lock again, and check the button is **gone** (it is evaluated each time the lock screen is mapped). Restore the switch to on.

- [ ] **Step 5: Commit**

```bash
cd /Users/lumey/src/l16-linux
git add pmaports/temp/phosh/lockscreen-camera.patch pmaports/temp/phosh/APKBUILD
git commit -m "phosh: a camera button on the lock screen

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Finish: restore the test action, the full suite, and the package

**Files:**
- Modify: `pmaports/temp/phosh/APKBUILD` (header comment), already carries the patch and `pkgrel=101`
- Device: restore `/usr/share/applications/org.l16linux.Nebula.desktop`

**Interfaces:**
- Consumes: everything above.
- Produces: `lockscreen-camera.patch` + APKBUILD ready for CI (phosh r101); a device running r101 with the original Nebula desktop file.

- [ ] **Step 1: Restore Nebula's desktop file on the device**

```bash
ssh root@192.168.1.191 'cp /root/Nebula.desktop.orig /usr/share/applications/org.l16linux.Nebula.desktop && grep -c "Desktop Action Locked" /usr/share/applications/org.l16linux.Nebula.desktop; grep -c "X-L16-Camera=true" /usr/share/applications/org.l16linux.Nebula.desktop'
```
Expected: `0` then `1` (no test action, the camera key kept). Plan C adds the real `Locked` action. (Until then the lock screen camera is inert: `fit_for_lock_screen ()` finds no action, so the button is hidden and `Open()` only wakes the screen. That is the intended state between plans B and C.)

- [ ] **Step 2: The final full suite on the final build (with a test action again for the run)**

The suite needs a camera with a `Locked` action; re-add the temporary one for the run, then restore (Step 1 again):
```bash
ssh root@192.168.1.191 'printf "Actions=Locked;\n\n[Desktop Action Locked]\nName=Locked camera\nExec=nebula\n" >> /usr/share/applications/org.l16linux.Nebula.desktop'
cd /Users/lumey/src/l16-linux && tools/lockcam-test.sh 2>&1 | tail -40
```
Expected: every scenario's screenshot is as described in Task 4 Step 3 and Task 5 (camera only, or the lock screen where noted), `locked: (true,)` after each, and the exit swipe returns the lock screen. **Look at every screenshot.** Anything that leaks is fixed as in Task 4 Step 4 before this plan is finished. Then restore the file as in Step 1.

- [ ] **Step 3: Tidy the package files**

In `pmaports/temp/phosh/APKBUILD`, the top comment: describe all four patches (the lock screen camera one: "lockscreen-camera.patch: the camera from the lock screen (L16 downstream: org.l16linux.Shell.LockscreenCamera, the exit strip and the lock screen button)"). Check `sha512sums` carries the real hash of the final patch (`tools/phosh-build.sh` keeps it current): 
Run: `cd /Users/lumey/src/l16-linux/pmaports/temp/phosh && shasum -a 512 lockscreen-camera.patch | cut -c1-16; grep "lockscreen-camera.patch" APKBUILD | cut -c1-16; grep -n "^pkgrel" APKBUILD`
Expected: the two hash prefixes are equal; `pkgrel=101`.

- [ ] **Step 4: Dry-run the install of exactly this package state**

The last `tools/phosh-build.sh` run built from these files. Confirm the apk on the device is that one: `ssh root@192.168.1.191 'apk info -v phosh; md5sum /usr/libexec/phosh'` and `md5sum` the same binary extracted from `~/phosh-build/phosh-0.55.0-r101.apk` (`tar -xzOf ~/phosh-build/phosh-0.55.0-r101.apk usr/libexec/phosh | md5`); the sums must be equal. (A mismatch means the device runs an older build than the committed patch: install again with the user's OK.)

- [ ] **Step 5: Commit**

```bash
cd /Users/lumey/src/l16-linux
git add pmaports/temp/phosh/APKBUILD pmaports/temp/phosh/lockscreen-camera.patch
git commit -m "phosh r101: the lock screen camera, ready for CI

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
Do not push: the user decides (and a push to the fork triggers its CI; `build.yml` builds phosh there only if its secret exists, which it doesn't).

---

## Self-review

- **Spec coverage:** D-Bus `Open()` with the app chosen by phosh and the three fitness checks → Task 3 (`default_camera`, `fit_for_lock_screen`); lock screen button → Task 6; steps the lock screen aside, panels and home off, `locked` untouched → Task 3 (`phosh_shell_set_camera_over_lock`, `set_stepped_aside`); exit strip and the three exits → Task 5 plus the manager's blank/closed handling in Task 3; 5 s launch watch, failed launch stays locked → Task 3 step 10; re-cover rules (closed, leaves front, another window, blank, unlocked) → Task 3 code, tested in Task 4; invariants 1–3 and 6 → the Task 4 scenarios; invariant 4 → Task 3 (no argument, system-installed, declared, `Locked` action); invariant 5 (no gallery in the locked camera) → plan C; the `lock-screen-camera` key and switch → Task 1 and Task 3 (`lock_screen_camera_enabled`); testing by `grim` + uinput → Task 4. Not here, by design: `--locked` in the camera apps (plan C) and `l16-shutter` (plan D). The spec's "signals the process after 3 s" → `on_kill_timeout` (Task 3), which kills only if the camera's window is still present.
- **Placeholders:** none in code. The one deliberate unknown is the exact outcome of the first device test (whether hiding the layer surfaces behaves as modelled); Task 3 steps 8-10 and Task 4 are written so that a different outcome becomes a ledgered `Ruling:` or, if the spec's design cannot hold, a stop to report.
- **Type consistency:** `phosh_lockscreen_camera_manager_{new,open,available,close_camera}`, `phosh_shell_{get_lockscreen_camera_manager,set_camera_over_lock}`, `phosh_lockscreen_manager_{set_stepped_aside,wakeup}`, `phosh_exit_strip_new` and the `exit-requested` signal are named identically where defined (Tasks 3, 5) and where used (Tasks 3, 5, 6).
