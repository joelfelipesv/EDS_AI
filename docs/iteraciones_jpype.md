# Iteraciones del Generador JPype de Bremsstrahlung

Registro de las iteraciones de desarrollo del script `generate_bremsstrahlung_jpype.py`,
sus errores y sus correcciones.

## Iteracion 1 - Entorno y arranque de la JVM

### Objetivo

Crear un entorno virtual con JPype e iniciar la JVM cargando los JARs de EPQ
directamente desde la instalacion de DTSA-II, sin usar la consola Jython.

### Estado

- Entorno virtual `venv/` creado con Python 3.13.14.
- JPype1 1.7.1 instalado.
- La instalacion de DTSA-II Polaris (2026-06-24) se encuentra en
  `C:\Users\USUARIO\AppData\Local\NIST\NIST DTSA-II Polaris 2026-06-24`.
- El runtime Java distribuido (`java-runtime`) es Temurin 26 (JDK 26), compatible
  con `epq-15.1.50.jar` (manifiesto `Build-Jdk-Spec: 26`).
- El sistema tenia Java 8 en el PATH, incompatible. Se usa `jvm.dll` del runtime
  de DTSA-II, no el del sistema.

### Problema: `import jpype.imports` falla

La emulacion de imports de Python sobre paquetes Java necesita abrir los JARs
como sistemas de archivos `jar:` (modulo `jdk.zipfs`). La imagen jlink de DTSA-II
no incluye `jdk.zipfs`, por lo que `jpype.imports` lanza
`FileSystemNotFoundException`.

### Solucion

`epq_bridge.py` implementa `JavaPackage`, una clase de acceso perezoso que
resuelve cada clase mediante `jpype.JClass` y expone la misma sintaxis de
atributos (`bridge.epq.Material`, `bridge.nm.MonteCarloSS`, etc.).

## Iteracion 2 - Inspeccion de la API

### Objetivo

Obtener las firmas reales de las clases clave del JAR 15.1.50, en lugar de
inferirlas de la documentacion (que suele estar desactualizada).

### Herramienta

`src/data/inspect_api_jpype.py` volca constructores y metodos de:

- `MonteCarloSS` y `MonteCarloSS$Region`
- `GaussianBeam`, `MultiPlaneShape`
- `BremsstrahlungXRayGeneration3`, `BaseXRayGeneration3`
- `EDSDetector`, `DetectorProperties`
- `Composition`, `Material`, `Element`

Salida: `docs/inspect_api_output.txt` (47 KB; el script `src/data/inspect_api_jpype.py` lo regenera por defecto en `src/data/`).

### Hallazgos clave

| Clase                          | Firma importante                                              |
|---------------------------------|--------------------------------------------------------------|
| `MonteCarloSS.addSubRegion`     | `(Region, Material, Shape)` -> `Region`                      |
| `MonteCarloSS.getChamber`       | `() -> Region`                                                |
| `MonteCarloSS.setBeamEnergy`    | `(double)`                                                    |
| `MonteCarloSS.runMultipleTrajectories` | `(int)`                                                 |
| `MultiPlaneShape.createSubstrate` | `(double[], double[]) -> Shape`                            |
| `BremsstrahlungXRayGeneration3.create` | `(MonteCarloSS) -> BremsstrahlungXRayGeneration3`       |
| `EDSDetector.createSDDDetector` | `(int, double, double)` y `(int, double, double, double)`     |

## Iteracion 3 - Primer script completo

### Objetivo

Crear `generate_bremsstrahlung_jpype.py` con la cadena de simulacion completa:
MonteCarloSS -> GaussianBeam -> MultiPlaneShape -> BremsstrahlungXRayGeneration3
-> XRayTransport3 -> EDSDetector.

### Error

```
[ERROR] C: NameError: name 'zero_ev' is not defined
```

### Causa

La funcion `simular_bremsstrahlung` llamaba a `crear_detector(puente, canales,
ancho_ev, zero_ev)`, pero `zero_ev` no esta definido en el alcance. La funcion
`crear_detector` acepta `resolucion_ev` como cuarto parametro, no `zero_ev`.

### Correccion

Cambiar la llamada a `crear_detector(puente, canales, ancho_ev, resolucion_ev)`.

## Iteracion 4 - Problema de resolucion del detector (0 eV)

### Sintoma

El espectro generado tiene **cero cuentas por debajo de 5.9 keV** y un **spike
exactamente en 5899 eV** (canal 590), que es la energia de Mn K-alpha.

```
Cu_emitido_30kV.csv (antes de la correccion):
  0-1keV:   0.0     <- espectro nulo
  3-6keV:   903.2   <- spike en 5.9 keV
  canal 590 (5.9 keV): 209.1 cuentas  <- spike
  canal 589 (5.89 keV): 0.0            <- cero a un canal del lado
  canal 591 (5.91 keV): 69.8          <- caida abrupta
```

