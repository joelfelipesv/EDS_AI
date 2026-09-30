# Generador de Bremsstrahlung Puro con EPQ + JPype

Script de Python que genera un corpus de espectros EDS de **bremsstrahlung puro**
(sin picos caracteristicos ni fluorescencia) usando la biblioteca Java **EPQ**
(Electron Probe Quantification) de NIST, invocada desde Python mediante **JPype**.

No se necesita abrir la GUI de DTSA-II ni usar su consola Jython.

## Requisitos

### Java

El JAR de EPQ (`epq-15.1.50.jar`) declara `Build-Jdk-Spec: 26` en su manifiesto.
La JVM del sistema (si es mas antigua) no puede cargar las clases. Es obligatorio
usar el runtime Java que instala DTSA-II en su directorio `java-runtime`.

### Python

- Python 3.10+ (probado con 3.13)
- JPype1

### Activar el entorno virtual

Desde la raiz del proyecto:

```
venv\Scripts\activate
```

Salir:

```
venv\Scripts\deactivate
```

## Instalacion de dependencias

El entorno virtual ya existe en `venv/`. Para volver a crearlo:

```bat
python -m venv venv
venv\Scripts\activate
pip install JPype1
```

## Ubicacion de los JARs de EPQ

El script autodetecta la instalacion de DTSA-II y sus JARs. Las rutas candidatas
que inspecciona `dtsa2_env.py` son:

1. Variable de entorno `DTSA2_HOME` (si esta definida).
2. `C:\Users\USUARIO\AppData\Local\NIST\NIST DTSA-II Polaris 2026-06-24`
3. `C:\Users\USUARIO\AppData\Local\NIST\NIST DTSA-II Oberon 2024-11-22`

Dentro de la instalacion, los JARs relevantes son:

| Archivo           | Contenido                                      |
|--------------------|-------------------------------------------------|
| `epq-15.1.50.jar`  | EPQLibrary + NISTMonte + Gen3 (todo en uno)     |
| `dtsa2-15.1.50.jar`| Clases de la consola de DTSA-II (no necesario)  |
| `jama-1.0.3.jar`   | Algebra lineal (dependencia de EPQ)             |
| `xstream-*.jar`    | Serializacion XML (dependencia de EPQ)          |

Se pueden listar los JARs con:

```python
from dtsa2_env import list_jars
print(list_jars())
```

Verificar que un JAR contiene las clases esperadas:

```python
from dtsa2_env import listar_clases
print(listar_clases("gov.nist.microanalysis.EPQLibrary"))
print(listar_clases("gov.nist.microanalysis.NISTMonte"))
print(listar_clases("gov.nist.microanalysis.NISTMonte.Gen3"))
```

## Ejecucion

Desde la raiz del proyecto:

```bat
venv\Scripts\python.exe src\data\generate_bremsstrahlung_jpype.py
```

### Argumentos

| Argumento           | Default | Descripcion                                    |
|----------------------|---------|------------------------------------------------|
| `--output-dir`       | `data\bremsstrahlung_only` | Directorio de salida.             |
| `--modo`             | `emitido`| `emitido`: con atenuacion y eficiencia del det. `generado`: solo emision. |
| `--e0-kv`            | `30.0`   | Energia del haz de electrones en keV.          |
| `--n-traj`           | `2000`   | Numero de trayectorias Monte Carlo.            |
| `--takeoff-deg`      | `40.0`   | Angulo de salida del detector en grados.       |
| `--dosis-na-s`       | `60.0`   | Dosis de referencia en nA*s.                   |
| `--canales`          | `4096`   | Numero de canales del detector.                |
| `--ancho-canal-ev`   | `10.0`   | Ancho de canal en eV.                          |
| `--resolucion-ev`    | `130.0`  | Resolucion del SDD en eV a Mn K-alpha.         |
| `--gun-width-m`      | `1e-9`   | Radio gaussiano del haz en metros.             |
| `--materiales`       | (todos)  | Subconjunto separado por comas: `C,Al,Si,Cu`.  |
| `--poisson`          | off      | Aplicar ruido de Poisson con semilla fija.    |
| `--semilla`          | `20260916` | Semilla para el ruido de Poisson.           |

Ejemplo con mas trayectorias y ruido Poisson:

```bat
venv\Scripts\python.exe src\data\generate_bremsstrahlung_jpype.py --n-traj 5000 --poisson
```

## Archivos de salida

En `data/bremsstrahlung_only/`:

- `C_emitido_30kV.csv`, `Al_emitido_30kV.csv`, `Si_emitido_30kV.csv`, `Cu_emitido_30kV.csv`
- `metadata.json`

Formato CSV: dos columnas `energy_keV,counts`.

## Validacion

```bat
venv\Scripts\python.exe scripts\validate_bremsstrahlung.py --csv
venv\Scripts\python.exe scripts\validate_bremsstrahlung.py --simulacion --n-traj 400
```

## Limitaciones y plan B

### 1. Resolucion del detector

`EDSDetector.createSDDDetector(int canales, double ancho_ev, double resolucion_ev)`
usa la sobrecarga de 3 argumentos. El tercer parametro es la **resolucion en eV
a Mn K-alpha (5899 eV)**, no el zero offset. Un valor de `0.0` produce un
detector degenerado: el espectro queda nulo por debajo de 5.9 keV y aparece un
artefacto en esa energia. El valor por defecto de `130.0` eV reproduce el
comportamiento de un SDD real.

Si el tercer argumento se necesita como zero offset, usar la sobrecarga de 4
argumentos: `createSDDDetector(int, double, double, double)` donde el tercer
argumento es el zero offset y el cuarto la resolucion.

### 2. Listeners personalizados en Python

JPype 1.7.1 no puede despachar callbacks Java desde el runtime JDK 26 que
distribuye DTSA-II (NoSuchMethodError en `org.jpype.proxy.JPypeProxy`). Como
consecuencia, no se pueden escribir listeners de eventos X-ray en Python. La
solucion adoptada es delegar la captura de eventos en el detector nativo
`EDSDetector`, que implementa internamente `IXRayListener` y acumula los
eventos directamente en su espectro interno.

### 3. Aislamiento del bremsstrahlung

El aislamiento es fisico, no filtrado: se instancia unicamente
`BremsstrahlungXRayGeneration3` y se omite `CharacteristicXRayGeneration3` y
`FluorescenceXRayGeneration3`. No existe ninguna via fisica por la que aparezcan
picos en el espectro resultante. En la practica, con resoluciones finitas del
detector, la linea base del continuo puede coincidir con la energia de una linea
caracteristica (especialmente para elementos de bajo Z), pero esto es la
fisica del fondo continuo y no un pico caracteristico.

## Archivos del modulo

| Archivo                              | Descripcion                                       |
|--------------------------------------|--------------------------------------------------|
| `generate_bremsstrahlung_jpype.py`   | Script principal de generacion.                |
| `epq_bridge.py`                      | Puente JPype: gestion de la JVM y acceso a clases. |
| `dtsa2_env.py`                       | Deteccion del entorno Java de DTSA-II.           |
| `inspect_api_jpype.py`               | Script de inspeccion de la API Java.            |
| `inspect_api_output.txt`             | Salida volcada por el script de inspeccion.     |
| `../scripts/jvm_smoke_test.py`       | Prueba de arranque/apagado basico de la JVM.     |
| `../scripts/validate_bremsstrahlung.py` | Bateria de validacion fisica del corpus.    |