# Iteraciones de Fase 1

| Iteración | Acción y observación | Corrección / resultado |
| --- | --- | --- |
| 1 | El entorno virtual contenía únicamente `numpy` y `jpype1`; los imports de PyTorch y scikit-learn fallaron. | Se instaló `requirements.txt` y se añadió `joblib>=1.3`. Versiones usadas: Python 3.13.14, JPype 1.7.1, PyTorch 2.14.0+cpu, scikit-learn 1.9.1, matplotlib 3.11.2. |
| 2 | Se amplió EPQ con Ge y Au y se ejecutó la simulación de 2000 trayectorias. | Se obtuvieron seis CSV y `metadata.json` con `C, Al, Si, Cu, Ge, Au`; no falló ningún material. |
| 3 | La validación CSV marcó como picos las variaciones anchas de eficiencia/respuesta del detector a baja energía, aunque la fuente EPQ era exclusivamente `BremsstrahlungXRayGeneration3`. | Se validó explícitamente la trazabilidad de la fuente y se dejó el indicador local como diagnóstico no concluyente para hombros del detector. El corte Duane-Hunt y la validación global pasan. |
| 4 | El preprocesado canónico produjo seis vectores L1. Un split estratificado no es posible con un solo vector por clase. | `inject_poisson.py` conserva el vector canónico y crea 10 realizaciones reproducibles por clase y dosis (60 por nivel), permitiendo 80/20 y 80/10/10 estratificados. `labels_map.json` permanece exactamente con seis claves. |
| 5 | La primera CNN colapsó a una sola clase: las entradas L1 tenían magnitud típica ~1/4096 y la epsilon de BatchNorm predominaba. | Se escaló globalmente la entrada por 4096, sin cambiar su forma ni normalización L1. Se reentrenó desde semilla 42; resultados finales registrados en `reports/cnn_results.txt`. |
| 6 | Se comprobó ROCm mediante `torch.cuda.is_available()`. | La build instalada es `2.14.0+cpu` y devolvió `False`; ambos entrenamientos se ejecutaron en CPU. |
| 7 | El comando compacto de verificación final contenía una comilla sin cerrar dentro de un `f-string`. | Se simplificó la expresión de verificación y se confirmó: 6 CSV, 6 vectores canónicos, 60 vectores por dosis, L1=1.0 y ambos modelos cargables. |
| 8 | `--csv` revisa los archivos pero no ejecuta la prueba dinámica de distancia. | Se ejecutó también `--simulacion --n-traj 2000`: linealidad OK y ley 1/r² OK (`total·r² = 15.5121, 14.9971, 15.2226` para 0.05, 0.10 y 0.15 m). |

La primera inspección local por consola usó una cadena Python con salto de línea escapado incorrectamente y produjo un `SyntaxError`; se sustituyó por comandos de inspección equivalentes y no afectó archivos ni resultados.
