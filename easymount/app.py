from __future__ import annotations

import sys
from dataclasses import dataclass

from .models import MountMode
from .settings import normalize_theme


# Minimal, theme-neutral application CSS. Colors are left to the active GTK
# theme (Adwaita on GNOME, Breeze-GTK on KDE, ...) so the app blends in. Only
# the semantic status pills, the share-kind badge, spacing helpers and the
# toast use custom styling.
# EasyMount ships its own light/dark colour palette via CSS so the in-app theme
# toggle works reliably on every desktop (GNOME, KDE/Breeze, COSMIC, ...). The
# root window carries a `.theme-light` or `.theme-dark` class that scopes the
# palette below; semantic widgets (status pills, toast) are theme-independent.
APP_CSS = """
/* ---- structural helpers (theme independent) ---------------------------- */
.page {
  padding: 22px;
}

.section-title {
  font-weight: 700;
  font-size: 1.05em;
  margin-bottom: 2px;
}

.page-title {
  font-weight: 800;
  font-size: 1.45em;
}

.field-label {
  font-weight: 600;
  font-size: 0.92em;
}

.field-hint {
  font-size: 0.88em;
}

.share-title {
  font-weight: 700;
  font-size: 1.02em;
}

.share-list,
scrolledwindow,
viewport {
  background: transparent;
}

.app-topbar {
  padding: 8px 14px;
}

.topbar-title {
  font-weight: 700;
}

.dialog-action-bar {
  padding: 12px 16px;
}

/* ---- status pills (semantic colours, both themes) ---------------------- */
.status-pill {
  border-radius: 999px;
  padding: 4px 12px;
  font-weight: 700;
  font-size: 0.85em;
  min-width: 76px;
}

.status-mounted {
  color: #07803d;
  background-color: rgba(18, 146, 69, 0.15);
}

.status-ready {
  color: #755300;
  background-color: rgba(180, 126, 0, 0.16);
}

.status-enabled {
  color: #16707a;
  background-color: rgba(22, 112, 122, 0.14);
}

.status-offline {
  color: #6b7280;
  background-color: rgba(107, 114, 128, 0.14);
}

.status-error {
  color: #9f1239;
  background-color: rgba(190, 18, 60, 0.14);
}

.status-checking {
  color: #8b93a1;
  background-color: rgba(127, 127, 127, 0.12);
}

.share-kind {
  border-radius: 6px;
  padding: 2px 8px;
  font-size: 0.72em;
  font-weight: 800;
  letter-spacing: 0.04em;
}

.app-toast {
  background-color: rgba(34, 36, 40, 0.96);
  color: #ffffff;
  border-radius: 11px;
  padding: 10px 18px;
  margin: 16px;
  font-weight: 600;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.28);
}

/* ====================================================================== */
/*  LIGHT THEME                                                            */
/* ====================================================================== */
.theme-light { background-color: #f5f7fb; color: #1d2635; }
.theme-light label { color: #1d2635; }
.theme-light .dim-label,
.theme-light .field-hint { color: #5d6878; }
.theme-light .share-kind { color: #5d6878; background-color: rgba(90, 90, 90, 0.12); }

.theme-light .app-topbar {
  background: #ffffff;
  border-bottom: 1px solid rgba(127, 127, 127, 0.18);
}
.theme-light .dialog-action-bar {
  background: #ffffff;
  border-top: 1px solid rgba(127, 127, 127, 0.18);
}

.theme-light .app-nav button:checked {
  background: #dfe6f1;
  border-color: transparent;
  color: #111827;
  font-weight: 700;
}
.theme-light .app-nav button:checked:hover { background: #d4ddec; }

.theme-light button {
  background: #ffffff;
  background-image: none;
  color: #1d2635;
  border: 1px solid rgba(93, 104, 120, 0.34);
  border-radius: 9px;
  box-shadow: none;
  padding: 4px 12px;
}
.theme-light button:hover { background: #edf1f7; color: #111827; }
.theme-light button:active { background: #e5ebf4; }
.theme-light button.flat {
  background: transparent;
  border-color: transparent;
}
.theme-light button.flat:hover { background: rgba(127, 127, 127, 0.10); }
.theme-light button.suggested-action {
  background: #16707a;
  color: #ffffff;
  border-color: transparent;
}
.theme-light button.suggested-action:hover { background: #115a62; }
.theme-light button.danger-icon { color: #b42318; }
.theme-light button.danger-icon:hover { background: rgba(180, 35, 24, 0.12); }
.theme-light button.destructive-action {
  background: #b42318;
  color: #ffffff;
  border-color: transparent;
}
.theme-light button.destructive-action:hover { background: #991b12; }

.theme-light checkbutton { color: #1d2635; }
.theme-light checkbutton > check {
  background: #ffffff;
  border: 1px solid rgba(93, 104, 120, 0.40);
  border-radius: 6px;
}
.theme-light checkbutton > check:checked,
.theme-light checkbutton > check:checked:hover {
  background: #16707a;
  border-color: #16707a;
  color: #ffffff;
}

.theme-light popover > contents,
.theme-light popover > arrow {
  background-color: #ffffff;
  color: #1d2635;
  border: 1px solid rgba(127, 127, 127, 0.20);
}
.theme-light popover > contents {
  border-radius: 11px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.16);
  padding: 4px;
}
.theme-light popover listview,
.theme-light popover scrolledwindow,
.theme-light popover .view {
  background-color: transparent;
  color: #1d2635;
}
.theme-light popover row {
  border-radius: 7px;
  color: #1d2635;
  background-color: transparent;
}
.theme-light popover row:selected,
.theme-light popover row:hover { background-color: rgba(22, 112, 122, 0.14); color: #16707a; }

.theme-light entry,
.theme-light spinbutton {
  background: #ffffff;
  color: #1d2635;
  border: 1px solid rgba(93, 104, 120, 0.34);
  border-radius: 9px;
  padding: 6px 10px;
}
.theme-light entry:focus-within { border-color: #16707a; }
.theme-light dropdown > button {
  background: #ffffff;
  border: 1px solid rgba(93, 104, 120, 0.34);
}

.theme-light switch {
  background: rgba(93, 104, 120, 0.30);
  border-radius: 999px;
}
.theme-light switch:checked { background: #16707a; }
.theme-light switch > slider { background: #ffffff; border-radius: 999px; }

.theme-light .share-list > row {
  background: transparent;
}
.theme-light .share-list > row:hover { background: rgba(127, 127, 127, 0.05); }
.theme-light .share-list separator,
.theme-light .share-list > row.separator { background: rgba(127, 127, 127, 0.14); }

/* ====================================================================== */
/*  DARK THEME                                                             */
/* ====================================================================== */
.theme-dark { background-color: #1b1d22; color: #eef1f5; }
.theme-dark label { color: #eef1f5; }
.theme-dark .dim-label,
.theme-dark .field-hint { color: #aab2bf; }
.theme-dark .share-kind { color: #aab2bf; background-color: rgba(255, 255, 255, 0.10); }

.theme-dark .app-topbar {
  background: #25272d;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}
.theme-dark .dialog-action-bar {
  background: #25272d;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.theme-dark .app-nav button:checked {
  background: #373b44;
  border-color: transparent;
  color: #ffffff;
  font-weight: 700;
}
.theme-dark .app-nav button:checked:hover { background: #3f4450; }

.theme-dark button {
  background: #25272d;
  background-image: none;
  color: #eef1f5;
  border: 1px solid rgba(170, 178, 191, 0.24);
  border-radius: 9px;
  box-shadow: none;
  padding: 4px 12px;
}
.theme-dark button:hover { background: #30333b; }
.theme-dark button:active { background: #373b44; }
.theme-dark button.flat {
  background: transparent;
  border-color: transparent;
}
.theme-dark button.flat:hover { background: rgba(255, 255, 255, 0.09); }
.theme-dark button.suggested-action {
  background: #3f9aa6;
  color: #ffffff;
  border-color: transparent;
  font-weight: 700;
}
.theme-dark button.suggested-action:hover { background: #52aeba; }
.theme-dark button.danger-icon { color: #f1786e; }
.theme-dark button.danger-icon:hover { background: rgba(241, 120, 110, 0.16); }
.theme-dark button.destructive-action {
  background: #cf4334;
  color: #ffffff;
  border-color: transparent;
}
.theme-dark button.destructive-action:hover { background: #dc5747; }

.theme-dark checkbutton { color: #eef1f5; }
.theme-dark checkbutton > check {
  background: #25272d;
  border: 1px solid rgba(170, 178, 191, 0.30);
  border-radius: 6px;
}
.theme-dark checkbutton > check:checked,
.theme-dark checkbutton > check:checked:hover {
  background: #3f9aa6;
  border-color: #3f9aa6;
  color: #ffffff;
}

.theme-dark popover > contents,
.theme-dark popover > arrow {
  background-color: #25272d;
  color: #eef1f5;
  border: 1px solid rgba(255, 255, 255, 0.10);
}
.theme-dark popover > contents {
  border-radius: 11px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.40);
  padding: 4px;
}
.theme-dark popover listview,
.theme-dark popover scrolledwindow,
.theme-dark popover .view {
  background-color: transparent;
  color: #eef1f5;
}
.theme-dark popover row {
  border-radius: 7px;
  color: #eef1f5;
  background-color: transparent;
}
.theme-dark popover row:selected,
.theme-dark popover row:hover { background-color: rgba(63, 154, 166, 0.30); color: #eaf6f7; }

.theme-dark entry,
.theme-dark spinbutton {
  background: #25272d;
  color: #eef1f5;
  border: 1px solid rgba(170, 178, 191, 0.24);
  border-radius: 9px;
  padding: 6px 10px;
}
.theme-dark entry:focus-within { border-color: #52aeba; }
.theme-dark dropdown > button {
  background: #25272d;
  border: 1px solid rgba(170, 178, 191, 0.24);
}

.theme-dark switch {
  background: rgba(255, 255, 255, 0.18);
  border-radius: 999px;
}
.theme-dark switch:checked { background: #3f9aa6; }
.theme-dark switch > slider { background: #f4f6fa; border-radius: 999px; }

.theme-dark .share-list > row {
  background: transparent;
}
.theme-dark .share-list > row:hover { background: rgba(255, 255, 255, 0.04); }
.theme-dark .share-list separator,
.theme-dark .share-list > row.separator { background: rgba(255, 255, 255, 0.08); }
"""


