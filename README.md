# X-ray Spectroscopy (EDS) Project for Material Classification

## Project Description
This project aims to develop and implement an advanced material classification system using one-dimensional energy spectra obtained with Energy Dispersive X-ray Spectroscopy (EDS). The core idea is to treat each spectrum captured by the SDD detector as a compositional fingerprint that 1D convolutional neural networks (1D-CNN) can analyze, training the model to tell different classes or materials apart.

The expected outcome is a robust classifier able to determine material composition from the spectrum, beating traditional methods that only rely on elemental peaks.

## Computing Environment and Hardware

The main compute node of the project has the following specs:

| Component | Specification |
| --- | --- |
| **Processor (CPU)** | AMD Ryzen 7 8700G |
| **Graphics Processing Unit (GPU)** | AMD Radeon RX 7800 XT (16 GB VRAM) |
| **GPU Environment** | ROCm |
| **RAM** | 32 GB DDR5 |

This hardware setup is enough for the project for two main reasons:
- **Monte Carlo Simulation:** Generating synthetic spectra with DTSA-II runs Monte Carlo simulations of electron transport. This workload is handled well by the Ryzen 7 8700G and the 32 GB of DDR5 RAM, keeping generation times reasonable even for large corpora of materials (bulks).
- **Training 1D-CNN models:** EDS spectra are one-dimensional vectors with a small size (from a few hundred to a few thousand channels). Training Deep Learning models on this kind of data is moderate in compute terms, and the Radeon RX 7800 XT with 16 GB of VRAM, running under ROCm, provides enough acceleration to train and iteratively validate the proposed 1D-CNN architectures.

## Project Roadmap

The project is divided into sequential phases to make sure the methodological and scientific progression is solid:

### Phase 1: Simulation of Pure Homogeneous Materials (Bulks) in DTSA-II
* **Goal:** Build a robust, large, and labeled corpus of simulated EDS spectra of pure homogeneous materials (bulks).
* **Tools:** NIST DTSA-II, Jython/Python.
* **Tasks:**
    1. Set up the environment with the optimal microscope parameters (electron flux, time, angle).
    2. Write scripts that simulate spectrum acquisition for a known library of pure homogeneous materials ($M_k$).
    3. Apply stochastic Poisson noise in post-simulation or inside the DTSA-II workflow.
    4. Generate and organize the raw files (`data/raw/*.msa`).
    5. Preprocessing: Export normalized spectra ($\hat{\mathbf{x}}$) to efficient formats (e.g., `.npy` or `.csv`) in `data/processed/`.

### Phase 2: Baseline Model (Random Forest with Scikit-Learn)
* **Goal:** Set a performance baseline using a Random Forest model, which will serve as a reference point to compare against the later Deep Learning models.
* **Tools:** Scikit-Learn, NumPy, SciPy.
* **Tasks:**
    1. Implement the input data structure from the preprocessed set $\hat{\mathbf{X}}, \mathbf{Y}$.
    2. Define the preprocessing and feature engineering pipeline (normalization and/or dimensionality reduction) on the spectra.
    3. Train and tune the hyperparameters of the Random Forest classifier.
    4. Evaluate the model with standard metrics: Accuracy, F1-Score, and Confusion Matrix.

### Phase 3: Deep Learning with PyTorch
* **Goal:** Train and validate a 1D-CNN model able to classify materials based only on the normalized spectral shape, improving on the baseline set in Phase 2.
* **Tools:** PyTorch, NumPy, Scikit-Learn.
* **Tasks:**
    1. Implement the `torch.utils.data.Dataset` data structure (`src/data/dataset.py`) to handle the $\hat{\mathbf{X}}, \mathbf{Y}$ set.
    2. Define the 1D-CNN architecture (`src/models/cnn1d.py`).
    3. Implement the PyTorch training loop, handling optimizers, loss functions (e.g., CrossEntropyLoss), and validation.
    4. Evaluate the model with standard metrics: Accuracy, F1-Score, and Confusion Matrix (`src/training/evaluate.py`).
    5. Compare the 1D-CNN performance against the Random Forest baseline.

## Current Project Status

Here's the current state of the core project tasks:

- [x] **Architecture definition:** The overall project architecture and the models to be implemented (Random Forest baseline and 1D-CNN) have been defined.
- [x] **Hardware evaluation:** The available computing environment (Ryzen 7 8700G, Radeon RX 7800 XT with ROCm, and 32 GB DDR5) has been evaluated and validated for the required workloads.
- [x] **Repository structure creation:** The repository directory structure has been set up (`data/`, `jython/`, `src/`, `notebooks/`).

The next phases (Bulk Simulation, Baseline, and Deep Learning) are still in development or pending execution according to the Roadmap.

## Setup and Installation

### System Prerequisites
You need to have **NIST DTSA-II** installed, or a compatible version with Jython/Python scripts, for the physical simulation of the spectra. For training with PyTorch under ROCm, a PyTorch installation with support for AMD GPUs is recommended.

### Software Dependencies
```bash
pip install -r requirements.txt
# If you use additional tools:
# pip install pytest
```

## Repository Structure
The project is organized as follows (see the detailed layout in the index). It's recommended to follow this flow: **Generation $\rightarrow$ Preprocessing $\rightarrow$ Modeling**.

*   `data/raw/`: Contains the raw simulated spectra (.msa, .emsa) generated by DTSA-II.
*   `data/processed/`: Stores the numpy arrays or CSV files of normalized spectra ready for PyTorch training.
*   `jython/`: Source scripts specific to the DTSA-II interface.
*   `src/`: Main Python package containing the core logic (models, dataloaders, trainers).
*   `notebooks/`: Interactive environment (`.ipynb`) for exploring, testing, and validating results in early stages.

## Basic Usage

1. **Prepare Data:** Run the spectrum simulation using the scripts in `jython/`. This will fill up `data/raw/`.
2. **Preprocessing:** Write a script (e.g., `src/data/preprocessing.py`) that reads `data/raw/` and generates $\hat{\mathbf{X}}$ in `data/processed/`.
3. **Training:** Run the main training loop, usually from `notebooks/`, or a dedicated script: `python src/training/train.py`.

---
*This README will be updated as the project phases move forward.*