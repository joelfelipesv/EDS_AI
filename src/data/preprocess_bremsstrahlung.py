"""Preprocesa los CSV de bremsstrahlung a vectores L1 normalizados."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "bremsstrahlung_only"
OUT_DIR = ROOT / "data" / "processed" / "bremsstrahlung"
REPORT_PLOT = ROOT / "reports" / "bremsstrahlung_6elementos.png"
LABELS = {"C": 0, "Al": 1, "Si": 2, "Cu": 3, "Ge": 4, "Au": 5}
EPSILON = 1e-8


def load_counts(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Return energy (keV) and counts from a generator CSV."""
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or set(rows[0]) != {"energy_keV", "counts"}:
        raise ValueError(f"CSV invalido: {path}")
    energy = np.asarray([float(row["energy_keV"]) for row in rows], dtype=np.float64)
    counts = np.asarray([float(row["counts"]) for row in rows], dtype=np.float64)
    if counts.ndim != 1 or counts.size != 4096:
        raise ValueError(f"{path.name}: se esperaban 4096 canales, se obtuvieron {counts.size}")
    if np.any(counts < 0):
        raise ValueError(f"{path.name}: contiene cuentas negativas")
    return energy, counts


def l1_normalize(counts: np.ndarray) -> np.ndarray:
    total = float(np.sum(counts))
    if total <= EPSILON:
        raise ValueError("Espectro con suma nula; no se puede normalizar L1")
    return (counts / max(total, EPSILON)).astype(np.float32)


def canonical_csvs(raw_dir: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for label in LABELS:
        candidates = sorted(raw_dir.glob(f"{label}_emitido_*kV.csv"))
        if len(candidates) != 1:
            raise FileNotFoundError(
                f"Se esperaba exactamente un CSV emitido para {label} en {raw_dir}; encontrados {len(candidates)}"
            )
        found[label] = candidates[0]
    return found


def plot_spectra(spectra: dict[str, tuple[np.ndarray, np.ndarray]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 5.5), constrained_layout=True)
    for label in LABELS:
        energy, counts = spectra[label]
        ax.plot(energy, l1_normalize(counts), linewidth=1.25, label=label)
    ax.set(xlim=(0, 30), xlabel="Energía (keV)", ylabel="Cuentas normalizadas (L1)",
           title="Continuo de bremsstrahlung puro — seis elementos, E₀ = 30 kV")
    ax.grid(alpha=0.25)
    ax.legend(title="Material", ncols=3)
    fig.savefig(output, dpi=180)
    plt.close(fig)


def preprocess(raw_dir: Path = RAW_DIR, out_dir: Path = OUT_DIR, plot_path: Path = REPORT_PLOT) -> dict[str, np.ndarray]:
    """Create the six canonical normalized spectra and their labels map."""
    out_dir.mkdir(parents=True, exist_ok=True)
    csvs = canonical_csvs(raw_dir)
    spectra: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    normalized: dict[str, np.ndarray] = {}
    for label, path in csvs.items():
        energy, counts = load_counts(path)
        spectra[label] = (energy, counts)
        normalized[label] = l1_normalize(counts)
        np.save(out_dir / f"{label}.npy", normalized[label])
    with (out_dir / "labels_map.json").open("w", encoding="utf-8") as handle:
        json.dump(LABELS, handle, indent=2)
    plot_spectra(spectra, plot_path)
    return normalized


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--plot", type=Path, default=REPORT_PLOT)
    args = parser.parse_args()
    spectra = preprocess(args.raw_dir, args.output_dir, args.plot)
    stack = np.stack([spectra[label] for label in LABELS])
    print(f"Espectros: {len(spectra)}")
    print(f"Forma del array: {stack.shape}")
    print(f"Mínimo/máximo: {stack.min():.8g} / {stack.max():.8g}")
    for label in LABELS:
        print(f"  {label}: suma={spectra[label].sum():.8f}")
    print(f"Etiquetas: {args.output_dir / 'labels_map.json'}")
    print(f"Gráfica: {args.plot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