@dataclass(slots=True)
class HelperResult:
    ok: bool
    payload: dict


def status_text(result: HelperResult) -> str:
    if not result.ok:
        return "Error"
    if result.payload.get("mounted"):
        return "Mounted"
    if result.payload.get("mount_active") == "activating":
        return "Starting"
    if result.payload.get("automount_active") == "active":
        return "Ready"
    if result.payload.get("mode") == MountMode.ALWAYS.value and result.payload.get("mount_enabled") == "enabled":
        return "Enabled"
    if result.payload.get("automount_enabled") == "enabled":
        return "Enabled"
    return "Offline"


def status_css_class(text: str) -> str:
    return {
        "Mounted": "status-mounted",
        "Starting": "status-enabled",
        "Ready": "status-ready",
        "Enabled": "status-enabled",
        "Offline": "status-offline",
        "Error": "status-error",
    }[text]


THEME_OPTIONS = ["System", "Light", "Dark"]
THEME_VALUES = ["system", "light", "dark"]
MOUNT_MODE_OPTIONS = ["Mounts when opened", "Always mounted"]
MOUNT_MODE_VALUES = [MountMode.AUTOMOUNT, MountMode.ALWAYS]


def theme_index(theme: str) -> int:
    theme = normalize_theme(theme)
    return THEME_VALUES.index(theme)


