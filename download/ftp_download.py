from __future__ import annotations

import fnmatch
from ftplib import FTP
from pathlib import Path
from typing import Iterator


def download_file_ftp(
    host: str,
    remote_path: str,
    local_path: str | Path,
    *,
    port: int = 21,
    user: str | None = None,
    password: str | None = None,
    timeout: float | None = None,
) -> None:
    """Download a single file from FTP server.

    remote_path: path on server, e.g. /specs/23501.zip or specs/Rel-18/23501.zip
    local_path: local file path (directory must exist or parent will be created).
    """
    local = Path(local_path)
    local.parent.mkdir(parents=True, exist_ok=True)

    with open(local, "wb") as f:

        def callback(data: bytes) -> None:
            f.write(data)

        ftp = FTP(timeout=timeout)
        ftp.connect(host, port)
        if user is not None:
            ftp.login(user=user, passwd=password or "")
        else:
            ftp.login()
        try:
            # Support both file and dir/file
            parts = remote_path.replace("\\", "/").strip("/").split("/")
            if len(parts) > 1:
                for d in parts[:-1]:
                    ftp.cwd(d)
                remote_name = parts[-1]
            else:
                remote_name = parts[0] if parts else remote_path
            ftp.retrbinary(f"RETR {remote_name}", callback)
        finally:
            ftp.quit()


def _iter_ftp_files(
    ftp: FTP,
    prefix: str,
    pattern: str,
    recurse: bool,
) -> Iterator[tuple[str, bool]]:
    """Yield (relative_path, is_file) for entries under prefix matching pattern."""
    try:
        lines: list[str] = []
        ftp.retrlines(f"LIST {prefix or '.'}", lines.append)
    except Exception:
        return
    for line in lines:
        parts = line.split(maxsplit=8)
        if len(parts) < 9:
            name = line.split()[-1] if line.split() else ""
        else:
            name = parts[-1].lstrip()
        if name in (".", "..") or not name:
            continue
        full = f"{prefix}/{name}".strip("/") if prefix else name
        is_dir = line.upper().startswith("D")
        if is_dir and recurse:
            yield from _iter_ftp_files(ftp, full, pattern, recurse)
        elif not is_dir and fnmatch.fnmatch(name, pattern):
            yield full, True


def download_dir_ftp(
    host: str,
    remote_dir: str,
    local_dir: str | Path,
    *,
    pattern: str = "*.zip",
    port: int = 21,
    user: str | None = None,
    password: str | None = None,
    timeout: float | None = None,
    recurse: bool = True,
) -> list[Path]:
    """List remote directory (optionally recursive), download files matching pattern.

    Returns list of local paths written.
    """
    local_root = Path(local_dir)
    local_root.mkdir(parents=True, exist_ok=True)
    ftp = FTP(timeout=timeout)
    ftp.connect(host, port)
    if user is not None:
        ftp.login(user=user, passwd=password or "")
    else:
        ftp.login()
    downloaded: list[Path] = []
    try:
        remote_dir_norm = remote_dir.replace("\\", "/").strip("/")
        if remote_dir_norm:
            ftp.cwd("/" + remote_dir_norm if not remote_dir_norm.startswith("/") else remote_dir_norm)
        for rel_path, is_file in _iter_ftp_files(ftp, remote_dir_norm, pattern, recurse):
            if not is_file:
                continue
            local_path = local_root / rel_path
            local_path.parent.mkdir(parents=True, exist_ok=True)
            with open(local_path, "wb") as f:
                ftp.retrbinary(f"RETR {rel_path}", f.write)
            downloaded.append(local_path)
    finally:
        ftp.quit()
    return downloaded
