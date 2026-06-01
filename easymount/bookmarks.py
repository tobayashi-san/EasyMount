from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

from .models import MountProfile


BOOKMARK_NS = "http://www.freedesktop.org/standards/desktop-bookmarks"
NETWORK_ICON = "network-server"

ET.register_namespace("bookmark", BOOKMARK_NS)


def sync_file_browser_bookmarks(
    profiles: list[MountProfile],
    *,
    enabled: bool,
    config_home: str | os.PathLike[str] | None = None,
    data_home: str | os.PathLike[str] | None = None,
) -> dict[str, bool]:
    gtk_ok = sync_gtk_bookmarks(profiles, enabled=enabled, config_home=config_home)
    kde_ok = sync_kde_places(profiles, enabled=enabled, data_home=data_home)
    icon_ok = sync_mountpoint_icons(profiles, enabled=enabled)
    return {"gtk": gtk_ok, "kde": kde_ok, "icons": icon_ok}


def remove_file_browser_bookmarks(
    profiles: list[MountProfile],
    *,
    config_home: str | os.PathLike[str] | None = None,
    data_home: str | os.PathLike[str] | None = None,
) -> dict[str, bool]:
    return sync_file_browser_bookmarks(
        profiles,
        enabled=False,
        config_home=config_home,
        data_home=data_home,
    )


def sync_gtk_bookmarks(
    profiles: list[MountProfile],
    *,
    enabled: bool,
    config_home: str | os.PathLike[str] | None = None,
) -> bool:
    ok = True
    for path in gtk_bookmark_paths(config_home):
        try:
            update_gtk_bookmark_file(path, profiles, enabled=enabled)
        except OSError:
            ok = False
    return ok


def update_gtk_bookmark_file(path: Path, profiles: list[MountProfile], *, enabled: bool) -> None:
    if not path.exists() and not enabled:
        return
    entries = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    profile_uris = {path_to_uri(profile.mount_path) for profile in profiles}
    entries = [entry for entry in entries if gtk_entry_uri(entry) not in profile_uris]
    if enabled:
        entries.extend(gtk_bookmark_entry(profile) for profile in profiles)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text("\n".join(entries) + ("\n" if entries else ""), encoding="utf-8")
    os.chmod(path, 0o600)


def sync_kde_places(
    profiles: list[MountProfile],
    *,
    enabled: bool,
    data_home: str | os.PathLike[str] | None = None,
) -> bool:
    path = kde_places_path(data_home)
    if not path.exists() and not enabled:
        return True
    try:
        root = read_or_create_xbel(path)
        profile_uris = {path_to_uri(profile.mount_path) for profile in profiles}
        for bookmark in list(root.findall("bookmark")):
            if bookmark.get("href") in profile_uris:
                root.remove(bookmark)
        if enabled:
            for profile in profiles:
                root.append(kde_bookmark(profile))
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
        os.chmod(path, 0o600)
        return True
    except (OSError, ET.ParseError):
        return False


def read_or_create_xbel(path: Path) -> ET.Element:
    if not path.exists():
        return ET.Element("xbel", {"version": "1.0"})
    root = ET.parse(path).getroot()
    if root.tag != "xbel":
        raise ET.ParseError("not an XBEL file")
    return root


def kde_bookmark(profile: MountProfile) -> ET.Element:
    bookmark = ET.Element("bookmark", {"href": path_to_uri(profile.mount_path)})
    ET.SubElement(bookmark, "title").text = profile.display_name
    info = ET.SubElement(bookmark, "info")
    freedesktop = ET.SubElement(info, "metadata", {"owner": "http://freedesktop.org"})
    ET.SubElement(freedesktop, f"{{{BOOKMARK_NS}}}icon", {"name": NETWORK_ICON})
    metadata = ET.SubElement(info, "metadata", {"owner": "org.easymount"})
    ET.SubElement(metadata, "profile").text = profile.id
    return bookmark


def sync_mountpoint_icons(profiles: list[MountProfile], *, enabled: bool) -> bool:
    gio = shutil.which("gio")
    if not gio:
        return False

    ok = True
    for profile in profiles:
        path = Path(profile.mount_path).expanduser()
        if not path.exists():
            continue
        if enabled:
            command = [gio, "set", "-t", "string", str(path), "metadata::custom-icon-name", NETWORK_ICON]
        else:
            command = [gio, "set", "-d", str(path), "metadata::custom-icon-name"]
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        ok = ok and result.returncode == 0
    return ok


def gtk_bookmark_paths(config_home: str | os.PathLike[str] | None = None) -> list[Path]:
    root = Path(config_home) if config_home is not None else Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return [root / "gtk-3.0" / "bookmarks", root / "gtk-4.0" / "bookmarks"]


def kde_places_path(data_home: str | os.PathLike[str] | None = None) -> Path:
    root = Path(data_home) if data_home is not None else Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / "user-places.xbel"


def gtk_bookmark_entry(profile: MountProfile) -> str:
    return f"{path_to_uri(profile.mount_path)} {profile.display_name}"


def gtk_entry_uri(entry: str) -> str:
    return entry.strip().split(" ", 1)[0]


def path_to_uri(path: str | os.PathLike[str]) -> str:
    uri = Path(path).expanduser().resolve(strict=False).as_uri()
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise ValueError("only local file bookmarks are supported")
    return uri