def theme_from_index(index: int) -> str:
    if 0 <= index < len(THEME_VALUES):
        return THEME_VALUES[index]
    return "system"


def mount_mode_index(mode: MountMode) -> int:
    return MOUNT_MODE_VALUES.index(mode)


def mount_mode_from_index(index: int) -> MountMode:
    if 0 <= index < len(MOUNT_MODE_VALUES):
        return MOUNT_MODE_VALUES[index]
    return MountMode.AUTOMOUNT


def mount_mode_label(mode: MountMode) -> str:
    return "Always mounted" if mode == MountMode.ALWAYS else "Mounts when opened"


def format_helper_status(payload: dict, *, secret_tool_available: bool) -> str:
    version = payload.get("version", "unknown")
    requirements = payload.get("requirements")
    if not isinstance(requirements, dict):
        return f"Host helper is installed. Version: {version}. Requirements check needs a helper update."

    messages = [f"Host helper is installed. Version: {version}."]
    systemd = requirements.get("systemd", {})
    if isinstance(systemd, dict):
        state = systemd.get("state")
        if systemd.get("available"):
            if state and state not in {"running", "degraded", "unknown"}:
                messages.append(f"systemd is available, current state: {state}.")
        else:
            messages.append(f"systemd is not usable: {systemd.get('message') or state or 'unknown state'}.")

    groups = requirements.get("groups", {})
    missing = set(requirements.get("missing", []))
    for key, label in [("core", "Required"), ("smb", "SMB"), ("nfs", "NFS")]:
        group_missing = [name for name in groups.get(key, []) if name in missing]
        if group_missing:
            messages.append(f"{label} tools missing: {', '.join(group_missing)}.")

    if not secret_tool_available:
        messages.append("Secret storage tool missing in the app runtime: secret-tool.")

    if len(messages) == 1:
        messages.append("All checked host requirements are available.")
    return "\n".join(messages)


def light_gtk_theme_name(theme_name: str | None) -> str | None:
    """Return the light variant of a GTK theme name, or None.

    Kept for backwards compatibility / tests. The app paints its own light/dark
    palette via CSS and no longer relies on swapping the system theme name.
    """
    if not theme_name:
        return None
    for suffix in ("-dark", "-Dark", "_dark", "_Dark"):
        if theme_name.endswith(suffix):
            return theme_name[: -len(suffix)]
    if theme_name.lower().endswith(":dark"):
        return theme_name[:-5]
    return None


def error_message(payload: dict) -> str:
    error = payload.get("error", {})
    if isinstance(error, dict):
        message = error.get("message") or error.get("code")
        if message:
            return str(message)
    return "Unknown helper error"


def main() -> int:
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Gdk", "4.0")
        from gi.repository import Gdk, Gtk  # noqa: F401
    except (ImportError, ValueError) as exc:
        print(f"GTK 4 / PyGObject is required to run the GUI: {exc}", file=sys.stderr)
        return 2

    from .ui import run

    return run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
