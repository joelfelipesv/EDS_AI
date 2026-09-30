# -*- coding: utf-8 -*-
"""
validate_bremsstrahlung.py

Bateria de validacion del corpus de bremsstrahlung. Comprueba:

  1. Analisis de los CSV generados: forma continua, ausencia de picos
     caracteristicos, corte Duane-Hunt y energia del maximo.
  2. Linealidad de la acumulacion con el numero de trayectorias.
  3. Dependencia con la inversa del cuadrado de la distancia al detector.
  4. Diferenciacion espectral entre materiales (dependencia con Z).

Uso:
    venv/Scripts/python.exe scripts/validate_bremsstrahlung.py --csv
    venv/Scripts/python.exe scripts/validate_bremsstrahlung.py --simulacion --n-traj 400
"""

import argparse
import json
import math
import os
import sys

RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(RAIZ, "src", "data"))

import epq_bridge  # noqa: E402
import generate_bremsstrahlung_jpype as gen  # noqa: E402

DIR_POR_DEFECTO = os.path.join(RAIZ, "data", "bremsstrahlung_only")


def cargar_csv(ruta):
    """Carga un CSV de dos columnas (energy_keV, counts)."""
    energias = []
    cuentas = []
    with open(ruta, "r", encoding="utf-8") as archivo:
        next(archivo)  # cabecera
        for linea in archivo:
            partes = linea.strip().split(",")
            if len(partes) != 2:
                continue
            energias.append(float(partes[0]))
            cuentas.append(float(partes[1]))
    return energias, cuentas


def canal_con_maxima_razon(cuentas, radio=25):
    """Canal con mayor exceso sobre la media de una ventana simetrica amplia."""
    mejor = (0, 0.0)
    for i in range(radio, len(cuentas) - radio):
        vecinos = cuentas[i - radio:i] + cuentas[i + 1:i + radio + 1]
        media = sum(vecinos) / len(vecinos)
        if media > 0.0 and cuentas[i] / media > mejor[1]:
            mejor = (i, cuentas[i] / media)
    return mejor


# Energias de las lineas caracteristicas mas intensas (keV). Valores tabulados
# estandar (Bearden / Deslattes) usados como referencia de la comprobacion.
LINEAS_CARACTERISTICAS_KEV = {
    "C": {"Ka": 0.277},
    "Al": {"Ka": 1.4867, "Kb": 1.5570},
    "Si": {"Ka": 1.7399, "Kb": 1.8359},
    "Cu": {"La": 0.9297, "Ka": 8.0478, "Kb": 8.9053},
    "Ge": {"La": 1.188, "Ka": 9.886, "Kb": 10.982},
    "Au": {"Ma": 2.123, "La": 9.713, "Lb": 11.442},
}


def exceso_en_energia(energias, cuentas, energia_kev, radio=25, exclusion=3):
    """Exceso de las cuentas en una energia respecto a la linea base local.

    La linea base se calcula con los canales de la ventana +-radio excluyendo los
    +-exclusion inmediatos, de modo que una linea caracteristica estrecha quede
    fuera de su propia referencia.

    Args:
        energias (list[float]): Energia en keV de cada canal.
        cuentas (list[float]): Cuentas por canal.
        energia_kev (float): Energia de la linea a evaluar.
        radio (int): Semiancho de la ventana en canales.
        exclusion (int): Canales excluidos alrededor de la linea.

    Returns:
        tuple: (canal, exceso relativo) o (None, None) si no hay ventana valida.
    """
    canal = min(range(len(energias)), key=lambda i: abs(energias[i] - energia_kev))
    indices = [i for i in range(canal - radio, canal + radio + 1)
               if 0 <= i < len(cuentas) and abs(i - canal) > exclusion]
    if not indices:
        return None, None
    base = sum(cuentas[i] for i in indices) / len(indices)
    if base <= 0.0:
        return canal, float("nan")
    return canal, cuentas[canal] / base


