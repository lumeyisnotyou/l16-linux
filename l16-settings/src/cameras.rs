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
