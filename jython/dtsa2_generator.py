# -*- coding: utf-8 -*-
"""
dtsa2_generator.py - Simulacion analitica de espectros EDS de elementos puros con NIST DTSA-II.

Este script se ejecuta dentro del interprete Jython integrado de NIST DTSA-II
(Menu: Tools -> Command Line; o bien `python dtsa2_generator.py` con DTSA-II en el classpath).

Para cada elemento de la lista ELEMENTS:
    1. Se crea el material del elemento puro.
    2. Se simula el espectro de forma analitica (modelo phi(rho*z)) con una dosis total
       de DOSE_NA_S (nC = nA * s) a una energia de haz BEAM_ENERGY_KV.
    3. Se exporta el espectro como CSV en data/raw/[Elemento]_20keV.csv.

Requisitos:
    - DTSA-II instalado y arrancado (proporciona el entorno de scripting, incluida la
      funcion global `findDetector` y los paquetes `epq` / `gov.nist.microanalysis.dtsa2`).
    - Un detector configurado en las Preferencias de DTSA-II cuyo nombre coincida con
      DETECTOR_NAME. El valor "Generico" es un marcador temporal: se debe sustituir por
      el nombre real del detector (p. ej. "Bruker 5", "Eleysi Slim 30", etc.). Con
      findDetector, si el nombre no coincide, se usara el primer detector configurado.
"""

import os
import sys

import gov.nist.microanalysis.EPQLibrary as epq
import gov.nist.microanalysis.dtsa2 as dtsa2

# ---------------------------------------------------------------------------
# Parametros de la simulacion
# ---------------------------------------------------------------------------
BEAM_ENERGY_KV = 20.0               # keV  - Energia del haz de electrones.
DOSE_NA_S = 60.0                    # nA*s -> nC - Dosis total absorbida.
PROBE_CURRENT_NA = 1.0              # nA   - Corriente de sonda del microscopio.
LIVE_TIME_S = DOSE_NA_S / PROBE_CURRENT_NA     # s, de modo que 1.0 x 60 = 60 nA*s.
TAKEOFF_ANGLE_DEG = 40.0            # deg  - Angulo de salida de los rayos X.

# Nombre del detector definido en Preferencias de DTSA-II. Cambiar por el real.
# Con findDetector, si "Generico" no coincide con ninguno, se usara el primer detector.
DETECTOR_NAME = "Generico"

# Lista de elementos puros a simular (simbolos quimicos validos en EPQ).
ELEMENTS = ["Fe", "Cu", "Si", "Au", "Ti", "Al", "Zn"]

# Obtener el directorio del script actual (funciona en Jython)
if hasattr(sys, 'argv') and sys.argv[0]:
    script_dir = os.path.dirname(sys.argv[0])
else:
    # Fallback a directorio de trabajo actual
    script_dir = os.getcwd()

# Directorio de salida: <proyecto>/data/raw/
# Suponemos que el script está en jython/, por lo que subimos un nivel.
PROJECT_ROOT = os.path.dirname(script_dir)
RAW_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "raw")


def get_detector(name):
    """
    Devuelve el detector DTSA-II configurado cuyo nombre es `name`.

    Se usa la utilidad estandar de scripting `findDetector`, que DTSA-II inyecta como
    global en el interprete Jython. Si `name` no coincide con ningun detector,
    `findDetector` devuelve el primer detector configurado (por lo que se imprime un
    aviso aclarando cual se esta usando).

    Args:
        name (str): Nombre del detector (p. ej. "Generico").

    Returns:
        Detector: Instancia de detector EDS.

    Raises:
        RuntimeError: Si no hay detectores o si `findDetector` no esta disponible.
    """
    try:
        detector = findDetector(name)
    except NameError:
        raise RuntimeError(
            "findDetector(...) no esta disponible. Ejecute este script desde el "
            "interprete Jython de DTSA-II (Tools -> Command Line)."
        )
    if detector is None:
        raise RuntimeError(
            "No hay detectores configurados en DTSA-II. Configure uno en "
            "Preferencias de DTSA-II o ajuste DETECTOR_NAME en este script."
        )
    if not detector.toString().startswith(name):
        print("[INFO] No se encontro un detector '%s'; se usara: %s"
              % (name, detector.toString()))
    return detector


def create_material(element_symbol):
    """
    Crea el material del elemento puro indicado por su simbolo quimico.

    Args:
        element_symbol (str): Simbolo quimico (p. ej. "Fe").

    Returns:
        Material: Material homogeneo del elemento puro.
    """
    element = epq.Element.byName(element_symbol)
    return epq.MaterialFactory.createPureElement(element)


