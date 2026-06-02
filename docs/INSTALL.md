# Installation

EasyMount has two pieces:

- the unprivileged GUI
- the host helper that writes systemd mount units through Polkit

The helper must be installed on the host even when the GUI is later shipped as a
Flatpak or AppImage.

## Development Install

Use this only for local testing:

```sh
sudo ./scripts/install-helper.sh
```

The script installs:

- Python commands below `/usr/bin`
- `/usr/libexec/easymount-helper`
- Polkit policy under `/usr/share/polkit-1/actions`
- Polkit rule under `/usr/share/polkit-1/rules.d`
- desktop file, icon and AppStream metadata
- `easymount-agent.service` as a systemd user service file
- global enablement for the login restore agent

The script accepts a custom prefix:

```sh
sudo ./scripts/install-helper.sh /usr/local
```

## Install Helper From The GUI

The Settings page has a Host helper section with:

- `Check Helper`
- `Install / Update Helper`

This exports a small host-helper source tree to the user's cache directory and
starts the installer through Polkit. In a Flatpak build it uses
`flatpak-spawn --host`; in an AppImage or normal install it uses `pkexec`
directly.

This GUI path installs the host helper pieces needed for mount management. It is
not a replacement for distro packaging, but it makes local Flatpak/AppImage
testing easier.

## Start The App

Installed command:

```sh
easymount
```

Source tree command:

```sh
python -m easymount.app
```

## Login Restore Agent

The installer globally enables `easymount-agent.service`. After the next login it
prepares saved SMB credentials again. For authenticated SMB shares, the agent
starts the deferred systemd automount trigger only after the runtime credential
file exists; for `Always mounted` profiles, it also starts the mount after
login. This avoids boot-time mount attempts against missing `/run` credential
files.

For manual testing in the current user session:

```sh
systemctl --user daemon-reload
systemctl --user enable --now easymount-agent.service
```

## Distro Dependencies

Install the packages that provide:

- Python 3.10+
- PyGObject / GTK 4
- `secret-tool`
- `pkexec`
- systemd
- `mount.cifs`
- `mount.nfs`
