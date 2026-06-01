#!/bin/sh
set -eu

prefix="/usr"

usage() {
  printf '%s\n' "Usage: sudo ./scripts/uninstall-helper.sh [prefix]"
  printf '%s\n' ""
  printf '%s\n' "Default prefix: /usr"
  printf '%s\n' "This removes files installed by scripts/install-helper.sh."
  printf '%s\n' "It does not remove user profiles, saved secrets or configured mount units."
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage
  exit 0
fi

if [ "$#" -gt 1 ]; then
  usage >&2
  exit 2
fi

if [ "$#" -eq 1 ]; then
  prefix="$1"
fi

if [ "$(id -u)" -ne 0 ]; then
  printf '%s\n' "Run this script as root, for example: sudo ./scripts/uninstall-helper.sh" >&2
  exit 1
fi

pip_extra_args=""
if python3 -m pip uninstall --help 2>/dev/null | grep -q -- "--break-system-packages"; then
  pip_extra_args="--break-system-packages"
fi

python3 -m pip uninstall -y --disable-pip-version-check ${pip_extra_args} easymount >/dev/null 2>&1 || true
python3 -m pip uninstall -y --disable-pip-version-check ${pip_extra_args} easysmb >/dev/null 2>&1 || true

if command -v systemctl >/dev/null 2>&1; then
  systemctl --global disable easymount-agent.service >/dev/null 2>&1 || true
fi

rm -f \
  "${prefix}/libexec/easymount-helper" \
  "${prefix}/libexec/easysmb-helper" \
  "${prefix}/lib/systemd/user/easymount-agent.service" \
  "${prefix}/share/applications/org.easymount.EasyMount.desktop" \
  "${prefix}/share/applications/org.easysmb.EasySMB.desktop" \
  "${prefix}/share/metainfo/org.easymount.EasyMount.metainfo.xml" \
  "${prefix}/share/metainfo/org.easysmb.EasySMB.metainfo.xml" \
  "${prefix}/share/icons/hicolor/scalable/apps/org.easymount.EasyMount.svg" \
  "${prefix}/share/icons/hicolor/scalable/apps/org.easysmb.EasySMB.svg" \
  /usr/share/polkit-1/actions/org.easymount.helper.policy \
  /usr/share/polkit-1/actions/org.easysmb.helper.policy

if command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1 && [ -d "${prefix}/share/icons/hicolor" ]; then
  gtk-update-icon-cache -q -t -f "${prefix}/share/icons/hicolor" >/dev/null 2>&1 || true
fi
if command -v update-desktop-database >/dev/null 2>&1 && [ -d "${prefix}/share/applications" ]; then
  update-desktop-database -q "${prefix}/share/applications" >/dev/null 2>&1 || true
fi

printf '%s\n' "Removed EasyMount files installed below ${prefix}."
printf '%s\n' "User profiles, saved secrets and configured mount units were left unchanged."
printf '%s\n' "Delete shares in EasyMount before uninstalling if you want their systemd mount units removed cleanly."
