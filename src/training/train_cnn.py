"""Entrena una CNN 1D para las tres dosis Poisson del corpus."""

from __future__ import annotations

import contextlib
import io
import json
import random
import sys
from copy import deepcopy
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import torch
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from torch import nn
from torch.utils.data import DataLoader, Subset

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.dataset import SpectraDataset  # noqa: E402
from src.model import Spectra1DCNN  # noqa: E402

SEED = 42
CLASS_NAMES = ["C", "Al", "Si", "Cu", "Ge", "Au"]
BATCH_SIZE = 16
EPOCHS = 100
PATIENCE = 15
# Mantiene la normalización L1 y eleva su magnitud típica (~1/4096) para que
# la epsilon interna de BatchNorm no domine la señal de entrada.
INPUT_SCALE = 4096.0


def set_seed() -> None:
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def split_dataset(dataset: SpectraDataset) -> tuple[Subset, Subset, Subset]:
    indices = np.arange(len(dataset))
    labels = np.asarray(dataset.labels)
    train_val, test = train_test_split(indices, test_size=0.10, random_state=SEED, stratify=labels)
    train, val = train_test_split(train_val, test_size=1 / 9, random_state=SEED, stratify=labels[train_val])
    return Subset(dataset, train.tolist()), Subset(dataset, val.tolist()), Subset(dataset, test.tolist())


def evaluate(model: nn.Module, loader: DataLoader, device: torch.device, criterion: nn.Module) -> tuple[float, float, np.ndarray, np.ndarray]:
    model.eval()
    losses: list[float] = []
    actual: list[int] = []
    predicted: list[int] = []
    with torch.no_grad():
        for spectra, labels in loader:
            spectra = spectra.to(device).unsqueeze(1) * INPUT_SCALE
            labels = labels.to(device)
            logits = model(spectra)
            losses.append(float(criterion(logits, labels).item()) * len(labels))
            actual.extend(labels.cpu().tolist())
            predicted.extend(logits.argmax(dim=1).cpu().tolist())
    y_true, y_pred = np.asarray(actual), np.asarray(predicted)
    return sum(losses) / len(y_true), accuracy_score(y_true, y_pred), y_true, y_pred


def table(cm: np.ndarray) -> str:
    rows = ["real\\pred " + " ".join(f"{name:>5}" for name in CLASS_NAMES)]
    rows += [f"{name:>9} " + " ".join(f"{value:5d}" for value in row)
             for name, row in zip(CLASS_NAMES, cm)]
    return "\n".join(rows)