### Diagnostico

El script usaba `RESOLUCION_EV = 0.0`. La fabrica
`createSDDDetector(int, double, double)` interpreta el tercer argumento como la
**resolucion en eV a Mn K-alpha**, no como zero offset. Con resolucion = 0, el
modelo de respuesta del detector se vuelve degenerado: la funcion de respuesta
es una delta en 5899 eV, lo que concentra toda la intensidad en ese canal y
deja el resto del espectro en cero.

### Verificacion con probe

Se creo `scripts/_probe_simulation.py` que comparo tres firmas:

1. 3 args `(4096, 10.0, 0.0)` -> resolucion 0 -> degenerado (spike)
2. 4 args `(4096, 10.0, 0.0, 130.0)` -> resolucion 130 -> continuo
3. 3 args `(4096, 10.0, 130.0)` -> resolucion 130 -> continuo

Los resultados confirmaron que **130 eV de resolucion produce un espectro
continuo con maximo a baja energia (~0.9 keV para Cu) y decaimiento suave hasta
30 keV**, sin picos degenerados.

### Correccion

Cambiar `RESOLUCION_EV` de `0.0` a `130.0` eV. El valor 130 eV corresponde a
una resolucion tipica de un SDD comercial.

## Iteracion 5 - Metadatos completos

### Objetivo

Hacer trazable la configuracion del detector en `metadata.json`.

### Cambios

- Anadir `resolucion_ev` y `gun_width_m` a la seccion `configuracion` del JSON.
- Exponer `--resolucion-ev` y `--gun-width-m` como argumentos de linea de
  comandos.
- Imprimir la resolucion del detector en la cabecera de salida.

## Iteracion 6 - Validacion final

### Resultado de `validate_bremsstrahlung.py --csv`

| Material | Max energia (keV) | Cu K-alpha (Cu) | Al K-alpha | C K-alpha | >30 keV |
|----------|--------------------|-----------------|------------|-----------|---------|
| C        | 0.25               | N/A             | N/A        | 0.28 keV  | 0       |
| Al       | 1.38               | N/A             | 1.49 keV   | N/A       | 0       |
| Si       | 1.51               | N/A             | N/A        | N/A       | 0       |
| Cu       | 0.87               | 8.05 keV        | N/A        | N/A       | 0       |

- **Cu K-alpha (8.048 keV)**: ratio = 1.000 (OK)
- **Cu K-beta (8.905 keV)**: ratio = 1.059 (OK)
- **Cu L-alpha (0.930 keV)**: ratio = 1.167 (OK)
- **Spike en 5.9 keV**: eliminado
- **Duane-Hunt**: cero cuentas por encima de 30 keV

### AVISOS menores

- C K-alpha (0.277 keV): ratio = 3.33 -> el maximo del continuo esta en 0.25 keV,
  la linea caracteristica coincide con el pico del fondo. Fisica, no artefacto.
- Al K-alpha (1.487 keV): ratio = 1.54 -> maximo del continuo en 1.38 keV,
  coincidencia con la linea. Fisica del fondo continuo.

Estos AVISOS son esperables: para elementos de bajo Z, la energia de la linea
caracteristica K-alpha se encuentra cerca del maximo del fondo de
bremsstrahlung. No son picos caracteristicos, sino la forma natural del continuo.

## Iteracion 7 - Validacion de simulacion con n_traj adecuado

### Problema

La validacion con `--simulacion --n-traj 300` producía resultados inestables:
la linealidad mostraba desviaciones del 46-76% y la reproducibilidad un 74% de
dispersion. Esto se debe a que 300 trayectorias son insuficientes para la
estadistica del bremsstrahlung (el rendimiento por trayectoria es ~0.15
eventos X-ray, con alta varianza Poisson).

### Correccion

- `check_linealidad`: comparar `total` (no `total/n_traj`) contra la referencia,
  ya que la escala de dosis ya incluye el factor 1/n_traj. El criterio es que el
  total sea constante dentro de 2x el ruido esperado `1/sqrt(n_traj)`.
- Trajectorias por defecto: 200 -> 1000/2000/4000 para linealidad;
  300 -> 2000 para las demas comprobaciones.

### Resultado final (n_traj=2000)

```
CHECK 1 - LINEALIDAD: OK (0.7% maxima desviacion vs ~1.6% ruido esperado)
CHECK 2 - 1/r2: OK (total*r^2 constante: 15.26, 15.41, 15.15)
CHECK 3 - Z-dependencia: OK (formas espectrales distintas por material)
CHECK 4 - REPROHIBILIDAD: OK (2.9% dispersion vs ~2.2% esperado)
RESULTADO GLOBAL: OK
```
