# Camera Discovery Implementation Plan (plan A of the lock-screen camera)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** L16 Settings lists whatever camera apps declare themselves in their desktop files (`X-L16-Camera=true`), instead of a hardcoded Viewfinder/Nebula pair.

**Architecture:** A dependency-free module `l16-settings/src/cameras.rs` turns a list of desktop entries into the list of choosable cameras (pure logic, unit-tested with `rustc --test`, no GTK needed). `main.rs` feeds it `gio::AppInfo::all()` and shows the result in the existing "Default camera" row. The two camera apps' desktop files gain the `X-L16-Camera=true` key.

**Tech Stack:** Rust, libadwaita 0.8 / GTK4 (gtk-rs `gio`), GLib desktop entries, Alpine APKBUILDs.

**Spec:** `docs/superpowers/specs/2026-10-05-lockscreen-camera-design.md` (section "Decisions": cameras are discovered, not hardcoded; section "Settings and schema").

**Scope of this plan:** only the discovery. The lock-screen pieces are separate plans written after this one: **B** the phosh patch (and the `lock-screen-camera` key and its Settings switch), **C** the camera apps' `--locked` mode (and their `Actions=Locked;`), **D** `l16-shutter`. The `Locked` desktop action is deliberately *not* added here: the apps don't understand `--locked` yet, and GApplication would refuse an unknown option.

## Global Constraints

- The desktop-file key is exactly `X-L16-Camera=true` (boolean, read with `DesktopAppInfo::boolean`).
- The gsettings key stays `org.l16linux.camera` / `default-camera`, a desktop id string (unchanged).
- The chosen camera stays listed even if its app is not installed (the row must always show it).
- `l16-settings` stays a libadwaita 0.8 / GTK4 Rust app with no new dependencies; `cameras.rs` uses only `std`.
- Package checksums are the sha512 of `sync.sh`'s reproducible tarball; they are made with GNU tar and gzip (not macOS), and each changed package's `pkgrel` is bumped.
- Commits are authored as `lumey <46928172+lumeyisnotyou@users.noreply.github.com>` (repo-local config in `~/src/l16-linux`) and end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Do not push without being asked.
- Device: `root@192.168.1.191` (ssh); build box `lumey@192.168.1.6`. Don't close the user's running apps without asking. Windows opened on the phone for tests are the user's screen: close the ones you opened.

## Review Focus

1. **No camera app installed, and nothing chosen:** Settings must open with an empty, disabled row and a message, not crash or show a blank combo. (Task 1 test `empty_when_nothing`; Task 2 builds the empty state.)
2. **The chosen camera's app was uninstalled:** the row still shows its name and keeps the setting, and doesn't silently switch. (Task 1 test `chosen_missing_stays_listed`.)
3. **The same desktop id twice** (a system entry and a user override in `~/.local/share/applications`): one row, not two. (Task 1 test `duplicate_ids_collapse`.)
4. **An entry that says `X-L16-Camera=false`, or any other value, or no key:** not listed. (Task 1 test `only_flagged_apps`; `boolean()` is false for all three.)
5. **Two cameras with the same display name:** both stay listed and ordering is stable (by id), so the selected index is never ambiguous. (Task 1 test `same_name_orders_by_id`.)

---

## File Structure

- Create: `l16-settings/src/cameras.rs`: pure discovery logic and its tests (no GTK).
- Modify: `l16-settings/src/main.rs`: use `cameras::discover`; empty state; remove the `CAMERAS` array.
- Modify: `l16-camera/org.l16linux.Camera.desktop`: add `X-L16-Camera=true`.
- Modify (other repo): `~/src/nebula/org.l16linux.Nebula.desktop`: add `X-L16-Camera=true`.
- Modify: `pmaports/main/l16-settings/APKBUILD`, `pmaports/main/l16-camera/APKBUILD`: `pkgrel` bumps and checksums.

---

### Task 1: The discovery logic (`cameras.rs`)

**Files:**
- Create: `l16-settings/src/cameras.rs`

**Interfaces:**
- Produces (used by Task 2):
  - `pub struct App { pub id: String, pub name: String, pub is_camera: bool }`: a desktop entry as read from the system.
  - `pub struct Camera { pub id: String, pub name: String }`: a row of the list (`Clone, Debug, PartialEq, Eq`).
  - `pub fn discover(apps: impl IntoIterator<Item = App>, chosen: &str) -> Vec<Camera>`.

