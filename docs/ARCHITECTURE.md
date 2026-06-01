# Architecture

EasyMount keeps the GUI unprivileged and delegates system changes to a small
host helper.

## Flow

1. The GUI reads and writes profiles in the user's config directory.
2. SMB passwords are stored in Secret Service.
3. The GUI sends a profile payload to `easymount-helper`.
4. Polkit authorizes privileged helper commands through `pkexec`.
5. The helper writes systemd `.mount` and `.automount` units.
6. systemd mounts shares either on access or immediately, depending on the
   profile's mount mode.

## Main Modules

- `app.py`: GTK windows, dialogs and status display
- `models.py`: profile schema, defaults and validation
- `unit.py`: systemd unit rendering
- `helper.py`: privileged command handlers
- `launcher.py`: local/Flatpak helper command construction
- `agent.py`: post-login SMB credential preparation
- `bookmarks.py`: GNOME Files and KDE Places sidebar integration
- `secret_store.py`: `secret-tool` wrapper
- `storage.py`: JSON profile storage

## Mount Modes

`automount`:

- enables the systemd `.automount` unit
- mounts the share on first access
- good default for normal file browsing

`always`:

- enables and starts the systemd `.mount` unit
- keeps the share mounted after setup/login
- better for video editing, media libraries, indexers and backup tools

## Runtime Credentials

Generated systemd units never store plaintext SMB passwords. Authenticated SMB
units reference root-readable credential files under:

```sh
/run/easymount/credentials
```

That directory is runtime-only. The GUI and optional user agent recreate
credential files after login when Secret Service is available.

## Sandboxed GUI

Flatpak/AppImage builds should not manage mounts directly. They call the host
helper instead. This keeps the sandboxed GUI simple and keeps all privileged
logic in one auditable place.

## Helper Installer

The GUI can prepare a host-helper installer for users:

1. copy the current EasyMount Python package to the user's cache directory
2. write minimal Polkit and systemd templates next to it
3. run the generated installer through `pkexec`
4. use `flatpak-spawn --host` first when running inside Flatpak

The GUI still never writes `/usr`, `/etc/systemd/system` or Polkit files
itself. Those changes stay inside the small root installer launched through
Polkit.
