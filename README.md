# EasyMount

EasyMount is a Linux desktop app for configuring persistent SMB and NFS network
mounts from a GUI. It creates systemd mount units through a small host helper
instead of asking users to edit `fstab`.

## Status

This project is still an early MVP. The core flow works, but packaging and
desktop integration are still being prepared.

Implemented:

- GTK 4 GUI for adding, editing and deleting SMB/NFS shares
- per-share mount behavior: mount on access or always mounted
- profile storage under `~/.config/easymount/profiles.json`
- SMB passwords stored through Secret Service via `secret-tool`
- privileged host helper for systemd mount/automount units
- Polkit policy, desktop file, icon and AppStream metadata
- Flatpak manifest scaffold for the GUI package
- Settings check for the host helper, systemd, SMB/NFS mount helpers and secret storage
- test coverage for models, helper behavior, launcher behavior and bookmarks

## Install For Testing

The development installer writes below `/usr`, installs the host helper, Polkit
policy, desktop integration files and the optional user agent service.

```sh
sudo ./scripts/install-helper.sh
```

Run the installed app:

```sh
easymount
```

Run from the source tree:

```sh
python -m easymount.app
```

The GUI also has `Settings -> Host helper -> Install / Update Helper`. That
path is intended for later Flatpak/AppImage builds and installs only the host
helper pieces through Polkit.

## Uninstall Test Install

First delete configured shares in the GUI if you want their systemd mount units
removed cleanly. Then remove the development install:

```sh
sudo ./scripts/uninstall-helper.sh
```

The uninstall script removes files installed by `scripts/install-helper.sh`. It
keeps user profiles, saved secrets and existing mount units by default.

## Documentation

- [Installation](docs/INSTALL.md)
- [Uninstall](docs/UNINSTALL.md)
- [Development](docs/DEVELOPMENT.md)
- [Packaging](docs/PACKAGING.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Helper protocol](docs/helper-protocol.md)

## Runtime Dependencies

Install distro packages that provide:

- Python 3.10+
- PyGObject / GTK 4
- libsecret `secret-tool`
- Polkit / `pkexec`
- systemd
- `cifs-utils` for SMB
- NFS client tools, usually `nfs-utils` or `nfs-common`

## Packaging Direction

Flatpak and AppImage builds should ship the GUI, desktop file, icon and
AppStream metadata. The privileged mount helper must stay installed on the host
at `/usr/libexec/easymount-helper`, because sandboxed apps cannot manage systemd
mount units directly.