Behavior of `discover`: keep apps with `is_camera`; drop duplicate ids (first seen wins); sort by name case-insensitively, ties by id; then, if `chosen` is non-empty and not in the list, append a `Camera` for it, named from its id (`org.l16linux.Nebula.desktop` → `Nebula`: the last dot-separated segment before `.desktop`).

- [ ] **Step 1: Write the failing tests (and a stub so they compile)**

Create `l16-settings/src/cameras.rs`:

```rust
// Which camera apps exist: the desktop entries that declare X-L16-Camera=true. Pure logic, no
// GTK, so it is tested on its own (rustc --test src/cameras.rs).

/// A desktop entry as the system lists it.
pub struct App {
    pub id: String,
    pub name: String,
    pub is_camera: bool,
}

/// One row of the "Default camera" list.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Camera {
    pub id: String,
    pub name: String,
}

pub fn discover(apps: impl IntoIterator<Item = App>, chosen: &str) -> Vec<Camera> {
    let _ = (apps, chosen);
    Vec::new()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn app(id: &str, name: &str, is_camera: bool) -> App {
        App { id: id.into(), name: name.into(), is_camera }
    }
    fn cam(id: &str, name: &str) -> Camera {
        Camera { id: id.into(), name: name.into() }
    }

    #[test]
    fn only_flagged_apps() {
        let got = discover(
            vec![app("a.desktop", "Aaa", true), app("b.desktop", "Bbb", false)],
            "",
        );
        assert_eq!(got, vec![cam("a.desktop", "Aaa")]);
    }

    #[test]
    fn empty_when_nothing() {
        assert_eq!(discover(Vec::new(), ""), Vec::new());
    }

    #[test]
    fn sorted_by_name_ignoring_case() {
        let got = discover(
            vec![app("z.desktop", "viewfinder", true), app("n.desktop", "Nebula", true)],
            "",
        );
        assert_eq!(got, vec![cam("n.desktop", "Nebula"), cam("z.desktop", "viewfinder")]);
    }

    #[test]
    fn same_name_orders_by_id() {
        let got = discover(
            vec![app("b.desktop", "Cam", true), app("a.desktop", "Cam", true)],
            "",
        );
        assert_eq!(got, vec![cam("a.desktop", "Cam"), cam("b.desktop", "Cam")]);
    }

    #[test]
    fn duplicate_ids_collapse() {
        let got = discover(
            vec![app("a.desktop", "First", true), app("a.desktop", "Second", true)],
            "",
        );
        assert_eq!(got, vec![cam("a.desktop", "First")]);
    }

    #[test]
    fn chosen_missing_stays_listed() {
        let got = discover(
            vec![app("a.desktop", "Aaa", true)],
            "org.l16linux.Nebula.desktop",
        );
        assert_eq!(
            got,
            vec![cam("a.desktop", "Aaa"), cam("org.l16linux.Nebula.desktop", "Nebula")]
        );
    }

    #[test]
    fn chosen_present_is_not_added_twice() {
        let got = discover(vec![app("a.desktop", "Aaa", true)], "a.desktop");
        assert_eq!(got, vec![cam("a.desktop", "Aaa")]);
    }

    #[test]
    fn chosen_without_dots_keeps_its_name() {
        let got = discover(Vec::new(), "weird");
        assert_eq!(got, vec![cam("weird", "weird")]);
    }
}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/lumey/src/l16-linux/l16-settings && rustc --edition 2021 --test src/cameras.rs -o /tmp/cameras_test 2>&1 | grep -v "^warning" | head -5; /tmp/cameras_test 2>&1 | tail -15`
Expected: it compiles (dead-code warnings are fine) and ends `test result: FAILED. 1 passed; 7 failed`. The stub returns an empty list, so only `empty_when_nothing` passes.

- [ ] **Step 3: Write the implementation**

Replace the stub `discover` in `l16-settings/src/cameras.rs` with:

