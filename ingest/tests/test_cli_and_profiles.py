"""Perfiles, estimación y guardas de la CLI (sin red ni base)."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from energy_lab_ingest.cli import EXIT_NEEDS_APPROVAL, main
from energy_lab_ingest.download import ChecksumError, extract_member, fetch
from energy_lab_ingest.profiles import estimate, spread


def test_full_sin_aprobacion_se_detiene_sin_descargar(capsys, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ENERGY_LAB_DATA_DIR", str(tmp_path))
    assert main(["uci", "--profile", "full"]) == EXIT_NEEDS_APPROVAL
    out = capsys.readouterr().out
    assert "filas estimadas: 51,894,720" in out
    assert "--yes" in out
    assert not any(tmp_path.iterdir())


def test_spread_reparte_y_no_toma_los_primeros() -> None:
    items = [f"MT_{i:03d}" for i in range(1, 371)]
    chosen = spread(items, 20)
    assert len(chosen) == len(set(chosen)) == 20
    assert chosen[0] == "MT_001"
    assert chosen[-1] > "MT_340"
    assert spread(items, 20) == chosen  # determinista
    assert spread(items[:5], 20) == items[:5]


def test_estimate() -> None:
    e = estimate(48_000_000, 48)
    assert e.disk_gb == pytest.approx(4.56)
    assert e.peak_memory_mb == pytest.approx(160.0)


def test_fetch_verifica_sha256(tmp_path: Path) -> None:
    src = tmp_path / "origen.bin"
    src.write_bytes(b"datos")
    good = hashlib.sha256(b"datos").hexdigest()
    assert fetch(src.as_uri(), tmp_path / "copia.bin", expected_sha256=good).read_bytes() == b"datos"
    with pytest.raises(ChecksumError):
        fetch(src.as_uri(), tmp_path / "otra.bin", expected_sha256="0" * 64)


def test_extract_member_ignora_rutas_del_zip(tmp_path: Path) -> None:
    archive = tmp_path / "a.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("carpeta/LD.txt", "hola")
    out = extract_member(archive, "carpeta/LD.txt", tmp_path / "ext")
    assert out == tmp_path / "ext" / "LD.txt"
    assert out.read_text() == "hola"
