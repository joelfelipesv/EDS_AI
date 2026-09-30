# Fase 1 — corpus de bremsstrahlung y clasificación

La simulación EPQ/JPype generó seis espectros emitidos de bremsstrahlung puro a E0 = 30 kV, 2000 trayectorias, detector SDD de 130 eV y transporte hasta el detector. La validación física pasó: el corte Duane-Hunt quedó por debajo de 0.001 % de las cuentas totales, no se instanció ningún generador característico/fluorescente y la procedencia registrada es `BremsstrahlungXRayGeneration3`.

## Resultados

| Nivel de estadística | Random Forest accuracy | CNN 1D accuracy |
| --- | ---: | ---: |
| Low (0.1×) | 1.0000 | 0.6667 |
| Mid (1×) | 1.0000 | 0.8333 |
| High (10×) | 1.0000 | 0.6667 |

El Random Forest es el mejor modelo de esta fase: separa perfectamente estas seis formas espectrales en el test estratificado. La CNN mejora de forma clara tras escalar numéricamente la entrada L1, con su mejor resultado en la dosis media, pero queda por detrás de RF. El tamaño del corpus sigue siendo pequeño: cada nivel contiene 10 realizaciones Poisson de los mismos seis espectros Monte Carlo, por lo que las métricas indican separación de ruido de adquisición, no generalización a nuevas geometrías o nuevas simulaciones independientes. En RF, las tres dosis son suficientes para conservar la forma discriminante. En la CNN la dosis mid alcanza 0.8333, mientras que low/high quedan en 0.6667 en un test de solo seis muestras. Con estos datos, la complejidad adicional de la CNN no se justifica todavía; RF es el baseline operativo recomendado. La siguiente fase debe añadir simulaciones Monte Carlo independientes por clase, variación instrumental y muestras compuestas antes de comparar arquitecturas de mayor capacidad.

## Archivos generados

- Corpus EPQ: `data/bremsstrahlung_only/{C,Al,Si,Cu,Ge,Au}_emitido_30kV.csv` y `data/bremsstrahlung_only/metadata.json`.
- Preprocesado canónico: `data/processed/bremsstrahlung/` (6 vectores `.npy` y `labels_map.json`).
- Corpus Poisson: `data/processed/bremsstrahlung_low/`, `data/processed/bremsstrahlung_mid/` y `data/processed/bremsstrahlung_high/` (10 realizaciones por cada una de las seis clases y mapa de etiquetas idéntico).
- Modelos: `models/random_forest_bremsstrahlung.pkl` y `models/cnn_bremsstrahlung.pth`.
- Evidencia y métricas: `reports/bremsstrahlung_6elementos.png`, `reports/random_forest_results.txt`, `reports/cnn_results.txt` y `reports/cnn_training_curves.png`.
- Registro de ejecución: `docs/iteraciones_fase1.md`.

## Reproducción

Desde la raíz del proyecto, en PowerShell:

```powershell
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe src\data\generate_bremsstrahlung_jpype.py --n-traj 2000
venv\Scripts\python.exe scripts\validate_bremsstrahlung.py --csv
venv\Scripts\python.exe src\data\preprocess_bremsstrahlung.py
venv\Scripts\python.exe src\data\inject_poisson.py --replicas 10 --seed 42
venv\Scripts\python.exe src\training\train_random_forest.py
venv\Scripts\python.exe src\training\train_cnn.py
```

Dispositivo usado: CPU (`torch 2.14.0+cpu`; `torch.cuda.is_available() == False`).
