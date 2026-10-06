# Helpers for the lock screen camera tests. Source me on the camera, as root:
#   . /tmp/lockcam-env.sh
# u CMD...   runs CMD as the user, in the logged-in phosh session
# lockedhint prints yes/no: the lock state as phosh publishes it to logind (the screensaver's
#            GetActive only says whether the display is off)
# shot FILE  a whole-display screenshot (grim; it needs the display awake)
P0=$(ps -o user,pid,args | awk '$1=="user" && $3 ~ /libexec\/phosh$/ {print $2; exit}')
B=$(tr "\0" "\n" < /proc/$P0/environ | grep ^DBUS_SESSION_BUS_ADDRESS= | cut -d= -f2-)
E="XDG_RUNTIME_DIR=/run/user/10000 WAYLAND_DISPLAY=wayland-0 DBUS_SESSION_BUS_ADDRESS=$B"
u() { su user -c "env $E $*" 2>&1 | grep -v dconf; }
SID=$(loginctl list-sessions --no-legend 2>/dev/null | awk '$3=="user" {print $1; exit}')
lockedhint() { loginctl show-session "$SID" -p LockedHint 2>/dev/null | cut -d= -f2; }
shot() { rm -f "$1"; u "grim -t png $1" | head -2; [ -f "$1" ] || echo "(no screenshot: is the display off?)"; }

SS="gdbus call --session --dest org.gnome.ScreenSaver --object-path /org/gnome/ScreenSaver --method"
LC="gdbus call --session --dest org.l16linux.Shell.LockscreenCamera --object-path /org/l16linux/Shell/LockscreenCamera --method org.l16linux.Shell.LockscreenCamera.Open"
lock()     { u "$SS org.gnome.ScreenSaver.Lock" >/dev/null; sleep 3; }
open_cam() { u "$LC" >/dev/null; sleep 7; }
poke()     { python3 /tmp/lockcam-touch.py "$@"; sleep 1.5; }
# a process by its exact command (never by a pattern that this shell's own command line matches)
pid_of()   { ps -o pid,args | awk -v c="$1" '$2==c {print $1; exit}'; }
kill_app() { P=$(pid_of "$1"); [ -n "$P" ] && u "kill $P"; sleep 4; }
