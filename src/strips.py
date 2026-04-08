"""
strips.py — Gemensam Y-bandes-logik för steg 8, 9, 10 och 11.

Delar SRC-rasterns Y-extent i STRIP_N jämt breda horisontella band med
STRIP_OVERLAP_M meters överlapp per sida. Returnerar band-dicts med:

  idx        — bandindex 0 … STRIP_N-1
  y_own_min  — underkant för "ägt" område (utan överlapp)
  y_own_max  — överkant för "ägt" område (utan överlapp)
  y_ov_min   — underkant inklusive överlapp (för GRASS-extraktion)
  y_ov_max   — överkant inklusive överlapp (för GRASS-extraktion)
"""

from __future__ import annotations
import subprocess, json, re
from functools import lru_cache
from pathlib import Path
from typing import Any

from config import SRC, STRIP_N, STRIP_OVERLAP_M


# ──────────────────────────────────────────────────────────────────────────────
# Intern hjälp: SRC-rasterns geografiska extent
# ──────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _src_extent() -> tuple[float, float, float, float]:
    """Returnera (x_min, y_min, x_max, y_max) i rasterns CRS via gdalinfo -json."""
    out = subprocess.check_output(
        ["gdalinfo", "-json", str(SRC)], text=True, stderr=subprocess.DEVNULL
    )
    info = json.loads(out)
    coords = info["cornerCoordinates"]
    xs = [coords["lowerLeft"][0], coords["upperRight"][0]]
    ys = [coords["lowerLeft"][1], coords["upperRight"][1]]
    return min(xs), min(ys), max(xs), max(ys)


def src_extent() -> tuple[float, float, float, float]:
    """Publik wrapper — returnerar (x_min, y_min, x_max, y_max)."""
    return _src_extent()


# ──────────────────────────────────────────────────────────────────────────────
# Band-beräkning
# ──────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def compute_strips() -> list[dict[str, Any]]:
    """
    Returnerar lista med STRIP_N band-dicts, sorterade nedifrån (band 0 = söder).

    Varje dict innehåller:
      idx        — int
      y_own_min  — float  (underkant ägt)
      y_own_max  — float  (överkant ägt)
      y_ov_min   — float  (underkant med överlapp)
      y_ov_max   — float  (överkant med överlapp)
    """
    _, y_min, _, y_max = _src_extent()
    total_h = y_max - y_min
    band_h  = total_h / STRIP_N

    strips = []
    for i in range(STRIP_N):
        own_min = y_min + i * band_h
        own_max = y_min + (i + 1) * band_h
        ov_min  = max(y_min, own_min - STRIP_OVERLAP_M)
        ov_max  = min(y_max, own_max + STRIP_OVERLAP_M)
        strips.append(dict(
            idx       = i,
            y_own_min = own_min,
            y_own_max = own_max,
            y_ov_min  = ov_min,
            y_ov_max  = ov_max,
        ))
    return strips


def strip_name(idx: int) -> str:
    """Returnerar nollutfyllat bandnamn, t.ex. 'strip_003'."""
    return f"strip_{idx:03d}"


# ──────────────────────────────────────────────────────────────────────────────
# Hjälp för rasterbaserat flöde (steg 8, raster-path)
# ──────────────────────────────────────────────────────────────────────────────

def _tile_y_extent(tif: Path) -> tuple[float, float]:
    """
    Returnerar (y_min, y_max) för en enskild tile via gdalinfo -json.
    Cashas inte — anropas en gång per tile vid filtrering.
    """
    out = subprocess.check_output(
        ["gdalinfo", "-json", str(tif)], text=True, stderr=subprocess.DEVNULL
    )
    info = json.loads(out)
    coords = info["cornerCoordinates"]
    ys = [coords["lowerLeft"][1], coords["upperRight"][1]]
    return min(ys), max(ys)


def get_tiles_for_strip(strip: dict[str, Any], tif_files: list[Path]) -> list[Path]:
    """
    Returnerar de TIF-filer vars Y-extent överlappar med bandets ov_min/ov_max.
    Tids-optimering: tif_files bör vara förfiltrerade på metod/variant.
    """
    ov_min = strip["y_ov_min"]
    ov_max = strip["y_ov_max"]
    result = []
    for tif in tif_files:
        t_min, t_max = _tile_y_extent(tif)
        if t_max > ov_min and t_min < ov_max:
            result.append(tif)
    return result
