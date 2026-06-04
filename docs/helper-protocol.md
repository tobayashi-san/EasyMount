# Helper Protocol

`easymount-helper` reads one JSON object from stdin and writes one JSON object to
stdout. Commands that alter mount units must run as root, usually through
`pkexec`.

`self-check` is the only command that does not need a profile payload. It is
used by the GUI to detect whether the host helper is installed and whether the
host has the required mount tools.

Payload shape:

```json
{
  "profile": {
    "id": "nas-12345678",
    "type": "smb",
    "display_name": "NAS",
    "server": "nas.local",
    "remote_path": "media",
    "mount_path": "/home/alice/Network/NAS",
    "mount_mode": "automount",
    "created_for_uid": 1000,
    "created_for_gid": 1000,
    "username": "alice"
  },
  "secret": "password-for-smb-only"
}
```

Responses always include `ok`. Failures include a stable error code:

```json
{
  "ok": false,
  "error": {
    "code": "missing_dependency",
    "message": "missing required command: mount.cifs"
  }
}
```

Successful `self-check` responses include a requirements report:

```json
{
  "ok": true,
  "version": "0.1.2",
  "systemd_dir": "/etc/systemd/system",
  "requirements": {
    "ok": false,
    "missing": ["mount.nfs"],
    "groups": {
      "core": ["systemctl", "findmnt", "mount", "umount", "pkexec"],
      "smb": ["mount.cifs"],
      "nfs": ["mount.nfs"]
    },
    "systemd": {
      "available": true,
      "state": "running"
    }
  }
}
```
