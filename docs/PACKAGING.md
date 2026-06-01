# Packaging

EasyMount should be packaged as two cooperating pieces:

- GUI package: unprivileged app, desktop file, icon and AppStream metadata
- host helper package: helper executable, Polkit policy and optional user agent

Flatpak and AppImage are good fits for the GUI. The host helper must remain a
native host install because it manages systemd mount units and runtime
credential files.

## Host Helper Files

The native helper package should install:

- `/usr/libexec/easymount-helper`
- `/usr/bin/easymount-helper`
- `/usr/bin/easymount-agent`
- `/usr/share/polkit-1/actions/org.easymount.helper.policy`
- `/usr/lib/systemd/user/easymount-agent.service`

The helper path in the Polkit policy must match the installed libexec wrapper.

## GUI-Driven Helper Install

The GUI can install or update the helper from Settings. It does this without
giving the GUI direct mount privileges:

1. export the Python helper source and install templates to the user's cache
2. start the exported installer through `pkexec`
3. on Flatpak, wrap that command with `flatpak-spawn --host`

This is useful for AppImage and local Flatpak testing. For distro repositories
or Flathub-style distribution, a native host-helper package is still the cleaner
and more reviewable path.

## GUI Files

GUI packages should install:

- `easymount`
- `org.easymount.EasyMount.desktop`
- `org.easymount.EasyMount.metainfo.xml`
- `org.easymount.EasyMount.svg`

## Flatpak

The manifest lives at:

```sh
packaging/flatpak/org.easymount.EasyMount.yml
```

The app launcher detects Flatpak by checking `/.flatpak-info` and runs the host
helper with:

```sh
flatpak-spawn --host pkexec /usr/libexec/easymount-helper <command>
```

That means the host helper package must be installed before the Flatpak GUI can
create or remove mounts. The GUI can guide users through that helper install by
launching the same host-side installer through Polkit.

## AppImage

An AppImage should bundle the GUI and Python application code, but it should not
bundle or run a private privileged helper. Use the same host helper path:

```sh
/usr/libexec/easymount-helper
```

## Validation Checklist

Run before cutting a package:

```sh
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tests
desktop-file-validate data/org.easymount.EasyMount.desktop
appstreamcli validate --no-net data/org.easymount.EasyMount.metainfo.xml
sh -n scripts/install-helper.sh
sh -n scripts/uninstall-helper.sh
python -m pip wheel --no-deps -w /tmp/easymount-wheel .
```

Clean generated files after local wheel checks:

```sh
rm -rf build easymount.egg-info
```