def simulate_spectrum_element(element_symbol, detector, e0_kv, dose_na_s,
                              probe_current_na, live_time_s, takeoff_deg):
    """
    Simula analiticamente el espectro EDS de un elemento puro.

    La dosis (en nA*s, equivalentes a nC) se fija mediante el par corriente de
    sonda x tiempo de vida: dose = probe_current * live_time.

    Args:
        element_symbol (str): Simbolo quimico del elemento puro.
        detector (Detector): Detector EDS configurado.
        e0_kv (float): Energia del haz en keV.
        dose_na_s (float): Dosis total en nA*s (= nC).
        probe_current_na (float): Corriente de sonda en nA.
        live_time_s (float): Tiempo de vida (adquisicion) en segundos.
        takeoff_deg (float): Angulo de salida en grados.

    Returns:
        ISpectrumData: Espectro simulado sin ruido de conteo estocastico.
    """
    material = create_material(element_symbol)

    props = epq.SpectrumProperties()
    props.setNumericProperty(epq.SpectrumProperties.BeamEnergy, e0_kv)
    # Corriente de sonda: FaradayBegin es la propiedad que SpectrumUtils lee para
    # computar la dosis, por lo que se fijan ambos para consistencia.
    props.setNumericProperty(epq.SpectrumProperties.ProbeCurrent, probe_current_na)
    props.setNumericProperty(epq.SpectrumProperties.FaradayBegin, probe_current_na)
    props.setNumericProperty(epq.SpectrumProperties.LiveTime, live_time_s)
    props.setNumericProperty(epq.SpectrumProperties.TakeOffAngle, takeoff_deg)
    props.setDetector(detector)

    # Simulador analitico con contribucion de radiacion de frenado (bremsstrahlung).
    spectrum = epq.SpectrumSimulator.Basic.generateSpectrum(material, props, True)
    print("[INFO] Simulado %s @ %g keV, dosis %g nA*s (curva phi(rho*z))."
          % (element_symbol, e0_kv, dose_na_s))
    return spectrum


def save_spectrum_csv(spectrum, element_symbol, e0_kv, output_dir):
    """
    Exporta el espectro simulado a un archivo CSV de dos columnas.

    Columnas: energia de canal en keV y conteos (intensidad) en ese canal.

    Args:
        spectrum (ISpectrumData): Espectro a exportar.
        element_symbol (str): Simbolo del elemento para nombrar el archivo.
        e0_kv (float): Energia del haz usada en el nombre del archivo.
        output_dir (str): Directorio donde se guarda el archivo.

    Returns:
        str: Ruta absoluta del archivo CSV generado.
    """
    # Crear directorio si no existe (compatible con Python 2)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    filename = "%s_%dkV.csv" % (element_symbol, int(round(e0_kv)))
    path = os.path.join(output_dir, filename)

    zero_offset_ev = spectrum.getZeroOffset()        # eV del canal 0.
    channel_width_ev = spectrum.getChannelWidth()    # eV por canal.
    channel_count = spectrum.getChannelCount()

    with open(path, "w") as csv_file:
        csv_file.write("energy_keV,counts\n")
        for ch in range(channel_count):
            energy_keV = (zero_offset_ev + ch * channel_width_ev) / 1000.0
            counts = spectrum.getCounts(ch)
            csv_file.write("%.6f,%.6f\n" % (energy_keV, counts))

    print("[OK] Espectro de %s exportado a: %s" % (element_symbol, path))
    return path


def main():
    """Punto de entrada principal: simula y exporta todos los elementos."""
    separador = "=" * 66
    print(separador)
    print("NIST DTSA-II - Generacion analitica de espectros EDS (elementos puros)")
    print(separador)
    print("[INFO] Energia de haz:      %g keV" % BEAM_ENERGY_KV)
    print("[INFO] Dosis total:         %g nA*s (nC)" % DOSE_NA_S)
    print("[INFO] Detector:            %s" % DETECTOR_NAME)
    print("[INFO] Elementos a simular: %s" % ", ".join(ELEMENTS))
    print("[INFO] Directorio de salida: %s" % RAW_OUTPUT_DIR)
    print("-" * 66)

    detector = get_detector(DETECTOR_NAME)

    for element_symbol in ELEMENTS:
        try:
            spectrum = simulate_spectrum_element(
                element_symbol,
                detector,
                BEAM_ENERGY_KV,
                DOSE_NA_S,
                PROBE_CURRENT_NA,
                LIVE_TIME_S,
                TAKEOFF_ANGLE_DEG,
            )
            save_spectrum_csv(spectrum, element_symbol, BEAM_ENERGY_KV, RAW_OUTPUT_DIR)
        except Exception as exc:  # noqa: BLE001 - Reporta y continua con el resto.
            print("[ERROR] Elemento %s fallo: %s" % (element_symbol, exc))

    print("-" * 66)
    print("[INFO] Proceso finalizado.")


# Ejecutar cuando se invoca directamente desde el interprete Jython de DTSA-II.
if __name__ == "__main__":
    main()