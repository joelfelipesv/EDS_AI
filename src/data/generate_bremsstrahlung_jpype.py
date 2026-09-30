# -*- coding: utf-8 -*-
"""
generate_bremsstrahlung_jpype.py

Genera un corpus de espectros EDS que contienen EXCLUSIVAMENTE radiacion de
frenado (bremsstrahlung): sin picos caracteristicos y sin fluorescencia. La
simulacion se ejecuta directamente sobre las clases Java de NIST EPQ (el motor
de DTSA-II) mediante JPype, sin abrir la GUI ni usar la consola Jython.

Cadena de simulacion
--------------------
    MonteCarloSS                    transporte de electrones
      + GaussianBeam                haz gaussiano (radio 1 nm)
      + MultiPlaneShape (substrato) muestra masiva, superficie en z = 0
      + BremsstrahlungXRayGeneration3   UNICA fuente de rayos X
      + XRayTransport3              atenuacion hasta la posicion del detector
      + EDSDetector                 eficiencia del detector y eje de canales

Al no instanciar CharacteristicXRayGeneration3 ni FluorescenceXRayGeneration3,
no existe ninguna via fisica por la que aparezcan picos en el espectro.

Nota sobre el detector de eventos
---------------------------------
La captura de eventos se delega en un EDSDetector nativo de EPQ. Un listener
escrito en Python (jpype.JProxy) NO es utilizable en este entorno: JPype 1.7.1
falla al despachar cualquier callback sobre el runtime JDK 26 que distribuye
DTSA-II (java.lang.NoSuchMethodError dentro de org.jpype.proxy.JPypeProxy).
Ver docs/iteraciones_jpype.md.

Uso:
    venv/Scripts/python.exe src/data/generate_bremsstrahlung_jpype.py
    venv/Scripts/python.exe src/data/generate_bremsstrahlung_jpype.py --n-traj 5000
"""

import argparse
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import jpype

import dtsa2_env
import epq_bridge

PROYECTO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SALIDA_POR_DEFECTO = os.path.join(PROYECTO, "data", "bremsstrahlung_only")

# Materiales del corpus: elemento puro, fraccion masica 1.0 y densidad (g/cm3).
MATERIALES = (
    {"nombre": "C", "elementos": ["C"], "fracciones": [1.0], "densidad": 2.26},
    {"nombre": "Al", "elementos": ["Al"], "fracciones": [1.0], "densidad": 2.70},
    {"nombre": "Si", "elementos": ["Si"], "fracciones": [1.0], "densidad": 2.33},
    {"nombre": "Cu", "elementos": ["Cu"], "fracciones": [1.0], "densidad": 8.96},
    {"nombre": "Ge", "elementos": ["Ge"], "fracciones": [1.0], "densidad": 5.323},
    {"nombre": "Au", "elementos": ["Au"], "fracciones": [1.0], "densidad": 19.30},
)

E0_KV = 30.0                # Energia del haz de electrones.
N_TRAJ = 2000               # Trayectorias Monte Carlo por espectro.
ANGULO_SALIDA_DEG = 40.0    # Angulo de salida (take-off) del detector.
DOSE_NA_S = 60.0            # Dosis de referencia del corpus (nA*s).
CANALES = 4096              # Canales del detector (0 - 40.96 keV a 10 eV/canal).
ANCHO_CANAL_EV = 10.0
ZERO_OFFSET_EV = 0.0        # El detector SDD sintetico arranca en 0 eV.
# Resolucion del detector a la energia de calibracion estandar (Mn K-alfa,
# 5899 eV). Un valor de 0 eV deja el modelo de respuesta degenerado: el espectro
# queda nulo por debajo de 5.9 keV y aparece un artefacto en esa energia. 130 eV
# es el valor tipico de un SDD.
RESOLUCION_EV = 130.0
GUN_WIDTH_M = 1.0e-9        # Radio del haz gaussiano.

# Carga del electron (C). Se usa para convertir dosis (nA*s) en numero de
# electrones incidentes: electrones = dose_A_s / CARGA_ELEMENTAL.
CARGA_ELEMENTAL = 1.602176634e-19

