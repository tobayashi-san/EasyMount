# Uninstall

Use this when you installed EasyMount with `scripts/install-helper.sh`.

## Recommended Order

1. Open EasyMount.
2. Delete every configured share you no longer want.
3. Close EasyMount.
4. Run the uninstall script.

Deleting shares in the GUI removes the generated systemd mount and automount
units cleanly through the helper.

## Remove The Development Install

```sh
sudo ./scripts/uninstall-helper.sh
```

With a custom prefix:

```sh
sudo ./scripts/uninstall-helper.sh /usr/local
```

The script removes:

- the `easymount` Python package installed by pip
- `/usr/libexec/easymount-helper`
- Polkit policy
- desktop file
- icon
- AppStream metadata
- systemd user service file
- legacy EasySMB files from older test installs

## What It Keeps

The uninstall script does not remove user data by default:

- `~/.config/easymount/profiles.json`
- saved SMB passwords in Secret Service
- already generated mount units if you did not delete shares first

This is intentional. Removing active network mounts automatically can interrupt
open files or applications.

## Manual User Data Cleanup

After uninstalling, remove profile config if you no longer need it:

```sh
rm -rf ~/.config/easymount
```

Saved SMB secrets are stored through Secret Service. The safest way to remove
them is to delete shares in the app before uninstalling. If the app is already
gone, use your desktop password/keyring manager and remove EasyMount entries.

## If Mount Units Were Left Behind

If you uninstalled before deleting shares, install EasyMount again, delete the
shares in the GUI, then uninstall again. This avoids guessing unit names and is
safer than manually deleting systemd unit files.