```rust
pub fn discover(apps: impl IntoIterator<Item = App>, chosen: &str) -> Vec<Camera> {
    let mut list: Vec<Camera> = Vec::new();
    for a in apps {
        if a.is_camera && !list.iter().any(|c| c.id == a.id) {
            list.push(Camera { id: a.id, name: a.name });
        }
    }
    list.sort_by(|a, b| {
        a.name.to_lowercase().cmp(&b.name.to_lowercase()).then_with(|| a.id.cmp(&b.id))
    });
    // the chosen camera stays on the list even when its app is gone, so the row can show it
    if !chosen.is_empty() && !list.iter().any(|c| c.id == chosen) {
        list.push(Camera { id: chosen.to_string(), name: name_from_id(chosen) });
    }
    list
}

// "org.l16linux.Nebula.desktop" -> "Nebula"
fn name_from_id(id: &str) -> String {
    let stem = id.strip_suffix(".desktop").unwrap_or(id);
    stem.rsplit('.').next().unwrap_or(stem).to_string()
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /Users/lumey/src/l16-linux/l16-settings && rustc --edition 2021 --test src/cameras.rs -o /tmp/cameras_test 2>&1 | grep -E "^error" ; /tmp/cameras_test 2>&1 | tail -4`
Expected: `test result: ok. 8 passed; 0 failed`

- [ ] **Step 5: Commit**

```bash
cd /Users/lumey/src/l16-linux
git add l16-settings/src/cameras.rs
git commit -m "l16-settings: the camera discovery, as pure logic with tests

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Settings shows the discovered cameras

**Files:**
- Modify: `l16-settings/src/main.rs` (whole file; it is short)

**Interfaces:**
- Consumes: `cameras::{App, Camera, discover}` from Task 1.
- Produces: a "Default camera" row whose entries come from `X-L16-Camera=true` desktop entries; disabled with a message when the list is empty.

- [ ] **Step 1: Replace `l16-settings/src/main.rs`**

```rust
// L16 Settings: the options of the L16's own apps, in groups, so more can join the camera one.
mod cameras;

use adw::prelude::*;
use adw::{gio, glib};

const APP_ID: &str = "org.l16linux.Settings";
const SCHEMA: &str = "org.l16linux.camera";

// the desktop entries on the system, as the discovery wants them (the key is X-L16-Camera=true)
fn installed_apps() -> Vec<cameras::App> {
    gio::AppInfo::all()
        .into_iter()
        .filter_map(|a| {
            let d = a.downcast::<gio::DesktopAppInfo>().ok()?;
            Some(cameras::App {
                id: d.id()?.to_string(),
                name: d.name().to_string(),
                is_camera: d.boolean("X-L16-Camera"),
            })
        })
        .collect()
}

fn camera_group() -> adw::PreferencesGroup {
    let group = adw::PreferencesGroup::builder()
        .title("Camera")
        .description("Opened by the gallery's camera button")
        .build();
    let settings = gio::Settings::new(SCHEMA);
    let chosen = settings.string("default-camera").to_string();
    let cams = cameras::discover(installed_apps(), &chosen);
    let names: Vec<&str> = cams.iter().map(|c| c.name.as_str()).collect();
    let row = adw::ComboRow::builder()
        .title("Default camera")
        .model(&adw::gtk::StringList::new(&names))
        .build();
    if cams.is_empty() {
        // nothing to choose: say so, and don't offer an empty list
        row.set_sensitive(false);
        row.set_subtitle("No camera app is installed");
    } else {
        if let Some(i) = cams.iter().position(|c| c.id == chosen) {
            row.set_selected(i as u32);
        }
        row.connect_selected_notify(move |row| {
            if let Some(c) = cams.get(row.selected() as usize) {
                if let Err(e) = settings.set_string("default-camera", &c.id) {
                    eprintln!("saving the default camera: {e}");
                }
            }
        });
    }
    group.add(&row);
    group
}

fn build(app: &adw::Application) {
    if let Some(w) = app.active_window() {
        w.present();
        return;
    }
    let page = adw::PreferencesPage::new();
    page.add(&camera_group());
    let view = adw::ToolbarView::new();
    view.add_top_bar(&adw::HeaderBar::new());
    view.set_content(Some(&page));
    adw::ApplicationWindow::builder()
        .application(app)
        .title("L16 Settings")
        .default_width(360)
        .default_height(640)
        .content(&view)
        .build()
        .present();
}