MODOS = ("emitido", "generado")


def crear_muestra(puente):
    """Crea una muestra masiva (substrato semi-infinito) con superficie en z = 0.

    El haz de electrones parte de z = -0.099 m y avanza hacia +z, por lo que el
    solido ocupa el semiespacio z > 0. La normal (0,0,-1) apunta hacia el vacio.
    """
    jd = puente.jdouble_array
    return puente.nm.MultiPlaneShape.createSubstrate(jd([0.0, 0.0, -1.0]),
                                                     jd([0.0, 0.0, 0.0]))


def crear_detector(puente, canales=CANALES, ancho_ev=ANCHO_CANAL_EV,
                   resolucion_ev=RESOLUCION_EV):
    """Crea un detector SDD sintetico con la calibracion indicada.

    La firma real de la fabrica es (canales, ancho de canal en eV, resolucion en
    eV a 5899 eV), verificada por introspeccion sobre el JAR 15.1.50. El detector
    resultante tiene 10 mm2 de area y su posicion por defecto se situa en la
    mitad en vacio de la camara (z < 0).
    """
    return puente.detector.EDSDetector.createSDDDetector(int(canales), float(ancho_ev),
                                                         float(resolucion_ev))


def extraer_cuentas(espectro):
    """Extrae el vector de cuentas y la calibracion de un ISpectrumData.

    Returns:
        tuple: (cuentas, zero_offset_ev, ancho_canal_ev, n_canales)
    """
    n = int(espectro.getChannelCount())
    cuentas = [float(espectro.getCounts(c)) for c in range(n)]
    return cuentas, float(espectro.getZeroOffset()), float(espectro.getChannelWidth()), n


def exceso_linea_base(cuentas, radio=25):
    """Maximo exceso de un canal sobre la media de una ventana simetrica amplia.

    Se usa una ventana de +-radio canales en lugar de vecinos inmediatos para no
    confundir los escalones de eficiencia del detector (bordes de absorcion, que
    son monotonos) con estructuras tipo pico. En un continuo suave el valor se
    mantiene proximo a 1.

    Args:
        cuentas (list[float]): Cuentas por canal.
        radio (int): Semiancho de la ventana en canales.

    Returns:
        float: Mayor exceso relativo encontrado.
    """
    razon = 0.0
    for i in range(radio, len(cuentas) - radio):
        vecinos = cuentas[i - radio:i] + cuentas[i + 1:i + radio + 1]
        media = sum(vecinos) / len(vecinos)
        if media > 0.0:
            razon = max(razon, cuentas[i] / media)
    return razon


def perfil_resumen(cuentas, zero_ev, ancho_ev):
    """Resumen numerico del espectro para la metadata."""
    n = len(cuentas)
    total = sum(cuentas)
    canal_max = max(range(n), key=lambda c: cuentas[c]) if n else 0
    no_nulos = sum(1 for c in cuentas if c > 0.0)
    return {
        "total_cuentas": total,
        "canal_maximo": canal_max,
        "energia_maxima_keV": (zero_ev + canal_max * ancho_ev) / 1000.0,
        "canales_no_nulos": no_nulos,
        "exceso_linea_base": exceso_linea_base(cuentas),
    }


