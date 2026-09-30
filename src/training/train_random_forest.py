"""Entrena y evalúa el baseline Random Forest para las tres dosis Poisson."""

from __future__ import annotations

import contextlib
import io
import json
import random
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.dataset import SpectraDataset  # noqa: E402

SEED = 42
CLASS_NAMES = ["C", "Al", "Si", "Cu", "Ge", "Au"]


def load_data(directory: Path) -> tuple[np.ndarray, np.ndarray]:
    with (directory / "labels_map.json").open(encoding="utf-8") as handle:
        labels = json.load(handle)
    dataset = SpectraDataset(directory, labels_map=labels, apply_l1_norm=False)
    x = np.stack([dataset[i][0].numpy() for i in range(len(dataset))])
    y = np.asarray([dataset[i][1] for i in range(len(dataset))], dtype=np.int64)
    return x, y


def format_confusion(cm: np.ndarray) -> str:
    header = "real\\pred " + " ".join(f"{name:>5}" for name in CLASS_NAMES)
    rows = [header]
    for name, row in zip(CLASS_NAMES, cm):
        rows.append(f"{name:>9} " + " ".join(f"{value:5d}" for value in row))
    return "\n".join(rows)


def train_one(level: str, directory: Path, save_model: Path | None = None) -> float:
    x, y = load_data(directory)
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.20, random_state=SEED, stratify=y
    )
    model = RandomForestClassifier(n_estimators=200, random_state=SEED, n_jobs=-1)
    model.fit(x_train, y_train)
    prediction = model.predict(x_test)
    accuracy = accuracy_score(y_test, prediction)
    macro_f1 = f1_score(y_test, prediction, average="macro", zero_division=0)
    matrix = confusion_matrix(y_test, prediction, labels=np.arange(len(CLASS_NAMES)))
    print("\n" + "=" * 76)
    print(f"RANDOM FOREST — {level.upper()} ({len(y)} espectros; train={len(y_train)}, test={len(y_test)})")
    print("=" * 76)
    print(f"Accuracy global: {accuracy:.4f}")
    print(f"F1 macro:        {macro_f1:.4f}")
    print("Matriz de confusión:")
    print(format_confusion(matrix))
    print("Reporte por clase:")
    print(classification_report(y_test, prediction, labels=np.arange(len(CLASS_NAMES)),
                                target_names=CLASS_NAMES, zero_division=0))
    if save_model is not None:
        save_model.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, save_model)
        print(f"Modelo guardado: {save_model}")
    return float(accuracy)


def run() -> dict[str, float]:
    random.seed(SEED)
    np.random.seed(SEED)
    processed = ROOT / "data" / "processed"
    model_path = ROOT / "models" / "random_forest_bremsstrahlung.pkl"
    outcomes = {}
    for level in ("low", "mid", "high"):
        outcomes[level] = train_one(level, processed / f"bremsstrahlung_{level}",
                                    model_path if level == "mid" else None)
    print("\nAccuracy final Random Forest")
    print("nivel | accuracy")
    for level in ("low", "mid", "high"):
        print(f"{level:5} | {outcomes[level]:.4f}")
    return outcomes


if __name__ == "__main__":
    report = ROOT / "reports" / "random_forest_results.txt"
    report.parent.mkdir(parents=True, exist_ok=True)
    capture = io.StringIO()
    with contextlib.redirect_stdout(capture):
        run()
    text = capture.getvalue()
    report.write_text(text, encoding="utf-8")
    print(text, end="")
    print(f"Salida completa guardada en: {report}")
