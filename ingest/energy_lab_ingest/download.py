"""Descarga con verificación sha256 a un caché local.

El caché vive fuera del repositorio (ENERGY_LAB_DATA_DIR, por omisión
~/.cache/energy-lab). Los datos crudos nunca se versionan.
"""

from __future__ import annotations

import hashlib
import os
import urllib.request
import zipfile
from pathlib import Path

CHUNK = 1 << 20


class ChecksumError(RuntimeError):
    """El archivo descargado no coincide con el sha256 esperado."""


def data_dir() -> Path:
    return Path(os.environ.get("ENERGY_LAB_DATA_DIR", Path.home() / ".cache" / "energy-lab"))


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(CHUNK):
            digest.update(block)
    return digest.hexdigest()


def fetch(url: str, dest: Path, expected_sha256: str | None = None) -> Path:
    """Descarga url a dest si no existe, y verifica el sha256 si se conoce."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        partial = dest.with_suffix(dest.suffix + ".part")
        request = urllib.request.Request(url, headers={"User-Agent": "energy-lab-ingest/0.1"})
        with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as out:
            while block := response.read(CHUNK):
                out.write(block)
        partial.rename(dest)
    if expected_sha256:
        actual = sha256_of(dest)
        if actual != expected_sha256:
            raise ChecksumError(f"{dest.name}: sha256 {actual}, se esperaba {expected_sha256}")
    return dest


def extract_member(archive: Path, member: str, dest_dir: Path) -> Path:
    """Extrae un solo miembro por nombre exacto (sin rutas arbitrarias del zip)."""
    target = dest_dir / Path(member).name
    if target.exists():
        return target
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf, zf.open(member) as src, target.open("wb") as out:
        while block := src.read(CHUNK):
            out.write(block)
    return target