def simular_bremsstrahlung(puente, material, e0_kv=E0_KV, n_traj=N_TRAJ, modo="emitido",
                           angulo_salida_deg=ANGULO_SALIDA_DEG, canales=CANALES,
                           ancho_ev=ANCHO_CANAL_EV, resolucion_ev=RESOLUCION_EV,
                           dosis_na_s=DOSE_NA_S, posicion_detector_m=None):
    """Simula un espectro de bremsstrahlung puro para un material masivo.

    Solo se instancia BremsstrahlungXRayGeneration3. Al no crear los generadores
    de rayos X caracteristicos ni de fluorescencia, no existe ninguna via fisica
    que introduzca picos en el espectro resultante.

    Args:
        puente (epq_bridge.EpqBridge): Puente JPype con la JVM ya iniciada.
        material (dict): Nombre, elementos, fracciones y densidad.
        e0_kv (float): Energia del haz en keV.
        n_traj (int): Numero de trayectorias Monte Carlo.
        modo (str): "emitido" (transporte hasta el detector) o "generado".
        angulo_salida_deg (float): Angulo de salida del detector en grados.
        canales (int): Numero de canales del detector.
        ancho_ev (float): Ancho de canal en eV.
        resolucion_ev (float): Resolucion del detector en eV a 5899 eV.
        dosis_na_s (float): Dosis de referencia del corpus, en nA*s.
        posicion_detector_m (list[float] | None): Posicion explicita del detector
            en metros. Si es None se usa mc.computeDetectorPosition con el
            angulo de salida indicado.

    Returns:
        dict: Cuentas por canal, calibracion del detector y trazabilidad.
    """
    epq, nm, nm3 = puente.epq, puente.nm, puente.nm3
    mat = epq_bridge.build_material(epq, material["elementos"], material["fracciones"],
                                    material["densidad"])

    mc = nm.MonteCarloSS()
    mc.setBeamEnergy(epq.ToSI.keV(e0_kv))
    mc.setElectronGun(nm.GaussianBeam(GUN_WIDTH_M))
    mc.addSubRegion(mc.getChamber(), mat, crear_muestra(puente))

    generador = nm3.BremsstrahlungXRayGeneration3.create(mc)
    detector = crear_detector(puente, canales, ancho_ev, resolucion_ev)

    traza = {"modo": modo}
    if modo == "emitido":
        if posicion_detector_m is not None:
            posicion = puente.jdouble_array([float(v) for v in posicion_detector_m])
            traza["posicion_explicita"] = True
        else:
            radianes = math.radians(angulo_salida_deg)
            posicion = mc.computeDetectorPosition(radianes, 0.0)
            traza["posicion_explicita"] = False
        traza["posicion_detector_m"] = [float(v) for v in posicion]
        traza["distancia_detector_m"] = math.sqrt(sum(float(v) ** 2 for v in posicion))
        transporte = nm3.XRayTransport3.create(mc, posicion, generador)
        transporte.addXRayListener(detector)
        traza["ruta_eventos"] = "BremsstrahlungXRayGeneration3 -> XRayTransport3 -> EDSDetector"
    elif modo == "generado":
        generador.addXRayListener(detector)
        traza["ruta_eventos"] = "BremsstrahlungXRayGeneration3 -> EDSDetector"
        traza["advertencia"] = ("La escala absoluta de este modo no esta calibrada; "
                               "unicamente la forma espectral es significativa.")
    else:
        raise ValueError("Modo no soportado: %s (validos: %s)" % (modo, ", ".join(MODOS)))

    inicio = time.time()
    mc.runMultipleTrajectories(int(n_traj))
    traza["segundos"] = time.time() - inicio

    # getSpectrum(1.0) devuelve el espectro acumulado por el detector: la dosis
    # es un factor escala lineal (getSpectrum(1.0) equivale al acumulado puro,
    # mientras que getSpectrum() sin argumento devuelve un objeto vacio).
    cuentas, z, w, n = extraer_cuentas(detector.getSpectrum(1.0))

    electrones = dosis_na_s * 1.0e-9 / CARGA_ELEMENTAL
    escala = electrones / float(n_traj)
    cuentas = [c * escala for c in cuentas]

    traza.update({
        "zero_offset_ev": z,
        "ancho_canal_ev": w,
        "canales": n,
        "n_traj": int(n_traj),
        "e0_keV": e0_kv,
        "dosis_na_s": dosis_na_s,
        "electrones_dosis": electrones,
        "escala_cuentas": escala,
    })
    return {"cuentas": cuentas, "traza": traza}


def guardar_csv(cuentas, ruta, zero_ev, ancho_ev):
    """Guarda el espectro como CSV de dos columnas: energy_keV, counts.

    Se respeta el mismo formato que los generadores Jython del proyecto.
    """
    directorio = os.path.dirname(ruta)
    if directorio and not os.path.isdir(directorio):
        os.makedirs(directorio)
    with open(ruta, "w", encoding="utf-8") as archivo:
        archivo.write("energy_keV,counts\n")
        for canal, valor in enumerate(cuentas):
            energia_kev = (zero_ev + canal * ancho_ev) / 1000.0
            archivo.write("%.6f,%.6f\n" % (energia_kev, valor))
    return ruta