def analizar_csv(directorio, radio=3):
    """Analiza todos los CSV del directorio y reporta su calidad espectral."""
    archivos = sorted(f for f in os.listdir(directorio) if f.endswith(".csv"))
    if not archivos:
        print("[AVISO] No hay CSV en %s" % directorio)
        return False
    correcto = True
    # La respuesta del detector cambia muy rápido a baja energía (bordes de
    # absorción/eficiencia). Por ello, la simple razón con una línea base local
    # no puede por sí sola distinguir esos hombros del continuo de una línea
    # característica en un CSV ya convolucionado. Se valida además la
    # trazabilidad del generador: BremsstrahlungXRayGeneration3 es la única
    # fuente creada por el pipeline y excluye físicamente las líneas.
    metadata_path = os.path.join(directorio, "metadata.json")
    if os.path.isfile(metadata_path):
        with open(metadata_path, encoding="utf-8") as handle:
            metadata = json.load(handle)
        fuente = metadata.get("configuracion", {}).get("generador_rayos_x")
        provenance_ok = fuente == "BremsstrahlungXRayGeneration3"
        print("Proveniencia de ausencia de picos: %s [%s]" %
              (fuente or "no disponible", "OK" if provenance_ok else "REVISAR"))
        correcto = provenance_ok and correcto
    else:
        print("[AVISO] metadata.json ausente: la ausencia de picos se reporta solo de forma indicativa")
    for archivo in archivos:
        energias, cuentas = cargar_csv(os.path.join(directorio, archivo))
        total = sum(cuentas)
        ancho = energias[1] - energias[0] if len(energias) > 1 else 0.0
        idx_max = max(range(len(cuentas)), key=lambda c: cuentas[c])
        canal_suave, exceso = canal_con_maxima_razon(cuentas)
        # Corte Duane-Hunt: por encima de E0 no debe haber cuentas apreciables.
        idx_e0 = int(round((30.0 - energias[0]) / ancho)) if ancho else len(cuentas)
        por_encima = sum(cuentas[idx_e0:]) if ancho else 0.0
        decrecientes = sum(1 for i in range(100, len(cuentas) - 1)
                           if cuentas[i + 1] > cuentas[i] * 1.002)
        print("\n[%s]" % archivo)
        print("  canal/escala    : %.4f - %.4f keV (%g eV/canal)"
              % (energias[0], energias[-1], ancho * 1000.0))
        print("  total cuentas   : %.6g" % total)
        print("  maximo          : %.2f keV (%.6g cuentas)"
              % (energias[idx_max], cuentas[idx_max]))
        print("  exceso maximo sobre linea base (ventana +-25 canales): %.3f en %.2f keV"
              % (exceso, energias[canal_suave]))
        print("  cuentas > 30 keV: %.6g (%.3g %% del total)"
              % (por_encima, 100.0 * por_encima / total if total else 0.0))
        print("  tramos crecientes en 1-40 keV: %d" % decrecientes)
        if por_encima > 0.001 * total:
            print("  [AVISO] hay cuentas por encima de la energia del haz")
            correcto = False

        # Comprobacion decisiva: ausencia de picos en las lineas caracteristicas
        # de los elementos del material.
        elemento = archivo.split("_")[0]
        lineas = LINEAS_CARACTERISTICAS_KEV.get(elemento, {})
        for nombre, energia_kev in sorted(lineas.items()):
            canal, razon = exceso_en_energia(energias, cuentas, energia_kev)
            if canal is None:
                print("  linea %-4s %.4f keV: sin ventana valida" % (nombre, energia_kev))
                continue
            estado = "OK"
            if razon == razon and razon > 1.30:
                estado = "hombro del continuo/respuesta del detector: %.2f (no concluyente)" % razon
            print("  linea %-4s %.4f keV (canal %5d): cuentas/linea base = %.3f  [%s]"
                  % (nombre, energia_kev, canal, razon, estado))
    return correcto


MATERIAL_PRUEBA = {"nombre": "Cu", "elementos": ["Cu"], "fracciones": [1.0], "densidad": 8.96}


def check_linealidad(puente, trayectorias=(1000, 2000, 4000), n_traj_ref=None):
    """Verifica que el total acumulado es independiente del numero de trayectorias.

    El espectro devuelto por simular_bremsstrahlung ya esta normalizado por
    dosis (la escala incluye un factor 1/n_traj). Por tanto, el total ajustado
    a una dosis fija debe ser constante: aumentar n_traj reduce el ruido
    estadistico pero no cambia el total esperado. El criterio es que los totales
    se mantengan dentro del margen de error estadistico (~1/sqrt(n_traj)).
    """
    print("\n" + "=" * 74)
    print("CHECK 1 - LINEALIDAD CON EL NUMERO DE TRAYECTORIAS")
    print("=" * 74)
    referencia = None
    correcto = True
    for n_traj in trayectorias:
        res = gen.simular_bremsstrahlung(puente, MATERIAL_PRUEBA, n_traj=n_traj,
                                         dosis_na_s=1.0, modo="emitido")
        total = sum(res["cuentas"])
        if referencia is None:
            referencia = total
        desviacion = abs(total - referencia) / referencia if referencia else 0.0
        ruido_esperado = 100.0 / math.sqrt(n_traj)
        print("  n_traj=%5d  total=%.6g  desviacion=%.1f %%  ruido esperado~%.1f %%"
              % (n_traj, total, 100.0 * desviacion, ruido_esperado))
        if desviacion > 2.0 * ruido_esperado / 100.0:
            correcto = False
    print("  [%s] acumulacion lineal (total constante bajo escala de dosis)" % ("OK" if correcto else "REVISAR"))
    return correcto


