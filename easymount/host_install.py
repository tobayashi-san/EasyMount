from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .constants import APP_NAME, VERSION
from .launcher import is_flatpak


POLKIT_POLICY = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE policyconfig PUBLIC
 "-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/PolicyKit/1/policyconfig.dtd">
<policyconfig>
  <vendor>EasyMount</vendor>
  <vendor_url>https://github.com/tobayashi-san/EasyMount</vendor_url>

  <action id="org.easymount.helper.manage-mounts">
    <description>Manage EasyMount network mounts</description>
    <message>Authentication is required to configure SMB and NFS mounts</message>
    <defaults>
      <allow_any>auth_admin</allow_any>
      <allow_inactive>auth_admin</allow_inactive>
      <allow_active>auth_admin_keep</allow_active>
    </defaults>
    <annotate key="org.freedesktop.policykit.exec.path">/usr/libexec/easymount-helper</annotate>
    <annotate key="org.freedesktop.policykit.exec.allow_gui">true</annotate>
  </action>
</policyconfig>
"""

POLKIT_RULES = """polkit.addRule(function(action, subject) {
    if (action.id == "org.easymount.helper.manage-mounts" &&
        subject.local &&
        subject.active) {
        return polkit.Result.YES;
    }
});
"""

AGENT_SERVICE = """[Unit]
Description=Restore EasyMount mounts after login
After=graphical-session.target

[Service]
Type=oneshot
ExecStart=/usr/bin/easymount-agent