def aplicar_poisson(cuentas, semilla):
    """Aplica ruido de Poisson al valor esperado del espectro."""
    import numpy as np

    generador = np.random.default_rng(semilla)
    return [float(v) for v in generador.poisson(np.asarray(cuentas, dtype=float))]


def parsear_argumentos(argv=None):
    """Define los argumentos de linea de comandos del generador."""
    parser = argparse.ArgumentParser(
        description="Genera un corpus de espectros de bremsstrahlung puro con NIST EPQ + JPype.")
    parser.add_argument("--output-dir", default=SALIDA_POR_DEFECTO,
                        help="Directorio de salida (por defecto data/bremsstrahlung_only).")
    parser.add_argument("--modo", choices=MODOS, default="emitido",
                        help="emitido: con atenuacion y eficiencia del detector. "
                             "generado: solo emision (escala no calibrada).")
    parser.add_argument("--e0-kv", type=float, default=E0_KV, help="Energia del haz en keV.")
    parser.add_argument("--n-traj", type=int, default=N_TRAJ,
                        help="Trayectorias Monte Carlo por espectro.")
    parser.add_argument("--takeoff-deg", type=float, default=ANGULO_SALIDA_DEG,
                        help="Angulo de salida del detector en grados.")
    parser.add_argument("--dosis-na-s", type=float, default=DOSE_NA_S,
                        help="Dosis de referencia en nA*s.")
    parser.add_argument("--canales", type=int, default=CANALES, help="Canales del detector.")
    parser.add_argument("--ancho-canal-ev", type=float, default=ANCHO_CANAL_EV,
                        help="Ancho de canal en eV.")
    parser.add_argument("--resolucion-ev", type=float, default=RESOLUCION_EV,
                        help="Resolucion del detector en eV a Mn K-alpha (5899 eV).")
    parser.add_argument("--gun-width-m", type=float, default=GUN_WIDTH_M,
                        help="Radio gaussiano del haz de electrones en metros.")
    parser.add_argument("--materiales", default="",
                        help="Subconjunto separado por comas (C,Al,Si,Cu,Ge,Au). Vacio: todos.")
    parser.add_argument("--poisson", action="store_true",
                        help="Aplicar ruido de Poisson con semilla fija.")
    parser.add_argument("--semilla", type=int, default=20260916, help="Semilla del ruido.")
    return parser.parse_args(argv)


def seleccionar_materiales(filtro):
    """Filtra la lista de materiales segun un argumento tipo 'C,Cu'."""
    if not filtro:
        return list(MATERIALES)
    pedidos = [nombre.strip() for nombre in filtro.split(",") if nombre.strip()]
    disponibles = {m["nombre"]: m for m in MATERIALES}
    desconocidos = [nombre for nombre in pedidos if nombre not in disponibles]
    if desconocidos:
        raise ValueError("Materiales no definidos: %s (disponibles: %s)"
                         % (", ".join(desconocidos), ", ".join(disponibles)))
    return [disponibles[nombre] for nombre in pedidos]