def plot_history(history: dict[str, list[float]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    epochs = range(1, len(history["train_loss"]) + 1)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), constrained_layout=True)
    axes[0].plot(epochs, history["train_loss"], label="train")
    axes[0].plot(epochs, history["val_loss"], label="validación")
    axes[0].set(title="Pérdida", xlabel="Época", ylabel="Cross-entropy")
    axes[1].plot(epochs, history["train_acc"], label="train")
    axes[1].plot(epochs, history["val_acc"], label="validación")
    axes[1].set(title="Accuracy", xlabel="Época", ylabel="Accuracy", ylim=(0, 1.02))
    for axis in axes:
        axis.grid(alpha=0.25)
        axis.legend()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def train_one(level: str, directory: Path, device: torch.device, save_model: Path | None = None,
              curves: Path | None = None) -> float:
    set_seed()
    with (directory / "labels_map.json").open(encoding="utf-8") as handle:
        labels_map = json.load(handle)
    dataset = SpectraDataset(directory, labels_map=labels_map, apply_l1_norm=False)
    train_set, val_set, test_set = split_dataset(dataset)
    loaders = [DataLoader(part, batch_size=BATCH_SIZE, shuffle=(i == 0), num_workers=0)
               for i, part in enumerate((train_set, val_set, test_set))]
    model = Spectra1DCNN(num_classes=6, in_channels=1, conv1_out_channels=32,
                         conv2_out_channels=64, kernel_size=5).to(device)
    criterion, optimizer = nn.CrossEntropyLoss(), torch.optim.Adam(model.parameters(), lr=0.001)
    history: dict[str, list[float]] = {key: [] for key in ("train_loss", "val_loss", "train_acc", "val_acc")}
    best_loss, best_state, wait = float("inf"), None, 0
    print("\n" + "=" * 76)
    print(f"CNN 1D — {level.upper()} ({len(dataset)} espectros; train={len(train_set)}, val={len(val_set)}, test={len(test_set)}, escala_entrada={INPUT_SCALE:g})")
    print("=" * 76)
    for epoch in range(1, EPOCHS + 1):
        model.train()
        weighted_loss, correct, seen = 0.0, 0, 0
        for spectra, targets in loaders[0]:
            spectra = spectra.to(device).unsqueeze(1) * INPUT_SCALE
            targets = targets.to(device)
            optimizer.zero_grad()
            logits = model(spectra)
            loss = criterion(logits, targets)
            loss.backward()
            optimizer.step()
            weighted_loss += float(loss.item()) * len(targets)
            correct += int((logits.argmax(dim=1) == targets).sum().item())
            seen += len(targets)
        train_loss, train_acc = weighted_loss / seen, correct / seen
        val_loss, val_acc, _, _ = evaluate(model, loaders[1], device, criterion)
        for key, value in (("train_loss", train_loss), ("val_loss", val_loss),
                           ("train_acc", train_acc), ("val_acc", val_acc)):
            history[key].append(value)
        print(f"época {epoch:03d}: train_loss={train_loss:.6f} val_loss={val_loss:.6f} val_acc={val_acc:.4f}")
        if val_loss < best_loss - 1e-7:
            best_loss, best_state, wait = val_loss, deepcopy(model.state_dict()), 0
        else:
            wait += 1
            if wait >= PATIENCE:
                print(f"Early stopping en época {epoch} (paciencia={PATIENCE}).")
                break
    model.load_state_dict(best_state)
    _, test_acc, y_true, y_pred = evaluate(model, loaders[2], device, criterion)
    macro_f1 = f1_score(y_true, y_pred, average="macro", zero_division=0)
    matrix = confusion_matrix(y_true, y_pred, labels=np.arange(6))
    print(f"Accuracy global test: {test_acc:.4f}")
    print(f"F1 macro test:        {macro_f1:.4f}")
    print("Matriz de confusión:")
    print(table(matrix))
    print("Reporte por clase:")
    print(classification_report(y_true, y_pred, labels=np.arange(6), target_names=CLASS_NAMES, zero_division=0))
    if save_model:
        save_model.parent.mkdir(parents=True, exist_ok=True)
        torch.save(model.state_dict(), save_model)
        print(f"Modelo guardado: {save_model}")
    if curves:
        plot_history(history, curves)
        print(f"Curvas guardadas: {curves}")
    return float(test_acc)


def run() -> dict[str, float]:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"PyTorch: {torch.__version__}")
    print(f"Dispositivo: {device}")
    processed = ROOT / "data" / "processed"
    outcomes = {}
    for level in ("low", "mid", "high"):
        outcomes[level] = train_one(
            level, processed / f"bremsstrahlung_{level}", device,
            ROOT / "models" / "cnn_bremsstrahlung.pth" if level == "mid" else None,
            ROOT / "reports" / "cnn_training_curves.png" if level == "mid" else None,
        )
    print("\nAccuracy final CNN 1D")
    print("nivel | accuracy")
    for level in ("low", "mid", "high"):
        print(f"{level:5} | {outcomes[level]:.4f}")
    return outcomes


if __name__ == "__main__":
    report = ROOT / "reports" / "cnn_results.txt"
    report.parent.mkdir(parents=True, exist_ok=True)
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        run()
    content = captured.getvalue()
    report.write_text(content, encoding="utf-8")
    print(content, end="")
    print(f"Salida completa guardada en: {report}")
