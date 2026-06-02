# Development

## Run Tests

Use `PYTHONDONTWRITEBYTECODE=1` to avoid creating `__pycache__` folders in the
repo:

```sh
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tests
```

## Run The GUI

```sh
python -m easymount.app
```

The GUI can run from the source tree. Actions that install or remove mounts use
the helper through `pkexec`.

## Helper Dry Runs

Dry runs validate payloads and render units without writing to
`/etc/systemd/system`:

```sh
python -m easymount.helper install-mount --dry-run < payload.json
python -m easymount.helper test-connection --dry-run < payload.json
```

## Validate Desktop Metadata

```sh
desktop-file-validate data/org.easymount.EasyMount.desktop
appstreamcli validate --no-net data/org.easymount.EasyMount.metainfo.xml
```

## Build A Wheel

```sh
python -m pip wheel --no-deps -w /tmp/easymount-wheel .
```

Remove generated build output afterwards:

```sh
rm -rf build easymount.egg-info
```

## Source Layout

- `easymount/ui.py`: GTK GUI (windows, dialogs, theming)
- `easymount/app.py`: pure helpers, theme options and GTK CSS
- `easymount/helper.py`: privileged helper command implementation
- `easymount/launcher.py`: local and Flatpak helper command launcher
- `easymount/unit.py`: systemd unit generation
- `easymount/models.py`: profile model and validation
- `easymount/storage.py`: profile persistence
- `easymount/secret_store.py`: Secret Service adapter
- `easymount/bookmarks.py`: file browser sidebar integration
