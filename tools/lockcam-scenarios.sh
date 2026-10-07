# The lock screen camera's leak scenarios, run on the camera (as root) by tools/lockcam-test.sh.
# For each one it lights the lock screen camera, throws touches at the screen, and takes a
# whole-display screenshot into /tmp/lockcam/ for a person to look at. A pass is a screenshot that
# shows only what the comment says. Every scenario also prints LockedHint: it must stay "yes".
# usage: sh /tmp/lockcam-scenarios.sh [scenario ...]     (default: all)
. /tmp/lockcam-env.sh
OUT=/tmp/lockcam
mkdir -p $OUT
chmod 777 $OUT   # grim runs as the user
CAM=/usr/bin/nebula

snap() { r=$(shot "$OUT/$1.png"); echo "  $1.png: $2${r:+   [$r]}"; }
hint() { echo "  LockedHint=$(lockedhint)"; }
camera_up() { lock; u "$SS org.gnome.ScreenSaver.SetActive false" >/dev/null; sleep 1; open_cam; }   # (woken first: opened with the display off, the camera is covered again at once)
close_cam() { kill_app $CAM; }

# a swipe in from each of the four edges, with a screenshot after every one (top, left, right; then the bottom one last: that
# is the exit): at no point an overview, shade or panel over the camera, and the lock screen after the last. (The camera
# app's own left-edge panel may open too until it has a locked mode.)
edge_walk() { poke swipe 500 5 500 400;    snap "$1-top"    "camera only: no shade"
              poke swipe 5 500 400 500;    snap "$1-left"   "camera only: no overview"
              poke swipe 995 500 600 500;  snap "$1-right"  "camera only: nothing from the right edge"
              poke swipe 500 995 500 600;  snap "$1"        "LOCK SCREEN: the bottom swipe is the exit"; }
edges()     { camera_up; edge_walk edges; hint; close_cam; }
corners()   { camera_up; poke corners; snap corners "camera only"; hint; close_cam; }
longpress() { camera_up; poke longpress 500 990; poke longpress 500 10; snap longpress "camera only: no menu or keyboard"; hint; close_cam; }
# the power button blanks the screen; waking it must show the lock screen, not the camera
power()     { camera_up; u "$SS org.gnome.ScreenSaver.SetActive true" >/dev/null; sleep 3; snap power-blank "(the display is off: no screenshot is expected)"
              u "$SS org.gnome.ScreenSaver.SetActive false" >/dev/null; sleep 3; snap power-wake "LOCK SCREEN, not the camera"; hint; close_cam; }
# the camera closes by itself: the lock screen straight away
selfclose() { camera_up; close_cam; u "$SS org.gnome.ScreenSaver.SetActive false" >/dev/null; sleep 1   # (the lock screen blanks itself when idle)
              snap selfclose "LOCK SCREEN"; hint; }
# another app open behind it must never show
behind()    { u "gtk-launch org.l16linux.Settings >/dev/null 2>&1 &"; sleep 4
              camera_up; edge_walk behind; hint
              close_cam; snap behind-closed "LOCK SCREEN: Settings must not show"; kill_app /usr/local/bin/l16-settings; }
# a window that opens over the camera ends it: the lock screen
other()     { camera_up; u "gtk-launch org.l16linux.Gallery >/dev/null 2>&1 &"; sleep 4; snap other-window "LOCK SCREEN: a new window ends the camera"; hint
              kill_app /usr/local/bin/l16-gallery; close_cam; }
# the exit swipe up from the bottom edge: the lock screen straight away, then the camera is gone
exitswipe() { camera_up; snap exit-before "the camera over the lock, a handle along the bottom edge"
              poke swipe 500 996 500 600 250; sleep 2; snap exit-after "LOCK SCREEN straight after the swipe"; hint
              echo "  camera running 2 s after: $([ -n "$(pid_of $CAM)" ] && echo yes || echo no)"; sleep 4
              echo "  camera running 6 s after: $([ -n "$(pid_of $CAM)" ] && echo yes || echo no)"; }
# the lock screen's camera button
button()    { lock; u "$SS org.gnome.ScreenSaver.SetActive false" >/dev/null; sleep 2; snap button "a round camera button at the bottom right"; hint; }
# the switch off: the lock screen camera never opens (the button's own visibility is only decided when a lock screen is
# made, and this runs on one that is already up: judge the camera, not the button)
switchoff() { u "gsettings set org.l16linux.camera lock-screen-camera false" >/dev/null; lock; open_cam; snap switch-off "LOCK SCREEN: the switch is off"; hint
              u "gsettings set org.l16linux.camera lock-screen-camera true" >/dev/null; }

ALL="button edges exitswipe corners longpress power selfclose behind other switchoff"
for s in ${*:-$ALL}; do
  echo "== $s"
  $s
done
echo "done: the screenshots are in $OUT"
