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
# (not piped into tail: that would hide pmbootstrap's exit status and report a failed build as done)
LOG=$(mktemp)
if ! ssh "$VM" 'PATH=$HOME/.local/bin:$PATH pmbootstrap -y build --arch aarch64 phosh' > "$LOG" 2>&1; then
	tail -40 "$LOG"
	echo "BUILD FAILED (the compiler's errors are above; the full log is $LOG)" >&2
	exit 1
fi
tail -6 "$LOG"
rm -f "$LOG"
mkdir -p "$HOME/phosh-build"
scp -q "$VM":.local/var/pmbootstrap/packages/v26.06/aarch64/phosh-0.55.0-*.apk \
  "$VM":.local/var/pmbootstrap/packages/v26.06/aarch64/libphosh-0.55.0-*.apk "$HOME/phosh-build/"
ls -la "$HOME/phosh-build/"
