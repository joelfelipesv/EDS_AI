"""
dataset.py - Dataset personalizado de PyTorch para espectros EDS.

Proporciona:
    - SpectraDataset: Clase heredando de torch.utils.data.Dataset que carga
      vectores numpy desde archivos .npy, los convierte a tensores float32
      y aplica normalizacion L1.
    - inject_poisson_noise(): Funcion utilitaria para inyectar ruido de Poisson
      sintético en espectros usando numpy.
"""

import os
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset


class SpectraDataset(Dataset):
    """
    Dataset personalizado para espectros EDS unidimensionales.

    Carga vectores de espectros desde archivos .npy en un directorio dado,
    los convierte a tensores PyTorch float32 y aplica normalizacion L1
    (cada espectro se divide por su suma total para que las intensidades
    integren a 1.0).

    Args:
        data_dir (str o Path): Ruta al directorio con archivos .npy de espectros.
            Se espera que cada archivo .npy contenga un array 1D de intensidades.
        labels_map (dict, optional): Mapeo {nombre_archivo_sin_ext: label_int}.
            Si es None, se asignan labels secuenciales (0, 1, 2, ...).
        apply_l1_norm (bool): Si True, normaliza cada espectro con norma L1.
    """

    def __init__(self, data_dir, labels_map=None, apply_l1_norm=True):
        self.data_dir = Path(data_dir)
        self.apply_l1_norm = apply_l1_norm

        # Descubrir todos los archivos .npy en el directorio
        self.file_paths = sorted(self.data_dir.glob("*.npy"))

        if not self.file_paths:
            raise FileNotFoundError(
                f"No se encontraron archivos .npy en {self.data_dir}"
            )

        # Construir mapeo de labels
        if labels_map is None:
            # Asignar labels secuenciales basados en el orden alfabetico
            self.labels = list(range(len(self.file_paths)))
        else:
            self.labels = []
            for fp in self.file_paths:
                stem = fp.stem  # nombre sin extension
                # Las realizaciones Poisson usan ``C__r01.npy`` etc.; todas
                # conservan la etiqueta canónica previa al separador ``__``.
                canonical_stem = stem.split("__", 1)[0]
                if canonical_stem not in labels_map:
                    raise KeyError(
                        f"Archivo '{stem}.npy' no tiene label definido en labels_map"
                    )
                self.labels.append(labels_map[canonical_stem])

        self.num_samples = len(self.file_paths)

    def __len__(self):
        """Devuelve el numero total de espectros en el dataset."""
        return self.num_samples

    def __getitem__(self, idx):
        """
        Obtiene un espectro y su label por indice.

        Carga el array numpy del archivo .npy correspondiente, lo convierte
        a tensor PyTorch float32, aplica normalizacion L1 si esta habilitada,
        y retorna el par (espectro_tensor, label).

        Args:
            idx (int): Indice del espectro en el dataset.

        Returns:
            tuple: (spectrum_tensor, label) donde spectrum_tensor es un tensor
                1D de tipo torch.float32 y label es un escalar int.
        """
        # Cargar vector numpy desde disco
        spectrum = np.load(self.file_paths[idx])

        # Convertir a tensor PyTorch float32
        spectrum_tensor = torch.from_numpy(spectrum).float()

        # Aplicar normalizacion L1: dividir por la suma de todas las intensidades
        if self.apply_l1_norm:
            spectrum_sum = spectrum_tensor.sum()
            if spectrum_sum > 0:
                spectrum_tensor = spectrum_tensor / spectrum_sum
            else:
                raise ValueError(
                    f"Espectro con suma cero en {self.file_paths[idx].name}. "
                    "No se puede normalizar L1."
                )

        # Obtener label correspondiente
        label = self.labels[idx]

        return spectrum_tensor, label


def inject_poisson_noise(spectrum, scaling_factor=1.0, random_state=None):
    """
    Inyectar ruido de Poisson sintético en un espectro EDS numpy.

    El ruido de Poisson modela la naturaleza discreta de los conteos de fotones
    (o electrones) detectados. Para cada canal del espectro, se muestrea una
    variable aleatoria de Poisson con lambda igual a la intensidad del canal
    multiplicada por un factor de escala.

    Args:
        spectrum (np.ndarray): Array 1D de intensidades del espectro.
            Debe contener valores no negativos.
        scaling_factor (float, optional): Factor para escalar las intensidades
            antes de muestrear Poisson. Un valor mayor simula mayor tiempo de
            adquisicion (mas conteos). Default: 1.0.
        random_state (int or np.random.Generator, optional): Semilla o generador
            para reproducibilidad.

    Returns:
        np.ndarray: Espectro con ruido de Poisson inyectado (float64).

    Raises:
        ValueError: Si el espectro contiene valores negativos.
    """
    if np.any(spectrum < 0):
        raise ValueError(
            "El espectro contiene valores negativos. "
            "No se puede aplicar ruido de Poisson."
        )

    # Configurar generador aleatorio para reproducibilidad
    rng = (
        np.random.default_rng(random_state)
        if random_state is not None
        else np.random
    )

    # Escalar intensidades y muestrear conteos de Poisson
    scaled_spectrum = spectrum * scaling_factor
    noisy_counts = rng.poisson(scaled_spectrum).astype(np.float64)

    return noisy_counts
