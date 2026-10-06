// L16 Settings: the options of the L16's own apps, in groups, so more can join the camera one.
use adw::prelude::*;
use adw::{gio, glib};

const APP_ID: &str = "org.l16linux.Settings";
const SCHEMA: &str = "org.l16linux.camera";

// the cameras one can choose: (desktop id, name)
const CAMERAS: [(&str, &str); 2] = [
    ("org.l16linux.Camera.desktop", "Viewfinder"),
    ("org.l16linux.Nebula.desktop", "Nebula"),
];

fn camera_group() -> adw::PreferencesGroup {
    let group = adw::PreferencesGroup::builder()
        .title("Camera")
        .description("Opened by the gallery's camera button")
        .build();
    // only the cameras that are installed (the chosen one stays listed, so the row shows it)
    let settings = gio::Settings::new(SCHEMA);
    let chosen = settings.string("default-camera").to_string();
    let cameras: Vec<(&str, &str)> = CAMERAS
        .iter()
        .copied()
        .filter(|(id, _)| *id == chosen || gio::DesktopAppInfo::new(id).is_some())
        .collect();
    let names: Vec<&str> = cameras.iter().map(|(_, n)| *n).collect();
    let row = adw::ComboRow::builder()
        .title("Default camera")
        .model(&gtk4_string_list(&names))
        .build();
    if let Some(i) = cameras.iter().position(|(id, _)| *id == chosen) {
        row.set_selected(i as u32);
    }
    row.connect_selected_notify(move |row| {
        if let Some((id, _)) = cameras.get(row.selected() as usize) {
            if let Err(e) = settings.set_string("default-camera", id) {
                eprintln!("saving the default camera: {e}");
            }
        }
    });
    group.add(&row);
    group
}

fn gtk4_string_list(items: &[&str]) -> adw::gtk::StringList {
    adw::gtk::StringList::new(items)
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