def main(argv=None):
    """Genera el corpus completo y su metadata."""
    args = parsear_argumentos(argv)
    materiales = seleccionar_materiales(args.materiales)
    if not os.path.isdir(args.output_dir):
        os.makedirs(args.output_dir)

    print("=" * 74)
    print("CORPUS DE BREMSSTRAHLUNG PURO - NIST EPQ mediante JPype")
    print("=" * 74)
    print(dtsa2_env.describe())
    print("modo            : %s" % args.modo)
    print("E0              : %g keV" % args.e0_kv)
    print("trayectorias    : %d por espectro" % args.n_traj)
    print("angulo de salida: %g deg" % args.takeoff_deg)
    print("dosis           : %g nA*s" % args.dosis_na_s)
    print("detector        : %d canales, %g eV/canal, %g eV resolucion @MnKa" % (args.canales, args.ancho_canal_ev, args.resolucion_ev))
    print("gun width       : %g m" % args.gun_width_m)
    print("materiales      : %s" % ", ".join(m["nombre"] for m in materiales))
    print("ruido Poisson   : %s" % ("si" if args.poisson else "no"))

    puente = epq_bridge.start_epq_jvm()
    registros = []
    try:
        for material in materiales:
            print("-" * 74)
            print("[MATERIAL] %s" % material["nombre"])
            try:
                resultado = simular_bremsstrahlung(
                    puente, material, e0_kv=args.e0_kv, n_traj=args.n_traj, modo=args.modo,
                    angulo_salida_deg=args.takeoff_deg, canales=args.canales,
                    ancho_ev=args.ancho_canal_ev, resolucion_ev=args.resolucion_ev,
                    dosis_na_s=args.dosis_na_s)
            except Exception as ex:  # noqa: BLE001 - se documenta y se continua
                print("[ERROR] %s: %s: %s" % (material["nombre"], type(ex).__name__, ex))
                registros.append({"material": material["nombre"], "error": str(ex)})
                continue

            traza = resultado["traza"]
            cuentas = resultado["cuentas"]
            cuentas_guardadas = (aplicar_poisson(cuentas, args.semilla)
                                 if args.poisson else cuentas)
            archivo = "%s_%s_%dkV.csv" % (material["nombre"], args.modo,
                                          int(round(args.e0_kv)))
            ruta = guardar_csv(cuentas_guardadas, os.path.join(args.output_dir, archivo),
                               traza["zero_offset_ev"], traza["ancho_canal_ev"])
            resumen = perfil_resumen(cuentas_guardadas, traza["zero_offset_ev"],
                                     traza["ancho_canal_ev"])
            print("[OK] %s | total=%.4g cuentas | max en %.2f keV | %.1f s | exceso max sobre linea base=%.2f"
                  % (ruta, resumen["total_cuentas"], resumen["energia_maxima_keV"],
                     traza["segundos"], resumen["exceso_linea_base"]))

            registro = {
                "archivo": archivo,
                "material": material["nombre"],
                "elementos": list(material["elementos"]),
                "fracciones": list(material["fracciones"]),
                "densidad_g_cm3": material["densidad"],
                "tipo": "bremsstrahlung_only",
                "with_poisson": bool(args.poisson),
                "semilla": args.semilla if args.poisson else None,
            }
            registro.update(traza)
            registro.update(resumen)
            registros.append(registro)
    finally:
        epq_bridge.shutdown_epq_jvm()

    metadata = {
        "descripcion": "Espectros EDS de bremsstrahlung puro (sin picos caracteristicos "
                       "ni fluorescencia) simulados con NIST EPQ mediante JPype.",
        "entorno": {
            "dtsa2_home": dtsa2_env.find_dtsa2_home(),
            "jvm_dll": dtsa2_env.find_jvm_dll(),
            "epq_jar": dtsa2_env.find_epq_jar(),
            "jpype": jpype.__version__,
            "python": sys.version.split()[0],
        },
        "configuracion": {
            "modo": args.modo,
            "e0_keV": args.e0_kv,
            "n_traj": args.n_traj,
            "angulo_salida_deg": args.takeoff_deg,
            "dosis_na_s": args.dosis_na_s,
            "canales": args.canales,
            "ancho_canal_ev": args.ancho_canal_ev,
            "generador_rayos_x": "BremsstrahlungXRayGeneration3",
            "resolucion_ev": args.resolucion_ev,
            "gun_width_m": args.gun_width_m,
            "materiales": [m["nombre"] for m in materiales],
        },
        "espectros": registros,
    }
    ruta_metadata = os.path.join(args.output_dir, "metadata.json")
    with open(ruta_metadata, "w", encoding="utf-8") as archivo:
        json.dump(metadata, archivo, indent=2, ensure_ascii=False)

    print("-" * 74)
    print("[OK] Corpus generado en: %s" % args.output_dir)
    print("[OK] Metadata: %s" % ruta_metadata)
    return 0


if __name__ == "__main__":
    sys.exit(main())