fn main() -> glib::ExitCode {
    // (the schema ships with this program; without it Settings::new would abort)
    let installed = gio::SettingsSchemaSource::default()
        .and_then(|s| s.lookup(SCHEMA, true))
        .is_some();
    if !installed {
        eprintln!("the {SCHEMA} schema isn't installed (glib-compile-schemas)");
        return glib::ExitCode::FAILURE;
    }
    let app = adw::Application::builder().application_id(APP_ID).build();
    app.connect_activate(build);
    app.run()
}
```

- [ ] **Step 2: Build it on the device**

The Mac has no libadwaita, so this builds on the device (it has `libadwaita-dev` and a warm cargo target dir).

Run:
```bash
cd /Users/lumey/src/l16-linux && tar --exclude=target -cf - l16-settings | ssh root@192.168.1.191 'su user -c "cd ~/build/gtree && tar xf -"' && ssh root@192.168.1.191 'su user -c "cd ~/build/gtree/l16-settings && cargo build --release --target-dir ~/build/l16-camera/target 2>&1 | tail -15"'
```
Expected: `Finished release profile`, no `error`. (First build after a long gap may take a few minutes; run in the background and wait.) If `d.id()` or `d.boolean` report "no method", add `use adw::gio::prelude::*;`; `adw::prelude::*` normally covers it.

- [ ] **Step 3: Run the logic tests once more and commit**

Run: `cd /Users/lumey/src/l16-linux/l16-settings && rustc --edition 2021 --test src/cameras.rs -o /tmp/cameras_test 2>&1 | grep -E "^error"; /tmp/cameras_test 2>&1 | tail -2`
Expected: `test result: ok. 8 passed`

```bash
cd /Users/lumey/src/l16-linux
git add l16-settings/src/main.rs
git commit -m "l16-settings: the default camera row lists the apps that declare X-L16-Camera

Not a fixed Viewfinder/Nebula pair any more; with none installed the row is off and says so.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Declare the cameras, package, and check on the device

**Files:**
- Modify: `l16-camera/org.l16linux.Camera.desktop`
- Modify: `~/src/nebula/org.l16linux.Nebula.desktop` (the Nebula repo)
- Modify: `pmaports/main/l16-settings/APKBUILD` (`pkgrel=0` → `1`, checksum)
- Modify: `pmaports/main/l16-camera/APKBUILD` (`pkgrel=17` → `18`, checksum)

**Interfaces:**
- Consumes: Task 2's Settings build (installed to `/usr/local/bin/l16-settings` on the device for the check).
- Produces: both camera apps declare `X-L16-Camera=true`; packages ready for CI/VM builds.

- [ ] **Step 1: Add the key to both desktop files**

In `l16-camera/org.l16linux.Camera.desktop` add this line after `Categories=Graphics;Photography;`:
```
X-L16-Camera=true
```
In `~/src/nebula/org.l16linux.Nebula.desktop` add the same line after its `Categories=` line.

- [ ] **Step 2: Validate the desktop files**

Run: `grep -c "X-L16-Camera=true" /Users/lumey/src/l16-linux/l16-camera/org.l16linux.Camera.desktop ~/src/nebula/org.l16linux.Nebula.desktop`
Expected: `…Camera.desktop:1` and `…Nebula.desktop:1`.
If `desktop-file-validate` is available (`which desktop-file-validate`), run it on both; expect no `error:` lines (the `X-` key is allowed).

- [ ] **Step 3: Install and check on the device**

Run:
```bash
cd /Users/lumey/src/l16-linux
scp -q l16-camera/org.l16linux.Camera.desktop ~/src/nebula/org.l16linux.Nebula.desktop root@192.168.1.191:/usr/share/applications/
ssh root@192.168.1.191 'install -m755 /home/user/build/l16-camera/target/release/l16-settings /usr/local/bin/l16-settings; update-desktop-database /usr/share/applications; grep -l "X-L16-Camera=true" /usr/share/applications/*.desktop'
```
Expected: both desktop files listed.

