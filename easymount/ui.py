from __future__ import annotations

import json
import os
import subprocess
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from .app import (  # noqa: E402
    APP_CSS,
    HelperResult,
    MOUNT_MODE_OPTIONS,
    THEME_OPTIONS,
    error_message,
    format_helper_status,
    mount_mode_from_index,
    mount_mode_index,
    mount_mode_label,
    status_css_class,
    status_text,
    theme_from_index,
    theme_index,
)
from .bookmarks import remove_file_browser_bookmarks, sync_file_browser_bookmarks  # noqa: E402
from .constants import APP_ID, APP_NAME, ICON_NAME, SOURCE_ICON_DIR  # noqa: E402
from .host_install import install_host_helper  # noqa: E402
from .launcher import HelperLaunchError, helper_command  # noqa: E402
from .models import (  # noqa: E402
    MountProfile,
    NFSVersion,
    ProfileType,
    default_mount_path,
    new_profile_id,
    validate_profile,
)
from .secret_store import SecretServiceStore, SecretStoreError, migrate_legacy_secrets  # noqa: E402
from .settings import SettingsStore, normalize_theme  # noqa: E402
from .storage import ProfileStore  # noqa: E402
from .unit import smb_requires_credentials  # noqa: E402


_PILL_CLASSES = [
    "status-mounted",
    "status-ready",
    "status-enabled",
    "status-offline",
    "status-error",
    "status-checking",
]


def _run_async(work, done) -> None:
    """Run ``work`` in a worker thread; deliver result to ``done`` on the main loop.

    ``work`` must not touch any GTK widgets. ``done(kind, value)`` runs on the
    main loop with kind ``"ok"`` and the return value, or kind ``"err"`` and the
    raised exception.
    """

    def runner() -> None:
        try:
            payload = ("ok", work())
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI thread.
            payload = ("err", exc)

        def deliver() -> bool:
            done(*payload)
            return False

        GLib.idle_add(deliver)

    threading.Thread(target=runner, daemon=True).start()


def call_helper(command: str, *, payload: dict | None = None, privileged: bool = False) -> HelperResult:
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


def _set_theme_class(widget: Gtk.Widget, theme_class: str) -> None:
    """Apply exactly one of our theme classes (or none for system theme)."""
    for css in ("theme-light", "theme-dark"):
        widget.remove_css_class(css)
    if theme_class:
        widget.add_css_class(theme_class)


def _hint(text: str) -> Gtk.Label:
    label = Gtk.Label(label=text, xalign=0)
    label.add_css_class("field-hint")
    label.set_wrap(True)
    return label


def _form_row(label_text: str, widget: Gtk.Widget, hint_text: str | None = None) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    label = Gtk.Label(label=label_text, xalign=0)
    label.add_css_class("field-label")
    box.append(label)
    box.append(widget)
    if hint_text:
        box.append(_hint(hint_text))
    return box


def _icon_button(icon_name: str, tooltip: str) -> Gtk.Button:
    button = Gtk.Button(icon_name=icon_name)
    button.add_css_class("flat")
    button.set_valign(Gtk.Align.CENTER)
    button.set_tooltip_text(tooltip)
    return button


