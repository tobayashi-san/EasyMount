#!/bin/sh
set -eu

prefix="${1:-/usr}"
repo_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
policy_tmp="$(mktemp)"
agent_tmp="$(mktemp)"
build_tmp="$(mktemp -d)"
trap 'rm -f "${policy_tmp}" "${agent_tmp}"; rm -rf "${build_tmp}"' EXIT

install -d "${prefix}/bin" "${prefix}/libexec" /usr/share/polkit-1/actions
install -d \
  "${prefix}/lib/systemd/user" \
  "${prefix}/share/applications" \
  "${prefix}/share/metainfo" \
  "${prefix}/share/icons/hicolor/scalable/apps"

cp -R "${repo_dir}" "${build_tmp}/easymount"
rm -rf \
  "${build_tmp}/easymount/.git" \
  "${build_tmp}/easymount/.agents" \
  "${build_tmp}/easymount/.codex" \
  "${build_tmp}/easymount/easymount.egg-info" \
  "${build_tmp}/easymount/easysmb.egg-info"

set -- install --prefix "${prefix}" --disable-pip-version-check --no-input
if python3 -m pip install --help 2>/dev/null | grep -q -- "--root-user-action"; then
  set -- "$@" --root-user-action ignore
fi
if python3 -m pip install --help 2>/dev/null | grep -q -- "--break-system-packages"; then
  set -- "$@" --break-system-packages
fi
set -- "$@" "${build_tmp}/easymount"

python3 -m pip uninstall -y --disable-pip-version-check easysmb >/dev/null 2>&1 || true
echo "Installing EasyMount Python commands into ${prefix}..."
python3 -m pip "$@"

cat > "${prefix}/libexec/easymount-helper" <<EOF
#!/bin/sh
exec "${prefix}/bin/easymount-helper" "\$@"
EOF
chmod 0755 "${prefix}/libexec/easymount-helper"

sed "s#/usr/libexec/easymount-helper#${prefix}/libexec/easymount-helper#g" \
  "${repo_dir}/packaging/polkit/org.easymount.helper.policy" > "${policy_tmp}"
install -m 0644 \
  "${policy_tmp}" \
  /usr/share/polkit-1/actions/org.easymount.helper.policy

install -m 0644 \
  "${repo_dir}/data/org.easymount.EasyMount.desktop" \
  "${prefix}/share/applications/org.easymount.EasyMount.desktop"
install -m 0644 \
  "${repo_dir}/data/icons/hicolor/scalable/apps/org.easymount.EasyMount.svg" \
  "${prefix}/share/icons/hicolor/scalable/apps/org.easymount.EasyMount.svg"
install -m 0644 \
  "${repo_dir}/data/org.easymount.EasyMount.metainfo.xml" \
  "${prefix}/share/metainfo/org.easymount.EasyMount.metainfo.xml"

sed "s#/usr/bin/easymount-agent#${prefix}/bin/easymount-agent#g" \
  "${repo_dir}/packaging/systemd/easymount-agent.service" > "${agent_tmp}"
install -m 0644 \
  "${agent_tmp}" \
  "${prefix}/lib/systemd/user/easymount-agent.service"

rm -f \
  "${prefix}/libexec/easysmb-helper" \
  /usr/share/polkit-1/actions/org.easysmb.helper.policy \
  "${prefix}/share/applications/org.easysmb.EasySMB.desktop" \
  "${prefix}/share/metainfo/org.easysmb.EasySMB.metainfo.xml" \
  "${prefix}/share/icons/hicolor/scalable/apps/org.easysmb.EasySMB.svg"

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -t -f "${prefix}/share/icons/hicolor" >/dev/null 2>&1 || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q "${prefix}/share/applications" >/dev/null 2>&1 || true
fi

echo "Installed EasyMount helper, agent service, desktop file, icon and Polkit policy."