Then, as the user asked, open Settings on the phone (it is the user's screen: close it afterwards):
```bash
ssh root@192.168.1.191 'P0=$(ps | awk "/[l]ibexec\/phosh$/ {print \$1; exit}"); B=$(tr "\0" "\n" < /proc/$P0/environ | grep ^DBUS_SESSION_BUS_ADDRESS= | cut -d= -f2-); su user -c "env XDG_RUNTIME_DIR=/run/user/10000 WAYLAND_DISPLAY=wayland-0 DBUS_SESSION_BUS_ADDRESS=$B gtk-launch org.l16linux.Settings >/tmp/set.log 2>&1 &"; sleep 5; cat /tmp/set.log'
```
Expected: empty log; the user sees "Default camera" with Nebula and Viewfinder.

- [ ] **Step 4: Prove it is dynamic with a throwaway third camera**

Run:
```bash
ssh root@192.168.1.191 'mkdir -p /home/user/.local/share/applications && cat > /home/user/.local/share/applications/test-cam.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Test Camera
Exec=true
X-L16-Camera=true
EOF
chown user:user /home/user/.local/share/applications/test-cam.desktop'
```
Ask the user to reopen L16 Settings (close it first). Expected: three entries, "Test Camera" included. Then remove it:
```bash
ssh root@192.168.1.191 'rm /home/user/.local/share/applications/test-cam.desktop'
```
Expected: back to two entries on the next open.

- [ ] **Step 5: Bump the packages and make the checksums**

In `pmaports/main/l16-settings/APKBUILD` set `pkgrel=1`; in `pmaports/main/l16-camera/APKBUILD` set `pkgrel=18`. Commit the sources first (the checksum is made from the committed tree):

```bash
cd /Users/lumey/src/l16-linux
git add l16-camera/org.l16linux.Camera.desktop pmaports/main/l16-settings/APKBUILD pmaports/main/l16-camera/APKBUILD
git commit -m "Viewfinder declares itself a camera (X-L16-Camera) (l16-camera r18, l16-settings r1)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
Then make the checksums on the build box, with GNU tar (the committed tree as `sync.sh` packs it):
```bash
git archive HEAD | ssh lumey@192.168.1.6 'rm -rf ~/src/l16-sync && mkdir -p ~/src/l16-sync && tar xf - -C ~/src/l16-sync && cd ~/src/l16-sync && PATH=$HOME/.local/bin:$PATH bash pmaports/sync.sh >/dev/null 2>&1; cd ~/.local/var/pmbootstrap/cache_git/pmaports/main && sha512sum l16-camera/l16-camera-src.tar.gz l16-settings/l16-settings-src.tar.gz'
```
Expected: two sha512 lines. Write each hash into the matching `sha512sums` line of `pmaports/main/l16-camera/APKBUILD` and `pmaports/main/l16-settings/APKBUILD` (the line ends `  l16-camera-src.tar.gz` / `  l16-settings-src.tar.gz`).

Sanity check that the method matches CI: the same command's `l16-gallery` hash must equal the one already committed in `pmaports/main/l16-gallery/APKBUILD` (`4d3ffcfb…`); add `l16-gallery/l16-gallery-src.tar.gz` to the `sha512sum` line to see it.

- [ ] **Step 6: Commit the checksums and the Nebula change**

```bash
cd /Users/lumey/src/l16-linux
git add pmaports/main/l16-camera/APKBUILD pmaports/main/l16-settings/APKBUILD
git commit -m "Checksums for l16-camera r18 and l16-settings r1

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
cd ~/src/nebula
git add org.l16linux.Nebula.desktop
git commit -m "Declare Nebula a camera (X-L16-Camera=true) for L16 Settings' list

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
Expected: two commits in `l16-linux` after the earlier ones, one in nebula. Neither is pushed.

---

## Self-review

- **Spec coverage:** "cameras are discovered by `X-L16-Camera=true`" → Tasks 1–3; "the chosen stays listed" → Task 1 tests; "the gallery's `default_camera()` already works with any id" → no change needed (it already validates with `DesktopAppInfo::new`). Everything else in the spec (phosh `Open()`, the exit strip, `--locked`, `l16-shutter`, the `lock-screen-camera` key and switch, `Actions=Locked;`) is in plans B–D, which will be written next.
- **Placeholders:** none. The one value to fill in during execution is each package's checksum (Task 3 Step 5), which cannot exist before the commit it is made from.
- **Type consistency:** `App`, `Camera`, `discover(apps, chosen)` are used in Task 2 exactly as defined in Task 1.