class StatusPill(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.set_valign(Gtk.Align.CENTER)
        self.spinner = Gtk.Spinner()
        self.spinner.set_visible(False)
        self.label = Gtk.Label()
        self.label.add_css_class("status-pill")
        self.append(self.spinner)
        self.append(self.label)

    def _set_class(self, css: str) -> None:
        for name in _PILL_CLASSES:
            self.label.remove_css_class(name)
        self.label.add_css_class(css)

    def set_checking(self) -> None:
        self.spinner.set_visible(True)
        self.spinner.start()
        self._set_class("status-checking")
        self.label.set_text("Checking")
        self.set_tooltip_text(None)

    def set_result(self, result: HelperResult) -> None:
        self.spinner.stop()
        self.spinner.set_visible(False)
        text = status_text(result)
        self._set_class(status_css_class(text))
        self.label.set_text(text)
        self.set_tooltip_text(error_message(result.payload) if not result.ok else None)


class ShareDialog(Gtk.Window):
    def __init__(
        self,
        parent: "MainWindow",
        initial_type: ProfileType = ProfileType.SMB,
        profile: MountProfile | None = None,
    ) -> None:
        super().__init__(
            title="Edit network mount" if profile else "Add network mount",
            transient_for=parent,
            modal=True,
        )
        self.parent_window = parent
        self.original_profile = profile
        self.set_default_size(540, 660)

        # No custom titlebar: keep the native window manager decorations.
        # Cancel / Save live in a bottom action bar inside the content.
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(root)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        root.append(scrolled)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.add_css_class("page")
        scrolled.set_child(box)

        self.type_dropdown = Gtk.DropDown.new_from_strings(["SMB / Windows share", "NFS export"])
        selected_type = profile.type if profile else initial_type
        self.type_dropdown.set_selected(0 if selected_type is ProfileType.SMB else 1)
        box.append(
            _form_row(
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
        self.password = Gtk.PasswordEntry()
        self.password.set_show_peek_icon(True)
        self.use_auth = Gtk.CheckButton(label="Use username / password")
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

        name_hint = (
            "Display name. Existing mount folders keep their current path."
            if profile
            else "Display name and folder name under ~/Network."
        )
        box.append(_form_row("Name", self.display, name_hint))
        box.append(_form_row("Server", self.server, "Hostname or IP address only."))
        self.remote_row = _form_row("Share", self.remote)
        box.append(self.remote_row)
        box.append(
            _form_row(
                "Mount behavior",
                self.mount_mode,
                "Use systemd automount for normal shares. Use always mounted for video editing, "
                "media libraries or indexers.",
            )
        )
        self.auth_row = _form_row("Authentication", self.use_auth, "Optional for public/guest shares.")
        box.append(self.auth_row)
        self.username_row = _form_row(
            "Username", self.username, "Optional. Leave auth fields empty for guest/public shares."
        )
        password_hint = (
            "Leave empty to keep the saved password. Enter a new value to replace it."
            if profile and profile.password_saved
            else "Optional. Stored in Secret Service."
        )
        self.password_row = _form_row("Password", self.password, password_hint)
        self.domain_row = _form_row("Domain / Workgroup", self.domain, "Optional. Usually empty on home networks.")
        self.version_row = _form_row("NFS version", self.version, "Use v4 first. Try v3 when the server export requires it.")
        for row in (self.username_row, self.password_row, self.domain_row, self.version_row):
            box.append(row)

        self.type_dropdown.connect("notify::selected", lambda *_: self._update_type())
        self.use_auth.connect("toggled", lambda *_: self._update_type())
        self._update_type()

        test_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        test = Gtk.Button(label="Test Connection")
        test.connect("clicked", self._on_test)
        test_box.append(test)
        box.append(test_box)

        self.test_status = _hint("")
        box.append(self.test_status)

        action_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        action_bar.add_css_class("dialog-action-bar")
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: self.close())
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        self.save_btn = Gtk.Button(label="Save")
        self.save_btn.add_css_class("suggested-action")
        self.save_btn.connect("clicked", self._on_save)
        action_bar.append(cancel)
        action_bar.append(spacer)
        action_bar.append(self.save_btn)
        root.append(action_bar)

        _set_theme_class(self, getattr(parent, "_effective_theme", ""))

    def selected_type(self) -> ProfileType:
        return ProfileType.SMB if self.type_dropdown.get_selected() == 0 else ProfileType.NFS

    def _update_type(self) -> None:
        is_smb = self.selected_type() is ProfileType.SMB
        self.remote_row.get_first_child().set_label("SMB share name" if is_smb else "NFS export path")
        self.remote.set_tooltip_text(
            "For SMB enter only the exported share name, not the server filesystem path."
            if is_smb
            else "For NFS enter the exported server path."
        )
        self.auth_row.set_visible(is_smb)
        show_auth_fields = is_smb and self.use_auth.get_active()
        for row in (self.username_row, self.password_row, self.domain_row):
            row.set_visible(show_auth_fields)
        self.version_row.set_visible(not is_smb)

    def build_profile(self) -> tuple[MountProfile, str | None, bool]:
        share_type = self.selected_type()
        auth_enabled = share_type is ProfileType.SMB and self.use_auth.get_active()
        display_name = (
            self.display.get_text().strip()
            or self.remote.get_text().strip()
            or self.server.get_text().strip()
        )
        password = self.password.get_text() if auth_enabled else None
        keep_existing_password = bool(
            self.original_profile
            and self.original_profile.password_saved
            and auth_enabled
            and not password
        )
        profile = MountProfile(
            id=self.original_profile.id
            if self.original_profile
            else new_profile_id(display_name or self.remote.get_text().strip() or "share"),
            type=share_type,
            display_name=display_name,
            server=self.server.get_text().strip(),
            remote_path=self.remote.get_text().strip(),
            mount_path=self.original_profile.mount_path
            if self.original_profile
            else default_mount_path(display_name or self.remote.get_text().strip()),
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

    def _on_test(self, *_args: object) -> None:
        try:
            profile, password, keep = self.build_profile()
            validate_profile(profile, user_home=os.path.expanduser("~"))
        except Exception as exc:  # noqa: BLE001 - validation surface.
            self.test_status.set_label(str(exc))
            return
        self.test_status.set_label("Testing connection…")

        def work() -> HelperResult:
            return self.parent_window.test_profile(
                profile,
                password,
                old_profile=self.original_profile,
                keep_existing_password=keep,
            )

        def done(kind: str, value: object) -> None:
            if kind == "err":
                self.test_status.set_label(str(value))
                return
            result = value  # type: ignore[assignment]
            self.test_status.set_label(
                "Connection test passed." if result.ok else error_message(result.payload)
            )

        _run_async(work, done)

    def _on_save(self, *_args: object) -> None:
        try:
            profile, password, keep = self.build_profile()
            validate_profile(profile, user_home=os.path.expanduser("~"))
        except Exception as exc:  # noqa: BLE001 - validation surface.
            self.parent_window.show_error(str(exc))
            return
        self.save_btn.set_sensitive(False)
        self.test_status.set_label("Saving…")

        def work() -> None:
            self.parent_window.save_profile(
                profile,
                password,
                old_profile=self.original_profile,
                keep_existing_password=keep,
            )

        def done(kind: str, value: object) -> None:
            if kind == "err":
                self.save_btn.set_sensitive(True)
                self.test_status.set_label(str(value))
                self.parent_window.show_error(str(value))
                return
            self.parent_window.toast("Mount saved.")
            self.parent_window.reload()
            self.close()

        _run_async(work, done)


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application) -> None:
        super().__init__(application=application, title=APP_NAME)
        self.set_icon_name(ICON_NAME)
        self.set_default_size(780, 520)
        self.set_size_request(420, 420)

        self.store = ProfileStore()
        self.settings_store = SettingsStore()
        self.settings = self.settings_store.load()
        self.secret_store = SecretServiceStore()
        migrate_legacy_secrets(self.store.load(), self.secret_store)

        self._reload_generation = 0
        self._toast_timeout = 0
        self._effective_theme = ""

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_vexpand(True)

        # No GtkHeaderBar / set_titlebar: the window keeps the native window
        # manager titlebar (server-side decorations on KDE/KWin). The tab
        # switcher and refresh action live inside the window content instead.
        # Individual ToggleButtons (instead of a GtkStackSwitcher) render as
        # normal bordered buttons in every theme, including the native one.
        topbar = Gtk.CenterBox()
        topbar.add_css_class("app-topbar")
        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        nav.add_css_class("app-nav")
        nav.set_valign(Gtk.Align.CENTER)
        self._nav_buttons: dict[str, Gtk.ToggleButton] = {}
        nav_group: Gtk.ToggleButton | None = None
        for name, label in (("shares", "Shares"), ("settings", "Settings"), ("info", "Info")):
            button = Gtk.ToggleButton(label=label)
            if nav_group is None:
                nav_group = button
            else:
                button.set_group(nav_group)
            button.connect("toggled", self._on_nav_toggled, name)
            nav.append(button)
            self._nav_buttons[name] = button
        topbar.set_start_widget(nav)
        title = Gtk.Label(label=APP_NAME)
        title.add_css_class("topbar-title")
        topbar.set_center_widget(title)
        refresh = _icon_button("view-refresh-symbolic", "Refresh")
        refresh.connect("clicked", lambda *_: self.reload())
        refresh.set_valign(Gtk.Align.CENTER)
        topbar.set_end_widget(refresh)

        self.stack.add_titled(self.build_shares_page(), "shares", "Shares")
        self.stack.add_titled(self.build_settings_page(), "settings", "Settings")
        self.stack.add_titled(self.build_info_page(), "info", "Info")
        self._nav_buttons["shares"].set_active(True)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.append(topbar)
        content.append(self.stack)

        overlay = Gtk.Overlay()
        overlay.set_child(content)
        self.toast_revealer = Gtk.Revealer()
        self.toast_revealer.set_halign(Gtk.Align.CENTER)
        self.toast_revealer.set_valign(Gtk.Align.END)
        self.toast_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)
        self.toast_revealer.set_can_target(False)
        self._toast_label = Gtk.Label()
        toast_box = Gtk.Box()
        toast_box.add_css_class("app-toast")
        toast_box.append(self._toast_label)
        self.toast_revealer.set_child(toast_box)
        overlay.add_overlay(self.toast_revealer)
        self.set_child(overlay)

        self.apply_theme()
        self.reload()

    def _on_nav_toggled(self, button: Gtk.ToggleButton, name: str) -> None:
        if button.get_active():
            self.stack.set_visible_child_name(name)

    # -- pages ---------------------------------------------------------------

    def build_shares_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        page.add_css_class("page")

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        title = Gtk.Label(label="Network mounts", xalign=0)
        title.add_css_class("page-title")
        subtitle = _hint("Shares mount automatically on access. Use the actions to edit or remove a mount.")
        copy.append(title)
        copy.append(subtitle)
        copy.set_hexpand(True)
        top.append(copy)

        add = Gtk.Button(label="Add Share")
        add.add_css_class("suggested-action")
        add.set_valign(Gtk.Align.CENTER)
        add.connect("clicked", lambda *_: self.open_share_dialog())
        top.append(add)
        page.append(top)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        self.list_box = Gtk.ListBox()
        self.list_box.add_css_class("share-list")
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.set_show_separators(True)
        self.list_box.set_valign(Gtk.Align.START)
        scrolled.set_child(self.list_box)
        page.append(scrolled)
        return page

    def build_settings_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        page.add_css_class("page")

        def settings_row(title_text: str, hint_text: str, control: Gtk.Widget) -> Gtk.Box:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
            copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            copy.set_hexpand(True)
            label = Gtk.Label(label=title_text, xalign=0)
            label.add_css_class("field-label")
            copy.append(label)
            copy.append(_hint(hint_text))
            control.set_valign(Gtk.Align.CENTER)
            row.append(copy)
            row.append(control)
            return row

        # Appearance
        appearance = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        appearance_title = Gtk.Label(label="Appearance", xalign=0)
        appearance_title.add_css_class("section-title")
        appearance.append(appearance_title)
        theme_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        theme_box.set_valign(Gtk.Align.CENTER)
        self._theme_buttons: list[Gtk.ToggleButton] = []
        theme_group: Gtk.ToggleButton | None = None
        for index, label in enumerate(THEME_OPTIONS):
            button = Gtk.ToggleButton(label=label)
            if theme_group is None:
                theme_group = button
            else:
                button.set_group(theme_group)
            button.set_active(index == theme_index(self.settings.theme))
            button.connect("toggled", self.on_theme_button_toggled, index)
            theme_box.append(button)
            self._theme_buttons.append(button)
        appearance.append(
            settings_row(
                "Theme",
                "System follows your desktop. Light and Dark force the EasyMount interface style.",
                theme_box,
            )
        )
        page.append(appearance)

        # Host helper
        helper_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        helper_title = Gtk.Label(label="Host helper", xalign=0)
        helper_title.add_css_class("section-title")
        helper_section.append(helper_title)
        helper_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        helper_actions.set_valign(Gtk.Align.CENTER)
        check_helper = Gtk.Button(label="Check Helper")
        install_helper = Gtk.Button(label="Install / Update")
        install_helper.add_css_class("suggested-action")
        check_helper.connect("clicked", lambda *_: self.check_host_helper())
        install_helper.connect("clicked", lambda *_: self.do_install_helper())
        helper_actions.append(check_helper)
        helper_actions.append(install_helper)
        helper_section.append(
            settings_row(
                "System integration",
                "Required for AppImage and normal installs to create or remove systemd mount units.",
                helper_actions,
            )
        )
        self.helper_status = _hint("Not checked yet.")
        helper_section.append(self.helper_status)
        page.append(helper_section)

        # File browser sidebar
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        sidebar_title = Gtk.Label(label="File browser sidebar", xalign=0)
        sidebar_title.add_css_class("section-title")
        sidebar.append(sidebar_title)
        self.sidebar_switch = Gtk.Switch()
        self.sidebar_switch.set_active(self.settings.show_in_file_browser)
        self.sidebar_switch.set_halign(Gtk.Align.START)
        self.sidebar_switch.connect("notify::active", self.on_sidebar_toggled)
        sidebar.append(
            settings_row(
                "Show mounted shares in the sidebar",
                "Adds ~/Network folders to GNOME Files and GTK pickers. Dolphin via KDE Places is best-effort.",
                self.sidebar_switch,
            )
        )
        sync_button = Gtk.Button(label="Sync Sidebar Entries")
        sync_button.set_halign(Gtk.Align.START)
        sync_button.connect("clicked", lambda *_: self.sync_sidebar_entries(show_success=True))
        sidebar.append(sync_button)
        self.settings_status = _hint("")
        sidebar.append(self.settings_status)
        page.append(sidebar)
        return page

    def build_info_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        page.add_css_class("page")
        title = Gtk.Label(label="Info", xalign=0)
        title.add_css_class("page-title")
        page.append(title)
        summary = Gtk.Label(
            label=(
                "EasyMount creates systemd automount units for SMB and NFS shares instead of editing fstab. "
                "Profiles stay in your user config, SMB passwords stay in Secret Service, and privileged "
                "mount changes go through Polkit."
            ),
            xalign=0,
        )
        summary.set_wrap(True)
        page.append(summary)
        link = Gtk.LinkButton(uri="https://github.com/tobayashi-san/EasyMount", label="GitHub project")
        link.set_halign(Gtk.Align.START)
        page.append(link)
        page.append(_hint("The GitHub page covers setup details, troubleshooting and the helper design."))
        return page

    # -- shares list ---------------------------------------------------------

    def reload(self) -> None:
        self._reload_generation += 1
        gen = self._reload_generation

        child = self.list_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.list_box.remove(child)
            child = nxt

        profiles = self.store.load()
        if not profiles:
            self.list_box.set_show_separators(False)
            self.list_box.append(self._empty_state())
            return
        self.list_box.set_show_separators(True)

        for profile in profiles:
            row, pill = self._build_share_row(profile)
            self.list_box.append(row)
            pill.set_checking()
            self._fetch_status(profile, pill, gen)

    def _empty_state(self) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.set_activatable(False)
        row.set_selectable(False)
        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        empty.set_margin_top(48)
        empty.set_margin_bottom(48)
        empty.set_halign(Gtk.Align.CENTER)
        title = Gtk.Label(label="No network mounts yet")
        title.add_css_class("page-title")
        subtitle = _hint("Add an SMB share or NFS export to mount it under ~/Network.")
        subtitle.set_justify(Gtk.Justification.CENTER)
        button = Gtk.Button(label="Add Share")
        button.add_css_class("suggested-action")
        button.set_halign(Gtk.Align.CENTER)
        button.connect("clicked", lambda *_: self.open_share_dialog())
        empty.append(title)
        empty.append(subtitle)
        empty.append(button)
        row.set_child(empty)
        return row

    def _build_share_row(self, profile: MountProfile) -> tuple[Gtk.ListBoxRow, StatusPill]:
        row = Gtk.ListBoxRow()
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
        title.add_css_class("share-title")
        kind = Gtk.Label(label=profile.type.value.upper())
        kind.add_css_class("share-kind")
        kind.set_valign(Gtk.Align.CENTER)
        heading.append(title)
        heading.append(kind)
        remote = Gtk.Label(label=f"{profile.server}:{profile.remote_path}", xalign=0)
        remote.add_css_class("dim-label")
        details = Gtk.Label(label=f"{mount_mode_label(profile.mount_mode)} · {profile.mount_path}", xalign=0)
        details.add_css_class("dim-label")
        text.append(heading)
        text.append(remote)
        text.append(details)
        text.set_hexpand(True)
        box.append(text)

        pill = StatusPill()
        box.append(pill)

        edit_btn = _icon_button("document-edit-symbolic", "Edit share")
        edit_btn.connect("clicked", lambda *_, p=profile: self.open_share_dialog(p))
        box.append(edit_btn)

        delete_btn = _icon_button("user-trash-symbolic", "Delete share")
        delete_btn.add_css_class("danger-icon")
        delete_btn.connect("clicked", lambda *_, p=profile: self.confirm_delete(p))
        box.append(delete_btn)
        return row, pill

    def _fetch_status(self, profile: MountProfile, pill: StatusPill, gen: int) -> None:
        def work() -> HelperResult:
            return self.helper("status", profile)

        def done(kind: str, value: object) -> None:
            if gen != self._reload_generation:
                return
            if kind == "err":
                pill.set_result(HelperResult(False, {"error": {"message": str(value)}}))
            else:
                pill.set_result(value)  # type: ignore[arg-type]

        _run_async(work, done)

    # -- dialogs / toasts ----------------------------------------------------

    def open_share_dialog(self, profile: MountProfile | None = None) -> None:
        dialog = ShareDialog(self, profile.type if profile else ProfileType.SMB, profile=profile)
        dialog.present()

    def confirm_delete(self, profile: MountProfile) -> None:
        self._themed_message(
            "Delete this mount?",
            f"“{profile.display_name}” will be unmounted and its systemd units removed.",
            buttons=("Cancel", "Delete"),
            primary_index=1,
            destructive=True,
            on_response=lambda idx: self._do_delete(profile) if idx == 1 else None,
        )

    def show_error(self, message: str) -> None:
        self._themed_message(
            "Something went wrong",
            message,
            buttons=("OK",),
            primary_index=0,
        )

    def _themed_message(
        self,
        message: str,
        detail: str | None = None,
        *,
        buttons: tuple[str, ...] = ("OK",),
        primary_index: int = 0,
        destructive: bool = False,
        on_response=None,
    ) -> None:
        """A small modal dialog that carries our own theme palette.

        Unlike ``Gtk.AlertDialog`` (a native, unstyled dialog) this is a plain
        ``Gtk.Window`` so it picks up the ``.theme-light`` / ``.theme-dark``
        classes and matches the rest of the app.
        """
        win = Gtk.Window(transient_for=self, modal=True)
        win.set_title(message)
        win.set_resizable(False)
        win.set_default_size(400, -1)
        _set_theme_class(win, self._effective_theme)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.add_css_class("page")
        win.set_child(box)

        heading = Gtk.Label(label=message, xalign=0)
        heading.add_css_class("section-title")
        heading.set_wrap(True)
        box.append(heading)

        if detail:
            detail_label = Gtk.Label(label=detail, xalign=0)
            detail_label.add_css_class("dim-label")
            detail_label.set_wrap(True)
            box.append(detail_label)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.END)
        box.append(actions)

        for index, label in enumerate(buttons):
            button = Gtk.Button(label=label)
            if index == primary_index:
                button.add_css_class("destructive-action" if destructive else "suggested-action")

            def handler(_btn: Gtk.Button, idx: int = index) -> None:
                win.close()
                if on_response is not None:
                    on_response(idx)

            button.connect("clicked", handler)
            actions.append(button)

        win.present()

    def toast(self, message: str) -> None:
        self._toast_label.set_text(message)
        self.toast_revealer.set_reveal_child(True)
        if self._toast_timeout:
            GLib.source_remove(self._toast_timeout)
        self._toast_timeout = GLib.timeout_add_seconds(3, self._hide_toast)

    def _hide_toast(self) -> bool:
        self.toast_revealer.set_reveal_child(False)
        self._toast_timeout = 0
        return False

    # -- data operations (helper calls run in worker threads) ----------------

    def _do_delete(self, profile: MountProfile) -> None:
        def work() -> HelperResult:
            result = self.helper("remove-mount", profile, privileged=True)
            if result.ok:
                if profile.type is ProfileType.SMB and profile.password_saved:
                    try:
                        self.secret_store.clear(profile.id)
                    except SecretStoreError:
                        pass
                remove_file_browser_bookmarks([profile])
                self.store.delete(profile.id)
            return result

        def done(kind: str, value: object) -> None:
            if kind == "err":
                self.show_error(str(value))
                return
            result = value  # type: ignore[assignment]
            if not result.ok:
                self.show_error(error_message(result.payload))
                return
            self.toast("Mount removed.")
            self.reload()

        _run_async(work, done)

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
        if (
            old_profile
            and (old_profile.type is not ProfileType.SMB or not profile.password_saved)
            and old_profile.password_saved
        ):
            self.secret_store.clear(old_profile.id)
        self.store.upsert(profile)
        try:
            sync_file_browser_bookmarks(self.store.load(), enabled=self.settings.show_in_file_browser)
        except (OSError, ValueError):
            pass

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
        return call_helper(command, payload=payload, privileged=privileged)

    # -- settings actions ----------------------------------------------------

    def on_theme_button_toggled(self, button: Gtk.ToggleButton, index: int) -> None:
        if not button.get_active():
            return
        self.settings.theme = theme_from_index(index)
        self.settings_store.save(self.settings)
        self.apply_theme()

    def apply_theme(self) -> None:
        theme = normalize_theme(self.settings.theme)
        # "system" applies no custom palette at all: the active GTK theme
        # (Breeze on KDE, Adwaita on GNOME, ...) renders everything natively,
        # including the window titlebar. "light"/"dark" force our own palette.
        if theme == "system":
            self._effective_theme = ""
        else:
            self._effective_theme = f"theme-{theme}"
        for window in self.get_application().get_windows():
            _set_theme_class(window, self._effective_theme)

    def on_sidebar_toggled(self, switch: Gtk.Switch, *_args: object) -> None:
        self.settings.show_in_file_browser = switch.get_active()
        self.settings_store.save(self.settings)
        self.sync_sidebar_entries(show_success=True)

    def sync_sidebar_entries(self, *, show_success: bool = False) -> None:
        try:
            result = sync_file_browser_bookmarks(
                self.store.load(),
                enabled=self.settings.show_in_file_browser,
            )
        except (OSError, ValueError) as exc:
            self.settings_status.set_label(str(exc))
            return
        if not show_success:
            return
        if result["gtk"] and result["kde"]:
            if result.get("icons"):
                self.settings_status.set_label("Sidebar entries and network icons updated.")
            else:
                self.settings_status.set_label(
                    "Sidebar entries updated. Custom network icons are not supported on this desktop."
                )
        elif result["gtk"]:
            self.settings_status.set_label("GTK sidebar entries updated. KDE Places could not be updated.")
        else:
            self.settings_status.set_label("Sidebar entries could not be updated.")

    def check_host_helper(self) -> None:
        self.helper_status.set_label("Checking host helper…")

        def work() -> HelperResult:
            return call_helper("self-check")

        def done(kind: str, value: object) -> None:
            if kind == "err":
                self.helper_status.set_label(str(value))
                return
            result = value  # type: ignore[assignment]
            if result.ok:
                self.helper_status.set_label(
                    format_helper_status(
                        result.payload,
                        secret_tool_available=self.secret_store.available(),
                    )
                )
            else:
                self.helper_status.set_label(f"Host helper is not ready: {error_message(result.payload)}")

        _run_async(work, done)

    def do_install_helper(self) -> None:
        self.helper_status.set_label("Starting host helper installer…")

        def work() -> subprocess.CompletedProcess[str]:
            return install_host_helper()

        def done(kind: str, value: object) -> None:
            if kind == "err":
                self.helper_status.set_label(str(value))
                return
            result = value  # type: ignore[assignment]
            if result.returncode == 0:
                self.helper_status.set_label("Host helper installed or updated.")
                self.check_host_helper()
                return
            message = (
                result.stderr.strip()
                or result.stdout.strip()
                or f"Installer failed with exit code {result.returncode}"
            )
            self.helper_status.set_label(message)

        _run_async(work, done)


class EasyMountApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
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

    def do_activate(self) -> None:
        window = self.get_active_window()
        if window is None:
            window = MainWindow(self)
        window.present()


def run(argv: list[str]) -> int:
    app = EasyMountApp()
    return app.run(argv)
