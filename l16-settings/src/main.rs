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
