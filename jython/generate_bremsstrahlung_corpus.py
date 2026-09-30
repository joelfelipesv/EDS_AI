# -*- coding: utf-8 -*-
"""
generate_bremsstrahlung_only.py

Genera espectros EDS que contienen SOLO la contribución de bremsstrahlung
(radiacion de frenado), excluyendo picos caracteristicos y fluorescencia.

Usa la API de bajo nivel NISTMonte con el listener BremsstrahlungXRayGeneration3,
que registra unicamente los eventos de frenado. NO aplica ruido Poisson:
el espectro es el valor esperado (analitico + MC).

Uso: ejecutar desde la consola Jython de DTSA-II:
    execfile('ruta/a/jython/generate_bremsstrahlung_only.py')
"""

import os
import sys
import json
import time

# --- CARGA DEL PAQUETE GEN3 (NECESARIO PARA BremsstrahlungXRayGeneration3) ---
sys.packageManager.makeJavaPackage(
    "gov.nist.microanalysis.NISTMonte.Gen3",
    "CharacteristicXRayGeneration3, BremsstrahlungXRayGeneration3, "
    "FluorescenceXRayGeneration3, XRayTransport3",
    None
)

import gov.nist.microanalysis.EPQLibrary as epq
import gov.nist.microanalysis.NISTMonte as nm
import gov.nist.microanalysis.NISTMonte.Gen3 as nm3
import gov.nist.microanalysis.Utility as epu
import dtsa2

# ---------------------------------------------------------------------------
# PARAMETROS
# ---------------------------------------------------------------------------
MATERIALES = [
    ("C",  [epq.Element.C],  [1.0], 2.26),
    ("Si", [epq.Element.Si], [1.0], 2.33),
    ("Al", [epq.Element.Al], [1.0], 2.70),
    ("Cu", [epq.Element.Cu], [1.0], 8.96),
]

E0_KV = 30.0
N_TRAJ = 5000          # Trayectorias MC (mayor = menos ruido de muestreo)
DOSE_NA_S = 60.0
BEAM_CURRENT_NA = 1.0
DETECTOR_NAME = "X_Flash"

OUTPUT_DIR = r"C:/Users/USUARIO/Documents/espectroscopia_rayos_x/data/bremsstrahlung_only"


# ---------------------------------------------------------------------------
# SIMULACION CON SOLO BREMSSTRAHLUNG
# ---------------------------------------------------------------------------
def simular_solo_bremsstrahlung(elementos, fracciones, densidad,
                                e0_kv, n_traj, dose_na_s, detector):
    """
    Simula un espectro que contiene unicamente la contribucion de bremsstrahlung.

    Se conecta unicamente el listener BremsstrahlungXRayGeneration3 al
    MonteCarloSS. Los eventos de caracteristico y fluorescencia NO se registran.

    Retorna un ISpectrumData con las cuentas esperadas (sin Poisson).
    """
    # 1. Construir material
    comp = epq.Composition(elementos, fracciones)
    mat = epq.Material(comp, epq.ToSI.gPerCC(densidad))

    # 2. Crear simulacion Monte Carlo
    mc = nm.MonteCarloSS()
    mc.setBeamEnergy(epq.ToSI.keV(e0_kv))
    gun = nm.GaussianBeam(1.0e-9)
    mc.setElectronGun(gun)

    # 3. Añadir la muestra como una subregión de la cámara
    #    Se crea un bloque grande que representa un material semi-infinito (bulk).
    #    Se necesitan las dimensiones en metros. Un cubo de 1 mm es más que suficiente.
    #    Nota: El constructor de nm.Block puede requerir (punto_inferior, punto_superior).
    #    Ajusta según la firma que encuentres con dir(nm.Block).
    sample_shape = nm.Block([-5.0e-4, -5.0e-4, 0.0], [5.0e-4, 5.0e-4, 1.0e-3]) 
    sample_region = nm.MonteCarloSS.Region(sample_shape, mat)

    # Añadir la región a la cámara de la simulación
    mc.addSubRegion(mc.getChamber(), sample_region)

    # 3. Listener de bremsstrahlung (solo este se conecta)
    brem_gen = nm3.BremsstrahlungXRayGeneration3()
    mc.addXRayListener(brem_gen)

    # 4. Correr trayectorias
    mc.runMultipleTrajectories(n_traj)

    # 5. Extraer los eventos de bremsstrahlung generados
    #    brem_gen expone los eventos como una lista de XRayEvent
    eventos = brem_gen.getEvents()

    # 6. Construir un espectro vacio con la geometria del detector
    #    Usamos la energia y canales del detector real.
    zero_offset_ev = detector.getZeroOffset()
    channel_width_ev = detector.getChannelWidth()
    channel_count = detector.getChannelCount()

    counts = [0.0] * channel_count
    for ev in eventos:
        energia_ev = ev.getEnergy()
        canal = int(round((energia_ev - zero_offset_ev) / channel_width_ev))
        if 0 <= canal < channel_count:
            counts[canal] += 1.0

    # 7. Escalar por dosis: cada trayectoria representa un electron;
    #    la dosis real se obtiene multiplicando por (dose_na_s / (n_traj * e))
    #    Aqui simplemente devolvemos la forma espectral normalizada.
    total = sum(counts)
    if total > 0:
        counts = [c / total for c in counts]

    espectro = epq.SpectrumUtils.createSpectrum(
        counts, zero_offset_ev, channel_width_ev, channel_count
    )
    return espectro


def guardar_csv(espectro, nombre_archivo, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    ruta = os.path.join(output_dir, nombre_archivo)
    zo = espectro.getZeroOffset()
    cw = espectro.getChannelWidth()
    n = espectro.getChannelCount()
    with open(ruta, "w") as f:
        f.write("energy_keV,counts\n")
        for ch in range(n):
            e_kev = (zo + ch * cw) / 1000.0
            f.write("%.6f,%.6f\n" % (e_kev, espectro.getCounts(ch)))
    return ruta


def main():
    print("=" * 70)
    print("GENERADOR DE BREMSSTRAHLUNG PURO (sin picos, sin Poisson)")
    print("=" * 70)

    det = findDetector(DETECTOR_NAME)
    if det is None:
        raise RuntimeError("Detector '%s' no encontrado" % DETECTOR_NAME)

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    metadata = []
    for nombre, elementos, fracciones, densidad in MATERIALES:
        print("\n[MATERIAL] %s" % nombre)
        espectro = simular_solo_bremsstrahlung(
            elementos, fracciones, densidad,
            E0_KV, N_TRAJ, DOSE_NA_S, det
        )
        archivo = "%s_brem_only.csv" % nombre
        ruta = guardar_csv(espectro, archivo, OUTPUT_DIR)
        metadata.append({
            "archivo": archivo,
            "material": nombre,
            "elementos": [str(e) for e in elementos],
            "fracciones": fracciones,
            "densidad_g_cm3": densidad,
            "e0_kv": E0_KV,
            "n_traj": N_TRAJ,
            "with_poisson": False,
            "tipo": "bremsstrahlung_only"
        })
        print("[OK] %s -> %s" % (nombre, ruta))

    with open(os.path.join(OUTPUT_DIR, "metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)

    print("\n[OK] Corpus generado en: %s" % OUTPUT_DIR)


if __name__ == "__main__":
    main()