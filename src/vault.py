"""
Private storage for licensed audio in a public repo.

ElevenLabs' Music Terms (2026-10-09, section 4.2) allow "storing Output for your
own internal use where it is not made available to third parties", and forbid
making a collection of tracks available for others to download. This repo is
public, so ElevenLabs tracks are committed only as AES-256 gpg files
(`assets/music/edit/<id>.mp3.gpg`), the pattern GitHub documents for files too
big for a secret. The passphrase is the `MUSIC_KEY` Actions secret, which the
owner made up and nobody else sees; GitHub never passes it to workflows run
from forks. Decrypted audio lives only in a temp directory for one render.

Without MUSIC_KEY nothing breaks: encrypted tracks are simply unavailable, so
the edit music falls back to the approved plain tracks, then Kevin MacLeod.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

ENV = "MUSIC_KEY"
SUFFIX = ".gpg"


def available() -> bool:
    return bool(os.environ.get(ENV, "").strip())


def _gpg(args: list[str], key: str) -> None:
    # The passphrase goes in on stdin, never on the command line or in a file.
    subprocess.run(["gpg", "--batch", "--yes", "--quiet", "--pinentry-mode", "loopback",
                    "--passphrase-fd", "0", *args],
                   input=key.encode(), check=True, capture_output=True)


def encrypt(src: Path, dst: Path, key: str | None = None) -> Path:
    key = key if key is not None else os.environ.get(ENV, "").strip()
    if not key:
        raise RuntimeError(f"{ENV} is not set: refusing to store licensed audio in the clear")
    dst.parent.mkdir(parents=True, exist_ok=True)
    _gpg(["--symmetric", "--cipher-algo", "AES256", "-o", str(dst), str(src)], key)
    return dst


def decrypt(src: Path, dst: Path, key: str | None = None) -> Path:
    key = key if key is not None else os.environ.get(ENV, "").strip()
    if not key:
        raise RuntimeError(f"{ENV} is not set")
    dst.parent.mkdir(parents=True, exist_ok=True)
    _gpg(["-o", str(dst), "-d", str(src)], key)
    return dst


def plain(path: Path, workdir: Path) -> Path | None:
    """A readable copy of `path`: itself, or decrypted into `workdir`. None
    when it is encrypted and no key is available, or decryption fails."""
    path = Path(path)
    if path.suffix != SUFFIX:
        return path if path.exists() else None
    if not available() or not path.exists():
        return None
    out = Path(workdir) / path.name[: -len(SUFFIX)]
    try:
        return decrypt(path, out)
    except Exception:  # noqa: BLE001
        return None
