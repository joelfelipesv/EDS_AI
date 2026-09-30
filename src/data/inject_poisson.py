"""Crea realizaciones Poisson L1-normalizadas para tres dosis simuladas."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.data.preprocess_bremsstrahlung import LABELS, EPSILON, canonical_csvs, load_counts  # noqa: E402
from src.dataset import inject_poisson_noise  # noqa: E402


LEVELS = {"low": 0.1, "mid": 1.0, "high": 10.0}


def normalize(noisy: np.ndarray) -> np.ndarray:
    total = float(noisy.sum())
    if total <= EPSILON:
        raise ValueError("Una realización Poisson quedó sin cuentas")
    return (noisy / total).astype(np.float32)


def generate(raw_dir: Path, processed_dir: Path, replicas: int, seed: int) -> dict[str, dict[str, float]]:
    """Generate canonical plus replica files.  Ten replicas allow stratified evaluation."""
    if replicas < 2:
        raise ValueError("Se necesitan al menos dos réplicas por clase para una división estratificada")
    csvs = canonical_csvs(raw_dir)
    raw = {label: load_counts(path)[1] for label, path in csvs.items()}
    summary: dict[str, dict[str, float]] = {}
    for level_index, (level, factor) in enumerate(LEVELS.items()):
        destination = processed_dir / f"bremsstrahlung_{level}"
        destination.mkdir(parents=True, exist_ok=True)
        for old in destination.glob("*.npy"):
            old.unlink()
        totals: list[float] = []
        for class_index, label in enumerate(LABELS):
            for replica in range(replicas):
                # A separate deterministic stream for every level/class/replica.
                noisy = inject_poisson_noise(
                    raw[label], scaling_factor=factor,
                    random_state=seed + level_index * 10000 + class_index * 100 + replica,
                )
                totals.append(float(noisy.sum()))
                name = label if replica == 0 else f"{label}__r{replica:02d}"
                np.save(destination / f"{name}.npy", normalize(noisy))
        with (destination / "labels_map.json").open("w", encoding="utf-8") as handle:
            json.dump(LABELS, handle, indent=2)
        summary[level] = {"factor": factor, "mean_total": float(np.mean(totals)),
                          "min_total": float(np.min(totals)), "max_total": float(np.max(totals)),
                          "files": len(totals)}
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "bremsstrahlung_only")
    parser.add_argument("--processed-dir", type=Path, default=ROOT / "data" / "processed")
    parser.add_argument("--replicas", type=int, default=10,
                        help="Realizaciones por clase y nivel (incluye la canónica).")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    summary = generate(args.raw_dir, args.processed_dir, args.replicas, args.seed)
    print("Resumen de cuentas Poisson antes de normalizar L1:")
    for level, values in summary.items():
        print("  %-4s factor=%4g archivos=%d total medio=%.6g (%.6g–%.6g)" %
              (level, values["factor"], values["files"], values["mean_total"],
               values["min_total"], values["max_total"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