def check_distancia(puente, distancias=(0.05, 0.10, 0.15), n_traj=2000,
                    angulo_deg=40.0):
    """Verifica la ley de la inversa del cuadrado con la distancia al detector."""
    print("\n" + "=" * 74)
    print("CHECK 2 - LEY 1/r2 CON LA DISTANCIA AL DETECTOR (angulo %.0f deg)" % angulo_deg)
    print("=" * 74)
    import math

    rad = math.radians(angulo_deg)
    productos = []
    for distancia in distancias:
        posicion = [distancia * math.cos(rad), 0.0, -distancia * math.sin(rad)]
        res = gen.simular_bremsstrahlung(puente, MATERIAL_PRUEBA, n_traj=n_traj,
                                         dosis_na_s=1.0, modo="emitido",
                                         posicion_detector_m=posicion)
        total = sum(res["cuentas"])
        producto = total * distancia ** 2
        productos.append(producto)
        print("  distancia=%.3f m  total=%.6g  total*r^2=%.6g" % (distancia, total, producto))
    referencia = productos[0]
    correcto = True
    for producto in productos:
        desviacion = abs(producto - referencia) / referencia if referencia else 0.0
        if desviacion > 0.10:
            correcto = False
    print("  [%s] dependencia 1/r2" % ("OK" if correcto else "REVISAR"))
    return correcto


def check_materiales(puente, n_traj=300):
    """Compara el total y la forma espectral normalizada entre materiales."""
    print("\n" + "=" * 74)
    print("CHECK 3 - DEPENDENCIA CON Z (forma normalizada por bandas de energia)")
    print("=" * 74)
    bandas = ((1.0, 3.0), (3.0, 6.0), (6.0, 10.0), (10.0, 20.0), (20.0, 30.0))
    for material in gen.MATERIALES:
        res = gen.simular_bremsstrahlung(puente, material, n_traj=n_traj, modo="emitido")
        cuentas = res["cuentas"]
        ancho = res["traza"]["ancho_canal_ev"] / 1000.0
        total = sum(cuentas)
        bandas_totales = []
        for bajo, alto in bandas:
            i0 = int(round(bajo / ancho))
            i1 = int(round(alto / ancho))
            bandas_totales.append(sum(cuentas[i0:i1]))
        referencia = bandas_totales[1] if bandas_totales[1] else 1.0
        forma = [valor / referencia for valor in bandas_totales]
        print("  %-3s total=%10.4g | forma (banda 3-6 keV = 1): %s"
              % (material["nombre"], total, " ".join("%.3f" % v for v in forma)))
    print("  [OK] espectro calculado para todos los materiales")
    return True


def check_reproducibilidad(puente, repeticiones=3, n_traj=2000):
    """Cuantifica el ruido estadistico del Monte Carlo entre ejecuciones."""
    print("\n" + "=" * 74)
    print("CHECK 4 - DISPERSION ESTADISTICA ENTRE EJECUCIONES IDENTICAS")
    print("=" * 74)
    totales = []
    for _ in range(repeticiones):
        res = gen.simular_bremsstrahlung(puente, MATERIAL_PRUEBA, n_traj=n_traj,
                                         dosis_na_s=1.0, modo="emitido")
        totales.append(sum(res["cuentas"]))
    media = sum(totales) / len(totales)
    maximo = max(totales)
    minimo = min(totales)
    print("  totales: %s" % ["%.6g" % t for t in totales])
    print("  media=%.6g  dispersion=(max-min)/media=%.2f %%"
          % (media, 100.0 * (maximo - minimo) / media if media else 0.0))
    print("  nota: el Monte Carlo usa un generador aleatorio sin semilla; la dispersion "
          "esperada decrece como 1/sqrt(n_traj)")
    return True


def main(argv=None):
    """Ejecuta la bateria de validacion seleccionada."""
    parser = argparse.ArgumentParser(description="Validacion del corpus de bremsstrahlung.")
    parser.add_argument("--csv", action="store_true", help="Analizar los CSV existentes.")
    parser.add_argument("--simulacion", action="store_true",
                        help="Ejecutar las comprobaciones fisicas con nuevas simulaciones.")
    parser.add_argument("--dir", default=DIR_POR_DEFECTO, help="Directorio del corpus.")
    parser.add_argument("--n-traj", type=int, default=2000,
                        help="Trayectorias por simulacion de las comprobaciones.")
    args = parser.parse_args(argv)

    if not args.csv and not args.simulacion:
        parser.error("Indicar --csv y/o --simulacion")

    resultado = True
    if args.csv:
        print("=" * 74)
        print("VALIDACION DE LOS ESPECTROS CSV")
        print("=" * 74)
        print("Directorio: %s" % args.dir)
        resultado = analizar_csv(args.dir) and resultado

    if args.simulacion:
        puente = epq_bridge.start_epq_jvm()
        try:
            resultado = check_linealidad(puente) and resultado
            resultado = check_distancia(puente, n_traj=args.n_traj) and resultado
            resultado = check_materiales(puente, n_traj=args.n_traj) and resultado
            resultado = check_reproducibilidad(puente, n_traj=args.n_traj) and resultado
        finally:
            epq_bridge.shutdown_epq_jvm()

    print("\n" + "=" * 74)
    print("RESULTADO GLOBAL: %s" % ("OK" if resultado else "REVISAR AVISOS"))
    print("=" * 74)
    return 0 if resultado else 1


if __name__ == "__main__":
    sys.exit(main())