[Install]
WantedBy=default.target
"""

PYPROJECT = f"""[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"

[project]
name = "easymount"
version = "{VERSION}"
description = "A Linux desktop GUI for persistent SMB and NFS mounts"
requires-python = ">=3.10"
license = {{ text = "MIT" }}
authors = [{{ name = "EasyMount contributors" }}]

[project.scripts]
easymount = "easymount.app:main"
easymount-agent = "easymount.agent:main"
easymount-helper = "easymount.helper:main"

[tool.setuptools]
packages = ["easymount"]
"""

INSTALL_SCRIPT = """#!/bin/sh
set -eu

prefix="${1:-/usr}"
repo_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
policy_tmp="$(mktemp)"
agent_tmp="$(mktemp)"
trap 'rm -f "${policy_tmp}" "${agent_tmp}"' EXIT

install -d "${prefix}/bin" "${prefix}/libexec" "${prefix}/lib/easymount" "${prefix}/lib/systemd/user" /usr/share/polkit-1/actions /usr/share/polkit-1/rules.d

rm -rf "${prefix}/lib/easymount/easymount"
cp -R "${repo_dir}/easymount" "${prefix}/lib/easymount/easymount"
find "${prefix}/lib/easymount/easymount" -type d -name __pycache__ -prune -exec rm -rf {} +

cat > "${prefix}/bin/easymount-helper" <<EOF
#!/bin/sh
export PYTHONPATH="${prefix}/lib/easymount\\${PYTHONPATH:+:\\${PYTHONPATH}}"
exec python3 -m easymount.helper "\\$@"
EOF
chmod 0755 "${prefix}/bin/easymount-helper"

cat > "${prefix}/bin/easymount-agent" <<EOF
#!/bin/sh
export PYTHONPATH="${prefix}/lib/easymount\\${PYTHONPATH:+:\\${PYTHONPATH}}"
exec python3 -m easymount.agent "\\$@"
EOF
chmod 0755 "${prefix}/bin/easymount-agent"

cat > "${prefix}/libexec/easymount-helper" <<EOF
#!/bin/sh
exec "${prefix}/bin/easymount-helper" "\\$@"
EOF
chmod 0755 "${prefix}/libexec/easymount-helper"

sed "s#/usr/libexec/easymount-helper#${prefix}/libexec/easymount-helper#g" \\
  "${repo_dir}/packaging/polkit/org.easymount.helper.policy" > "${policy_tmp}"
install -m 0644 "${policy_tmp}" /usr/share/polkit-1/actions/org.easymount.helper.policy
install -m 0644 "${repo_dir}/packaging/polkit/org.easymount.helper.rules" /usr/share/polkit-1/rules.d/org.easymount.helper.rules

sed "s#/usr/bin/easymount-agent#${prefix}/bin/easymount-agent#g" \\
  "${repo_dir}/packaging/systemd/easymount-agent.service" > "${agent_tmp}"
install -m 0644 "${agent_tmp}" "${prefix}/lib/systemd/user/easymount-agent.service"

rm -f \\
  "${prefix}/libexec/easysmb-helper" \\
  /usr/share/polkit-1/actions/org.easysmb.helper.policy \\
  /usr/share/polkit-1/rules.d/org.easysmb.helper.rules

if command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload >/dev/null 2>&1 || true
  systemctl --global enable easymount-agent.service >/dev/null 2>&1 || true
fi

printf '%s\\n' "Installed EasyMount host helper."
"""

UNINSTALL_SCRIPT = """#!/bin/sh
set -eu

prefix="${1:-/usr}"

rm -f \\
  "${prefix}/bin/easymount-helper" \\
  "${prefix}/bin/easymount-agent" \\
  "${prefix}/libexec/easymount-helper" \\
  "${prefix}/libexec/easysmb-helper" \\
  "${prefix}/lib/systemd/user/easymount-agent.service" \\
  /usr/share/polkit-1/actions/org.easymount.helper.policy \\
  /usr/share/polkit-1/actions/org.easysmb.helper.policy \\
  /usr/share/polkit-1/rules.d/org.easymount.helper.rules \\
  /usr/share/polkit-1/rules.d/org.easysmb.helper.rules
rm -rf "${prefix}/lib/easymount"

if command -v systemctl >/dev/null 2>&1; then
  systemctl --global disable easymount-agent.service >/dev/null 2>&1 || true
  systemctl daemon-reload >/dev/null 2>&1 || true
fi

printf '%s\\n' "Removed EasyMount host helper files."
"""


def cache_root() -> Path:
    root = os.environ.get("XDG_CACHE_HOME")
    if root:
        return Path(root) / "easymount"
    return Path.home() / ".cache" / "easymount"


REPO_ROOT = Path(__file__).resolve().parent.parent


def packaging_text(rel_path: str, fallback: str) -> str:
    """Prefer the canonical file in the source tree; fall back to the embedded copy.

    The embedded constants keep the helper installable from an installed package
    or Flatpak sandbox where the ``packaging/`` tree is not shipped, while a
    source/dev checkout stays the single source of truth.
    """
    candidate = REPO_ROOT / rel_path
    try:
        return candidate.read_text(encoding="utf-8")
    except OSError:
        return fallback


def export_host_installer(root: str | os.PathLike[str] | None = None) -> Path:
    export_root = Path(root) if root is not None else cache_root() / "host-installer"
    if export_root.exists():
        shutil.rmtree(export_root)
    package_root = export_root / "easymount"
    package_root.mkdir(parents=True)

    source_package = Path(__file__).resolve().parent
    for path in source_package.glob("*.py"):
        shutil.copy2(path, package_root / path.name)

    write_file(export_root / "pyproject.toml", PYPROJECT)
    write_file(export_root / "README.md", f"# {APP_NAME} host helper export\n")
    write_file(
        export_root / "packaging" / "polkit" / "org.easymount.helper.policy",
        packaging_text("packaging/polkit/org.easymount.helper.policy", POLKIT_POLICY),
    )
    write_file(
        export_root / "packaging" / "polkit" / "org.easymount.helper.rules",
        packaging_text("packaging/polkit/org.easymount.helper.rules", POLKIT_RULES),
    )
    write_file(
        export_root / "packaging" / "systemd" / "easymount-agent.service",
        packaging_text("packaging/systemd/easymount-agent.service", AGENT_SERVICE),
    )

    install_script = export_root / "scripts" / "install-host-helper.sh"
    write_file(install_script, INSTALL_SCRIPT)
    install_script.chmod(0o755)
    uninstall_script = export_root / "scripts" / "uninstall-host-helper.sh"
    write_file(uninstall_script, UNINSTALL_SCRIPT)
    uninstall_script.chmod(0o755)
    return install_script


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def host_prefix() -> list[str]:
    if not is_flatpak():
        return []
    flatpak_spawn = shutil.which("flatpak-spawn") or "/usr/bin/flatpak-spawn"
    return [flatpak_spawn, "--host"]


def install_host_helper() -> subprocess.CompletedProcess[str]:
    script = export_host_installer()
    return subprocess.run(
        [*host_prefix(), "pkexec", "/bin/sh", str(script)],
        text=True,
        capture_output=True,
        check=False,
    )


def uninstall_host_helper() -> subprocess.CompletedProcess[str]:
    script = export_host_installer().parent / "uninstall-host-helper.sh"
    return subprocess.run(
        [*host_prefix(), "pkexec", "/bin/sh", str(script)],
        text=True,
        capture_output=True,
        check=False,
    )
