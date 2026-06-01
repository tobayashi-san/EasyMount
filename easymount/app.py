from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass

from .constants import APP_ID, APP_NAME, ICON_NAME, SOURCE_ICON_DIR
from .host_install import install_host_helper
from .launcher import HelperLaunchError, helper_command
from .models import (
    MountMode,
    MountProfile,
    NFSVersion,
    ProfileType,
    default_mount_path,
    new_profile_id,
    validate_profile,
)
from .bookmarks import remove_file_browser_bookmarks, sync_file_browser_bookmarks
from .secret_store import SecretServiceStore, SecretStoreError
from .settings import SettingsStore, normalize_theme
from .storage import ProfileStore
from .unit import smb_requires_credentials


APP_CSS = """
.theme-light,
.theme-light .app-shell,
.theme-light .page,
.theme-light list,
.theme-light row,
.theme-light viewport {
  background-color: #f5f7fb;
  color: #1d2635;
}

.theme-light .topbar {
  background: #ffffff;
  color: #1d2635;
}

.theme-light label,
.theme-light image {
  color: #1d2635;
}

.theme-light .dim-label,
.theme-light .field-hint {
  color: #5d6878;
  opacity: 1;
}

.theme-light button {
  background: #ffffff;
  background-image: none;
  color: #1d2635;
  border-color: rgba(93, 104, 120, 0.34);
  box-shadow: none;
}

.theme-light button:hover {
  background: #edf1f7;
  background-image: none;
  color: #111827;
}

.theme-light button.header-button {
  background: transparent;
  border-color: transparent;
}

.theme-light button.header-button:hover {
  background: #e8edf5;
  background-image: none;
  border-color: transparent;
}

.theme-light button.header-button.tab-active {
  background: #dfe6f1;
  background-image: none;
  color: #111827;
  border-color: transparent;
}

.theme-light .segmented-control {
  background: #e5ebf4;
}

.theme-light button.segment-button {
  background: transparent;
  background-image: none;
  color: #3d4858;
  border-color: transparent;
}

.theme-light button.segment-button:hover {
  background: #f5f7fb;
  background-image: none;
  color: #111827;
}

.theme-light button.segment-button:checked {
  background: #ffffff;
  background-image: none;
  color: #111827;
  border-color: transparent;
}

.theme-light entry,
.theme-light dropdown button {
  background: #ffffff;
  background-image: none;
  color: #1d2635;
  border-color: rgba(93, 104, 120, 0.34);
}

.theme-dark,
.theme-dark .app-shell,
.theme-dark .page,
.theme-dark list,
.theme-dark row,
.theme-dark viewport {
  background-color: #1b1d22;
  color: #eef1f5;
}

.theme-dark .topbar {
  background: #25272d;
  color: #eef1f5;
}

.theme-dark label,
.theme-dark image {
  color: #eef1f5;
}

.theme-dark .dim-label,
.theme-dark .field-hint {
  color: #aab2bf;
  opacity: 1;
}

.theme-dark button {
  background: #25272d;
  background-image: none;
  color: #eef1f5;
  border-color: rgba(170, 178, 191, 0.24);
  box-shadow: none;
}

.theme-dark button:hover {
  background: #30333b;
  background-image: none;
}

.theme-dark button.header-button {
  background: transparent;
  border-color: transparent;
}

.theme-dark button.header-button:hover {
  background: #30333b;
  background-image: none;
  border-color: transparent;
}

.theme-dark button.header-button.tab-active {
  background: #373b44;
  background-image: none;
  color: #ffffff;
  border-color: transparent;
}

.theme-dark .segmented-control {
  background: #15171c;
}

.theme-dark button.segment-button {
  background: transparent;
  background-image: none;
  color: #c1c8d3;
  border-color: transparent;
}

.theme-dark button.segment-button:hover {
  background: #30333b;
  background-image: none;
  color: #ffffff;
}

.theme-dark button.segment-button:checked {
  background: #3a3e48;
  background-image: none;
  color: #ffffff;
  border-color: transparent;
}

.theme-dark entry,
.theme-dark dropdown button {
  background: #25272d;
  background-image: none;
  color: #eef1f5;
  border-color: rgba(170, 178, 191, 0.24);
}

.field-hint {
  opacity: 0.72;
  font-size: 0.88em;
}

.empty-state-row,
.empty-state-row:hover,
.empty-state-row:selected,
.share-row,
.share-row:hover,
.share-row:selected {
  background: transparent;
}

.nav-box {
  margin-left: 8px;
}

.header-actions {
  margin-right: 8px;
}

.topbar {
  padding: 8px 12px;
  border-bottom: 1px solid rgba(127, 127, 127, 0.18);
}

.header-button {
  border-color: transparent;
  box-shadow: none;
  background: transparent;
}

.header-button:hover {
  border-color: transparent;
  box-shadow: none;
  background-color: rgba(127, 127, 127, 0.10);
}

.header-button.tab-active {
  background-color: rgba(127, 127, 127, 0.14);
  font-weight: 600;
}

.header-button:focus,
.header-button:focus-visible,
.header-button:checked,
.header-button:active {
  border-color: transparent;
  box-shadow: none;
  outline-color: transparent;
}

.soft-action {
  border-color: rgba(127, 127, 127, 0.24);
  box-shadow: none;
}

.soft-action:hover,
.soft-action:focus,
.soft-action:focus-visible {
  border-color: rgba(127, 127, 127, 0.34);
  box-shadow: none;
  outline-color: transparent;
}

.settings-section {
  margin-top: 6px;
}

.settings-row {
  padding: 8px 0;
}

.settings-copy {
  min-width: 260px;
}

.segmented-control {
  border-radius: 8px;
  padding: 3px;
}

.segment-button {
  min-width: 92px;
  min-height: 34px;
  padding: 6px 12px;
  border-radius: 6px;
  box-shadow: none;
  outline-color: transparent;
}

.segment-button:focus,
.segment-button:focus-visible,
.segment-button:checked {
  box-shadow: none;
  outline-color: transparent;
}

.icon-action {
  min-width: 36px;
  min-height: 32px;
  padding: 6px;
}

.danger-icon {
  color: #b42318;
}

.share-status {
  min-width: 88px;
}

.status-pill {
  border-radius: 999px;
  padding: 4px 10px;
  font-weight: 600;
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
  color: #315f8a;
  background-color: rgba(49, 95, 138, 0.14);
}

.status-offline {
  color: #6b7280;
  background-color: rgba(107, 114, 128, 0.14);
}

.status-error {
  color: #9f1239;
  background-color: rgba(190, 18, 60, 0.14);
}

.share-kind {
  border-radius: 999px;
  padding: 3px 8px;
  font-size: 0.84em;
  font-weight: 600;
  background-color: rgba(90, 90, 90, 0.12);
}

.toolbar-title {
  font-weight: 700;
  font-size: 1.18em;
}

.app-title {
  font-weight: 700;
}

.page {
  padding: 22px;
}

.share-list {
  background: transparent;
}
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
MOUNT_MODE_OPTIONS = ["Mount when opened", "Always mounted"]
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
    if not theme_name:
        return None
    for suffix in ("-dark", "-Dark", "_dark", "_Dark"):
        if theme_name.endswith(suffix):
            return theme_name[: -len(suffix)]
    if theme_name.lower().endswith(":dark"):
        return theme_name[:-5]
    return None


def main() -> int:
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Gdk", "4.0")
        from gi.repository import Gdk, Gio, Gtk
    except (ImportError, ValueError) as exc:
        print(f"GTK 4 / PyGObject is required to run the GUI: {exc}", file=sys.stderr)
        return 2

    css_provider = Gtk.CssProvider()
    css_provider.load_from_data(APP_CSS.encode("utf-8"))
    display = Gdk.Display.get_default()
    if display is not None:
        Gtk.IconTheme.get_for_display(display).add_search_path(str(SOURCE_ICON_DIR))
        Gtk.Window.set_default_icon_name(ICON_NAME)
        Gtk.StyleContext.add_provider_for_display(
            display,
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def hint(text: str):
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class("field-hint")
        label.set_wrap(True)
        return label

    def form_row(label_text: str, widget, hint_text: str | None = None):
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        label = Gtk.Label(label=label_text, xalign=0)
        label.add_css_class("caption-heading")
        row.append(label)
        row.append(widget)
        if hint_text:
            row.append(hint(hint_text))
        return row

    def icon_button(icon_name: str, tooltip: str):
        button = Gtk.Button.new_from_icon_name(icon_name)
        button.add_css_class("icon-action")
        button.add_css_class("flat")
        button.set_tooltip_text(tooltip)
        return button

    class ShareDialog(Gtk.Window):
        def __init__(
            self,
            parent: "MainWindow",
            initial_type: ProfileType = ProfileType.SMB,
            profile: MountProfile | None = None,
        ) -> None:
            super().__init__(title="Edit network mount" if profile else "Add network mount")
            self.parent_window = parent
            self.original_profile = profile
            self.set_transient_for(parent)
            self.set_modal(True)
            self.set_default_size(560, 600)

            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            box.set_margin_top(16)
            box.set_margin_bottom(16)
            box.set_margin_start(16)
            box.set_margin_end(16)
            self.set_child(box)

            title = Gtk.Label(label="Edit SMB or NFS share" if profile else "Add SMB or NFS share", xalign=0)
            title.add_css_class("title-3")
            box.append(title)

            self.type_dropdown = Gtk.DropDown.new_from_strings(["SMB / Windows share", "NFS export"])
            selected_type = profile.type if profile else initial_type
            self.type_dropdown.set_selected(0 if selected_type is ProfileType.SMB else 1)
            box.append(
                form_row(
                    "Share type",
                    self.type_dropdown,
                    "SMB is typical for Windows, Samba and NAS shares. NFS is typical for Linux exports.",
                )
            )

            self.display = Gtk.Entry()
            self.server = Gtk.Entry()
            self.remote = Gtk.Entry()
            self.username = Gtk.Entry()
            self.domain = Gtk.Entry()
            self.password = Gtk.Entry()
            self.password.set_visibility(False)
            self.use_auth = Gtk.CheckButton(label="Use username/password")
            self.mount_mode = Gtk.DropDown.new_from_strings(MOUNT_MODE_OPTIONS)
            self.mount_mode.set_selected(mount_mode_index(profile.mount_mode) if profile else 0)

            self.version = Gtk.DropDown.new_from_strings(["4", "3"])
            if profile:
                self.display.set_text(profile.display_name)
                self.server.set_text(profile.server)
                self.remote.set_text(profile.remote_path)
                self.username.set_text(profile.username or "")
                self.domain.set_text(profile.domain or "")
                if profile.nfs_version is NFSVersion.V3:
                    self.version.set_selected(1)
                self.use_auth.set_active(profile.type is ProfileType.SMB and smb_requires_credentials(profile))

            name_hint = "Display name. Existing mount folders keep their current path." if profile else "Display name and folder name under ~/Network."
            box.append(form_row("Name", self.display, name_hint))
            box.append(form_row("Server", self.server, "Hostname or IP address only."))
            self.remote_row = form_row("Share", self.remote)
            box.append(self.remote_row)
            box.append(
                form_row(
                    "Mount behavior",
                    self.mount_mode,
                    "Use access-based mounting for normal shares. Use always mounted for video editing, media libraries or indexers.",
                )
            )
            self.auth_row = form_row("Authentication", self.use_auth, "Optional for public/guest shares.")
            box.append(self.auth_row)
            self.username_row = form_row("Username", self.username, "Optional. Leave auth fields empty for guest/public shares.")
            password_hint = "Leave empty to keep the saved password. Enter a new value to replace it." if profile and profile.password_saved else "Optional. Stored in Secret Service."
            self.password_row = form_row("Password", self.password, password_hint)
            self.domain_row = form_row("Domain / Workgroup", self.domain, "Optional. Usually empty on home networks.")
            self.version_row = form_row("NFS version", self.version, "Use v4 first. Try v3 when the server export requires it.")
            for row in [self.username_row, self.password_row, self.domain_row, self.version_row]:
                box.append(row)

            self.type_dropdown.connect("notify::selected", lambda *_: self._update_type())
            self.use_auth.connect("toggled", lambda *_: self._update_type())
            self._update_type()

            self.test_status = hint("")
            box.append(self.test_status)

            button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            button_box.set_halign(Gtk.Align.END)
            test = Gtk.Button(label="Test Connection")
            cancel = Gtk.Button(label="Cancel")
            save = Gtk.Button(label="Save mount")
            save.add_css_class("soft-action")
            test.connect("clicked", self._test)
            cancel.connect("clicked", lambda *_: self.close())
            save.connect("clicked", self._save)
            button_box.append(test)
            button_box.append(cancel)
            button_box.append(save)
            box.append(button_box)

        def selected_type(self) -> ProfileType:
            return ProfileType.SMB if self.type_dropdown.get_selected() == 0 else ProfileType.NFS

        def _update_type(self) -> None:
            share_type = self.selected_type()
            is_smb = share_type is ProfileType.SMB
            self.remote_row.get_first_child().set_label("SMB share name" if is_smb else "NFS export path")
            self.remote.set_placeholder_text("")
            self.remote.set_tooltip_text(
                "For SMB enter only the exported share name, not the server filesystem path."
                if is_smb
                else "For NFS enter the exported server path."
            )
            remote_hint = self.remote_row.get_last_child()
            if remote_hint is self.remote:
                remote_hint = hint("")
                self.remote_row.append(remote_hint)
            remote_hint.set_label(
                "Only the exported SMB share name, not a server path."
                if is_smb
                else "The exported NFS server path; it starts with /."
            )
            self.auth_row.set_visible(is_smb)
            show_auth_fields = is_smb and self.use_auth.get_active()
            for row in [self.username_row, self.password_row, self.domain_row]:
                row.set_visible(show_auth_fields)
            self.version_row.set_visible(not is_smb)

        def build_profile(self) -> tuple[MountProfile, str | None, bool]:
            share_type = self.selected_type()
            auth_enabled = share_type is ProfileType.SMB and self.use_auth.get_active()
            display_name = self.display.get_text().strip() or self.remote.get_text().strip() or self.server.get_text().strip()
            password = self.password.get_text() if auth_enabled else None
            keep_existing_password = bool(
                self.original_profile
                and self.original_profile.password_saved
                and auth_enabled
                and not password
            )
            profile = MountProfile(
                id=self.original_profile.id if self.original_profile else new_profile_id(display_name or self.remote.get_text().strip() or "share"),
                type=share_type,
                display_name=display_name,
                server=self.server.get_text().strip(),
                remote_path=self.remote.get_text().strip(),
                mount_path=self.original_profile.mount_path if self.original_profile else default_mount_path(display_name or self.remote.get_text().strip()),
                created_for_uid=self.original_profile.created_for_uid if self.original_profile else os.getuid(),
                created_for_gid=self.original_profile.created_for_gid if self.original_profile else os.getgid(),
                mount_mode=mount_mode_from_index(self.mount_mode.get_selected()),
                username=(self.username.get_text().strip() or None) if auth_enabled else None,
                domain=(self.domain.get_text().strip() or None) if auth_enabled else None,
                password_saved=bool(password) or keep_existing_password,
                nfs_version=NFSVersion(self.version.get_selected_item().get_string())
                if share_type is ProfileType.NFS
                else None,
            )
            return profile, password, keep_existing_password

        def _test(self, *_args: object) -> None:
            try:
                profile, password, keep_existing_password = self.build_profile()
                validate_profile(profile, user_home=os.path.expanduser("~"))
                result = self.parent_window.test_profile(
                    profile,
                    password,
                    old_profile=self.original_profile,
                    keep_existing_password=keep_existing_password,
                )
            except Exception as exc:  # noqa: BLE001 - GUI surface must show validation/helper details.
                self.test_status.set_label(str(exc))
                return
            self.test_status.set_label("Connection test passed." if result.ok else error_message(result.payload))

        def _save(self, *_args: object) -> None:
            try:
                profile, password, keep_existing_password = self.build_profile()
                validate_profile(profile, user_home=os.path.expanduser("~"))
                self.parent_window.save_profile(
                    profile,
                    password,
                    old_profile=self.original_profile,
                    keep_existing_password=keep_existing_password,
                )
            except Exception as exc:  # noqa: BLE001 - GUI surface must show helper details.
                self.parent_window.show_error(str(exc))
                return
            self.close()

    class MainWindow(Gtk.ApplicationWindow):
        def __init__(self, application: Gtk.Application) -> None:
            super().__init__(application=application, title=APP_NAME)
            self.set_icon_name(ICON_NAME)
            self.set_default_size(860, 560)
            self.store = ProfileStore()
            self.settings_store = SettingsStore()
            self.settings = self.settings_store.load()
            self.secret_store = SecretServiceStore()
            gtk_settings = Gtk.Settings.get_default()
            self.system_prefer_dark = (
                bool(gtk_settings.get_property("gtk-application-prefer-dark-theme"))
                if gtk_settings is not None
                else False
            )
            self.system_theme_name = (
                str(gtk_settings.get_property("gtk-theme-name") or "")
                if gtk_settings is not None
                else ""
            )

            root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            root.add_css_class("app-shell")
            self.root = root
            self.set_child(root)

            header = Gtk.CenterBox()
            header.add_css_class("topbar")
            title = Gtk.Label(label=APP_NAME)
            title.add_css_class("app-title")
            title.set_halign(Gtk.Align.CENTER)

            nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            nav.add_css_class("nav-box")
            shares = Gtk.Button(label="Shares")
            settings = Gtk.Button(label="Settings")
            info = Gtk.Button(label="Info")
            for button in [shares, settings, info]:
                button.add_css_class("header-button")
            nav.append(shares)
            nav.append(settings)
            nav.append(info)
            self.nav_buttons = {
                "shares": shares,
                "settings": settings,
                "info": info,
            }

            tools = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            tools.add_css_class("header-actions")
            refresh = icon_button("view-refresh-symbolic", "Refresh")
            refresh.add_css_class("header-button")
            tools.append(refresh)

            shares.connect("clicked", lambda *_: self.stack.set_visible_child_name("shares"))
            refresh.connect("clicked", lambda *_: self.reload())
            settings.connect("clicked", lambda *_: self.stack.set_visible_child_name("settings"))
            info.connect("clicked", lambda *_: self.stack.set_visible_child_name("info"))
            header.set_start_widget(nav)
            header.set_center_widget(title)
            header.set_end_widget(tools)
            root.append(header)

            self.stack = Gtk.Stack()
            self.stack.set_vexpand(True)
            root.append(self.stack)

            self.stack.add_named(self.build_shares_page(), "shares")
            self.stack.add_named(self.build_settings_page(), "settings")
            self.stack.add_named(self.build_info_page(), "info")
            self.stack.connect("notify::visible-child-name", lambda *_: self.update_nav_tabs())
            self.stack.set_visible_child_name("shares")
            self.update_nav_tabs()
            self.apply_theme()
            self.reload()

        def update_nav_tabs(self) -> None:
            active = self.stack.get_visible_child_name()
            for name, button in self.nav_buttons.items():
                if name == active:
                    button.add_css_class("tab-active")
                else:
                    button.remove_css_class("tab-active")

        def build_theme_control(self):
            control = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
            control.add_css_class("segmented-control")
            control.set_halign(Gtk.Align.START)

            self.theme_buttons = {}
            group = None
            for label, value in zip(THEME_OPTIONS, THEME_VALUES, strict=True):
                button = Gtk.ToggleButton(label=label)
                button.add_css_class("segment-button")
                if group is None:
                    group = button
                else:
                    button.set_group(group)
                control.append(button)
                self.theme_buttons[value] = button

            self.theme_buttons[normalize_theme(self.settings.theme)].set_active(True)
            for value, button in self.theme_buttons.items():
                button.connect("toggled", self.on_theme_button_toggled, value)
            return control

        def build_shares_page(self):
            page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
            page.add_css_class("page")

            top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            title = Gtk.Label(label="Network mounts", xalign=0)
            title.add_css_class("toolbar-title")
            subtitle = hint("Shares mount automatically when opened. Use Edit to change details or Delete to remove the mount.")
            copy.append(title)
            copy.append(subtitle)
            copy.set_hexpand(True)
            top.append(copy)

            add = Gtk.Button(label="Add Share")
            add.add_css_class("soft-action")
            add.connect("clicked", lambda *_: ShareDialog(self).present())
            top.append(add)
            page.append(top)

            self.list_box = Gtk.ListBox()
            self.list_box.add_css_class("share-list")
            self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
            self.list_box.set_vexpand(True)
            page.append(self.list_box)
            return page

        def build_settings_page(self):
            page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
            page.add_css_class("page")

            title = Gtk.Label(label="Settings", xalign=0)
            title.add_css_class("title-2")
            page.append(title)

            def settings_row(title_text: str, hint_text: str, control):
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
                row.add_css_class("settings-row")
                copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
                copy.add_css_class("settings-copy")
                copy.set_hexpand(True)
                label = Gtk.Label(label=title_text, xalign=0)
                label.add_css_class("heading")
                copy.append(label)
                copy.append(hint(hint_text))
                control.set_valign(Gtk.Align.CENTER)
                row.append(copy)
                row.append(control)
                return row

            appearance = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            appearance.add_css_class("settings-section")
            appearance_title = Gtk.Label(label="Appearance", xalign=0)
            appearance_title.add_css_class("heading")
            appearance.append(appearance_title)
            appearance.append(
                settings_row(
                    "Theme",
                    "System follows your desktop. Light and Dark force the EasyMount interface style.",
                    self.build_theme_control(),
                )
            )
            page.append(appearance)

            helper_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            helper_section.add_css_class("settings-section")
            helper_title = Gtk.Label(label="Host helper", xalign=0)
            helper_title.add_css_class("heading")
            helper_section.append(helper_title)
            helper_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            helper_actions.set_halign(Gtk.Align.START)
            check_helper = Gtk.Button(label="Check Helper")
            check_helper.add_css_class("soft-action")
            install_helper = Gtk.Button(label="Install / Update Helper")
            install_helper.add_css_class("soft-action")
            check_helper.connect("clicked", lambda *_: self.check_host_helper())
            install_helper.connect("clicked", lambda *_: self.install_host_helper())
            helper_actions.append(check_helper)
            helper_actions.append(install_helper)
            helper_section.append(
                settings_row(
                    "System integration",
                    "Required for Flatpak, AppImage and normal installs to create or remove systemd mount units.",
                    helper_actions,
                )
            )
            self.helper_status = hint("")
            helper_section.append(self.helper_status)
            page.append(helper_section)

            section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            section.add_css_class("settings-section")
            section_title = Gtk.Label(label="File browser sidebar", xalign=0)
            section_title.add_css_class("heading")
            section.append(section_title)

            self.sidebar_check = Gtk.CheckButton(label="Show mounted shares in the file browser sidebar")
            self.sidebar_check.set_active(self.settings.show_in_file_browser)
            self.sidebar_check.connect("toggled", self.on_sidebar_setting_toggled)
            section.append(self.sidebar_check)
            section.append(hint("Adds the ~/Network mount folders to GNOME Files and GTK file pickers. Dolphin support is best-effort through KDE Places."))

            sync_button = Gtk.Button(label="Sync Sidebar Entries")
            sync_button.add_css_class("soft-action")
            sync_button.set_halign(Gtk.Align.START)
            sync_button.connect("clicked", lambda *_: self.sync_sidebar_entries(show_success=True))
            section.append(sync_button)

            self.settings_status = hint("")
            section.append(self.settings_status)
            page.append(section)
            return page

        def build_info_page(self):
            page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
            page.add_css_class("page")

            title = Gtk.Label(label="Info", xalign=0)
            title.add_css_class("title-2")
            page.append(title)

            summary = Gtk.Label(
                label=(
                    "EasyMount creates systemd automount units for SMB and NFS shares instead of editing fstab. "
                    "Profiles stay in your user config, SMB passwords stay in Secret Service, and privileged mount changes go through Polkit."
                ),
                xalign=0,
            )
            summary.set_wrap(True)
            page.append(summary)

            link = Gtk.LinkButton(uri="https://github.com/tobayashi-san/EasyMount", label="GitHub project")
            link.set_halign(Gtk.Align.START)
            page.append(link)
            page.append(hint("The GitHub page will contain setup details, troubleshooting and the helper design."))
            return page

        def reload(self) -> None:
            child = self.list_box.get_first_child()
            while child is not None:
                next_child = child.get_next_sibling()
                self.list_box.remove(child)
                child = next_child
            profiles = self.store.load()
            if not profiles:
                row = Gtk.ListBoxRow()
                row.add_css_class("empty-state-row")
                row.set_activatable(False)
                row.set_selectable(False)
                empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
                empty.set_margin_top(48)
                empty.set_margin_bottom(48)
                empty.set_margin_start(24)
                empty.set_margin_end(24)
                empty.set_halign(Gtk.Align.CENTER)
                title = Gtk.Label(label="No network mounts yet")
                title.add_css_class("title-3")
                subtitle = hint("Add an SMB share or NFS export to mount it under ~/Network.")
                subtitle.set_justify(Gtk.Justification.CENTER)
                button = Gtk.Button(label="Add Share")
                button.add_css_class("soft-action")
                button.connect("clicked", lambda *_: ShareDialog(self).present())
                empty.append(title)
                empty.append(subtitle)
                empty.append(button)
                row.set_child(empty)
                self.list_box.append(row)
                return
            for profile in profiles:
                self.list_box.append(self._row(profile))

        def _row(self, profile: MountProfile):
            row = Gtk.ListBoxRow()
            row.add_css_class("share-row")
            row.set_activatable(False)
            row.set_selectable(False)

            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
            box.set_margin_top(12)
            box.set_margin_bottom(12)
            box.set_margin_start(14)
            box.set_margin_end(14)
            row.set_child(box)

            icon = Gtk.Image.new_from_icon_name("network-server-symbolic")
            icon.set_pixel_size(28)
            box.append(icon)

            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            title = Gtk.Label(label=profile.display_name, xalign=0)
            title.add_css_class("heading")
            kind = Gtk.Label(label=profile.type.value.upper())
            kind.add_css_class("share-kind")
            heading.append(title)
            heading.append(kind)
            remote = Gtk.Label(label=f"{profile.type.value.upper()} {profile.server}:{profile.remote_path}", xalign=0)
            remote.add_css_class("dim-label")
            mode = Gtk.Label(label=mount_mode_label(profile.mount_mode), xalign=0)
            mode.add_css_class("dim-label")
            mount_path = Gtk.Label(label=profile.mount_path, xalign=0)
            mount_path.add_css_class("dim-label")
            text.append(heading)
            text.append(remote)
            text.append(mode)
            text.append(mount_path)
            text.set_hexpand(True)
            box.append(text)

            status = self.helper("status", profile)
            status_label = status_text(status)
            status_widget = Gtk.Label(label=status_label)
            status_widget.set_valign(Gtk.Align.CENTER)
            status_widget.add_css_class("share-status")
            status_widget.add_css_class("status-pill")
            status_widget.add_css_class(status_css_class(status_label))
            box.append(status_widget)

            edit_btn = icon_button("document-edit-symbolic", "Edit share")
            delete_btn = icon_button("user-trash-symbolic", "Delete share")
            for button in [edit_btn, delete_btn]:
                button.set_size_request(38, -1)
                button.set_valign(Gtk.Align.CENTER)
            delete_btn.add_css_class("danger-icon")
            edit_btn.connect("clicked", lambda *_: ShareDialog(self, profile.type, profile=profile).present())
            delete_btn.connect("clicked", lambda *_: self.delete_profile(profile))
            actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            actions.append(edit_btn)
            actions.append(delete_btn)
            box.append(actions)
            return row

        def profile_secret_payload(
            self,
            profile: MountProfile,
            password: str | None,
            *,
            old_profile: MountProfile | None = None,
            keep_existing_password: bool = False,
        ) -> dict:
            if profile.type is not ProfileType.SMB or not smb_requires_credentials(profile):
                return {}
            if password:
                return {"secret": password}
            if keep_existing_password and old_profile:
                secret = self.secret_store.lookup(old_profile.id)
                if not secret:
                    raise RuntimeError("No saved SMB password found. Enter a new password and test again.")
                return {"secret": secret}
            return {"secret": ""}

        def test_profile(
            self,
            profile: MountProfile,
            password: str | None,
            *,
            old_profile: MountProfile | None = None,
            keep_existing_password: bool = False,
        ) -> HelperResult:
            payload_extra = self.profile_secret_payload(
                profile,
                password,
                old_profile=old_profile,
                keep_existing_password=keep_existing_password,
            )
            return self.helper("test-connection", profile, privileged=True, extra=payload_extra)

        def save_profile(
            self,
            profile: MountProfile,
            password: str | None,
            *,
            old_profile: MountProfile | None = None,
            keep_existing_password: bool = False,
        ) -> None:
            payload_extra = self.profile_secret_payload(
                profile,
                password,
                old_profile=old_profile,
                keep_existing_password=keep_existing_password,
            )
            if profile.type is ProfileType.SMB and password:
                self.secret_store.store(profile.id, password, label=f"EasyMount {profile.display_name}")
            result = self.helper("install-mount", profile, privileged=True, extra=payload_extra)
            if not result.ok:
                if profile.type is ProfileType.SMB and password:
                    self.secret_store.clear(profile.id)
                raise RuntimeError(error_message(result.payload))
            if old_profile and (old_profile.type is not ProfileType.SMB or not profile.password_saved) and old_profile.password_saved:
                self.secret_store.clear(old_profile.id)
            self.store.upsert(profile)
            self.sync_sidebar_entries()
            self.reload()

        def delete_profile(self, profile: MountProfile) -> None:
            result = self.helper("remove-mount", profile, privileged=True)
            if not result.ok:
                self.show_error(error_message(result.payload))
                return
            if profile.type is ProfileType.SMB and profile.password_saved:
                try:
                    self.secret_store.clear(profile.id)
                except SecretStoreError:
                    pass
            remove_file_browser_bookmarks([profile])
            self.store.delete(profile.id)
            self.reload()

        def on_sidebar_setting_toggled(self, *_args: object) -> None:
            self.settings.show_in_file_browser = self.sidebar_check.get_active()
            self.settings_store.save(self.settings)
            self.sync_sidebar_entries(show_success=True)

        def on_theme_button_toggled(self, button, theme: str) -> None:
            if not button.get_active():
                return
            self.settings.theme = normalize_theme(theme)
            self.settings_store.save(self.settings)
            self.apply_theme()

        def apply_theme(self) -> None:
            theme = normalize_theme(self.settings.theme)
            for class_name in ["theme-light", "theme-dark"]:
                self.root.remove_css_class(class_name)
                self.remove_css_class(class_name)
            gtk_settings = Gtk.Settings.get_default()
            if gtk_settings is None:
                return
            if theme == "light":
                self.root.add_css_class("theme-light")
                self.add_css_class("theme-light")
                light_name = light_gtk_theme_name(self.system_theme_name)
                if light_name:
                    gtk_settings.set_property("gtk-theme-name", light_name)
                gtk_settings.set_property("gtk-application-prefer-dark-theme", False)
            elif theme == "dark":
                self.root.add_css_class("theme-dark")
                self.add_css_class("theme-dark")
                if self.system_theme_name:
                    gtk_settings.set_property("gtk-theme-name", self.system_theme_name)
                gtk_settings.set_property("gtk-application-prefer-dark-theme", True)
            else:
                if self.system_theme_name:
                    gtk_settings.set_property("gtk-theme-name", self.system_theme_name)
                gtk_settings.set_property("gtk-application-prefer-dark-theme", self.system_prefer_dark)

        def sync_sidebar_entries(self, *, show_success: bool = False) -> None:
            try:
                result = sync_file_browser_bookmarks(
                    self.store.load(),
                    enabled=self.settings.show_in_file_browser,
                )
            except (OSError, ValueError) as exc:
                if hasattr(self, "settings_status"):
                    self.settings_status.set_label(str(exc))
                return
            if show_success and hasattr(self, "settings_status"):
                if result["gtk"] and result["kde"]:
                    if result.get("icons"):
                        self.settings_status.set_label("Sidebar entries and network icons updated.")
                    else:
                        self.settings_status.set_label("Sidebar entries updated. Custom network icons are not supported on this desktop.")
                elif result["gtk"]:
                    self.settings_status.set_label("GTK sidebar entries updated. KDE Places could not be updated.")
                else:
                    self.settings_status.set_label("Sidebar entries could not be updated.")

        def check_host_helper(self) -> None:
            result = self.call_helper("self-check")
            if not hasattr(self, "helper_status"):
                return
            if result.ok:
                self.helper_status.set_label(
                    format_helper_status(
                        result.payload,
                        secret_tool_available=self.secret_store.available(),
                    )
                )
            else:
                self.helper_status.set_label(f"Host helper is not ready: {error_message(result.payload)}")

        def install_host_helper(self) -> None:
            if hasattr(self, "helper_status"):
                self.helper_status.set_label("Starting host helper installer...")
            try:
                result = install_host_helper()
            except OSError as exc:
                if hasattr(self, "helper_status"):
                    self.helper_status.set_label(str(exc))
                return
            if result.returncode == 0:
                if hasattr(self, "helper_status"):
                    self.helper_status.set_label("Host helper installed or updated.")
                self.check_host_helper()
                return
            message = result.stderr.strip() or result.stdout.strip() or f"Installer failed with exit code {result.returncode}"
            if hasattr(self, "helper_status"):
                self.helper_status.set_label(message)

        def helper_or_error(
            self,
            command: str,
            profile: MountProfile,
            *,
            privileged: bool = True,
            extra: dict | None = None,
        ) -> None:
            result = self.helper(command, profile, privileged=privileged, extra=extra)
            if not result.ok:
                self.show_error(error_message(result.payload))
            self.reload()

        def helper(
            self,
            command: str,
            profile: MountProfile,
            *,
            privileged: bool = False,
            extra: dict | None = None,
        ) -> HelperResult:
            payload = {"profile": profile.to_dict()}
            if extra:
                payload.update(extra)
            return self.call_helper(command, payload=payload, privileged=privileged)

        def call_helper(
            self,
            command: str,
            *,
            payload: dict | None = None,
            privileged: bool = False,
        ) -> HelperResult:
            payload = payload or {}
            try:
                cmd = helper_command(command, privileged=privileged)
            except HelperLaunchError as exc:
                return HelperResult(False, {"error": {"message": str(exc)}})
            try:
                result = subprocess.run(
                    cmd,
                    input=json.dumps(payload),
                    text=True,
                    capture_output=True,
                    check=False,
                )
            except OSError as exc:
                return HelperResult(False, {"error": {"message": str(exc)}})
            try:
                parsed = json.loads(result.stdout or "{}")
            except json.JSONDecodeError:
                parsed = {
                    "error": {
                        "message": result.stderr.strip()
                        or result.stdout.strip()
                        or f"Helper command failed with exit code {result.returncode}",
                        "returncode": result.returncode,
                    }
                }
            if result.returncode != 0 and not parsed.get("error"):
                parsed["error"] = {
                    "message": result.stderr.strip() or f"Helper command failed with exit code {result.returncode}",
                    "returncode": result.returncode,
                }
            return HelperResult(result.returncode == 0 and parsed.get("ok", False), parsed)

        def show_error(self, message: str) -> None:
            if hasattr(Gtk, "AlertDialog"):
                dialog = Gtk.AlertDialog(message=message)
                dialog.show(self)
                return
            dialog = Gtk.MessageDialog(
                transient_for=self,
                modal=True,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text=message,
            )
            dialog.connect("response", lambda dialog, *_: dialog.destroy())
            dialog.present()

    class Application(Gtk.Application):
        def __init__(self) -> None:
            super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

        def do_activate(self) -> None:
            window = self.get_active_window()
            if window is None:
                window = MainWindow(self)
            window.present()

    app = Application()
    return app.run(sys.argv)


def error_message(payload: dict) -> str:
    error = payload.get("error", {})
    if isinstance(error, dict):
        message = error.get("message") or error.get("code")
        if message:
            return str(message)
    return "Unknown helper error"


if __name__ == "__main__":
    raise SystemExit(main())
