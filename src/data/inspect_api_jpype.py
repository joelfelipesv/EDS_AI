# -*- coding: utf-8 -*-
"""
inspect_api_jpype.py

Diagnostico de la API de NIST EPQ accesible desde JPype. Inicia la JVM con el
classpath de DTSA-II, importa los paquetes EPQLibrary / NISTMonte / Gen3 y
volca la firma real de las clases clave (constructores y metodos) en
`src/data/inspect_api_output.txt`.

El objetivo es obtener las firmas reales del JAR de esta instalacion concreta
(15.1.50) en lugar de inferirlas de la documentacion, que suele estar
desactualizada.

Uso:
    venv/Scripts/python.exe src/data/inspect_api_jpype.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import jpype

import dtsa2_env
import epq_bridge

OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inspect_api_output.txt")

EPQ_LIB = "gov.nist.microanalysis.EPQLibrary"
NISTMONTE = "gov.nist.microanalysis.NISTMonte"
GEN3 = "gov.nist.microanalysis.NISTMonte.Gen3"

# Clases cuyo API interesa volcar: nombre Java completo.
CLASES = [
    NISTMONTE + ".MonteCarloSS",
    NISTMONTE + ".MonteCarloSS$Region",
    NISTMONTE + ".MonteCarloSS$RegionBase",
    NISTMONTE + ".MonteCarloSS$ElectronGun",
    NISTMONTE + ".GaussianBeam",
    NISTMONTE + ".Chamber",
    NISTMONTE + ".MultiPlaneShape",
    NISTMONTE + ".BasicMaterialModel",
    GEN3 + ".BremsstrahlungXRayGeneration3",
    GEN3 + ".BaseXRayGeneration3",
    GEN3 + ".BaseXRayGeneration3$XRay",
    GEN3 + ".BaseXRayGeneration3$BremsstrahlungXRay",
    GEN3 + ".XRayTransport3",
    EPQ_LIB + ".Composition",
    EPQ_LIB + ".Material",
    EPQ_LIB + ".ToSI",
    EPQ_LIB + ".SpectrumUtils",
    EPQ_LIB + ".Element",
    EPQ_LIB + ".Detector.EDSDetector",
    EPQ_LIB + ".Detector.IXRayDetector",
    EPQ_LIB + ".Detector.DetectorProperties",
    EPQ_LIB + ".Bremsstrahlung",
]


class Tee(object):
    """Duplica la salida por consola y por archivo."""

    def __init__(self, path):
        self.file = open(path, "w", encoding="utf-8")
        self.stdout = sys.stdout

    def write(self, texto):
        self.stdout.write(texto)
        self.file.write(texto)

    def flush(self):
        self.stdout.flush()
        self.file.flush()

    def close(self):
        self.flush()
        self.file.close()


def firma(miembro):
    """Devuelve la firma legible de un Method o Constructor de Java."""
    try:
        tipos = ", ".join(str(t.getName()) for t in miembro.getParameterTypes())
    except Exception as ex:  # noqa: BLE001 - diagnostico
        return "%s <error leyendo parametros: %s>" % (miembro.getName(), ex)
    try:
        retorno = "%s " % miembro.getReturnType().getName()
    except Exception:  # los constructores no declaran tipo de retorno
        retorno = ""
    return "%s%s(%s)" % (retorno, miembro.getName(), tipos)


def volcar_clase(nombre_java):
    """Imprime constructores y metodos declarados de una clase Java."""
    print("\n" + "=" * 78)
    print("CLASE %s" % nombre_java)
    print("=" * 78)
    try:
        cls = jpype.JClass(nombre_java)
    except Exception as ex:  # noqa: BLE001 - diagnostico
        print("  [NO DISPONIBLE] %s" % ex)
        return None

    try:
        constructores = sorted(firma(c) for c in cls.class_.getDeclaredConstructors())
    except Exception as ex:  # noqa: BLE001
        constructores = ["<error: %s>" % ex]
    print("  -- Constructores (%d) --" % len(constructores))
    for item in constructores:
        print("     %s" % item)

    try:
        metodos = sorted(firma(m) for m in cls.class_.getDeclaredMethods())
    except Exception as ex:  # noqa: BLE001
        metodos = ["<error: %s>" % ex]
    print("  -- Metodos declarados (%d) --" % len(metodos))
    for item in metodos:
        print("     %s" % item)
    return cls


def informe(etiqueta, funcion):
    """Ejecuta una operacion y reporta exito o el error exacto."""
    try:
        resultado = funcion()
        print("  [OK]    %-56s -> %r" % (etiqueta, resultado))
        return resultado
    except Exception as ex:  # noqa: BLE001 - diagnostico
        print("  [FALLA] %-56s -> %s: %s" % (etiqueta, type(ex).__name__, ex))
        return None


def build_composition(epq, simbolos, fracciones):
    """Construye una Composition de EPQ a partir de simbolos de elemento."""
    return epq_bridge.build_composition(epq, simbolos, fracciones)


def probar_operaciones(epq, nm, nm3):
    """Comprueba las operaciones concretas que necesita el generador."""
    print("\n" + "=" * 78)
    print("PRUEBAS DE OPERACION (instanciacion real)")
    print("=" * 78)

    informe("ToSI.keV(30.0)", lambda: epq.ToSI.keV(30.0))
    informe("ToSI.gPerCC(8.96)", lambda: epq.ToSI.gPerCC(8.96))
    informe("ToSI.eV(1.0)", lambda: epq.ToSI.eV(1.0))
    informe("Element.Cu", lambda: epq.Element.Cu)
    informe("Composition([Cu],[1.0])", lambda: build_composition(epq, ["Cu"], [1.0]))

    mat = informe("Material(Composition([Cu]), 8.96 g/cc)",
                  lambda: epq.Material(build_composition(epq, ["Cu"], [1.0]),
                                       epq.ToSI.gPerCC(8.96)))
    informe("BasicMaterialModel(mat)", lambda: nm.BasicMaterialModel(mat))
    informe("GaussianBeam(1.0e-9)", lambda: nm.GaussianBeam(1.0e-9))

    mc = informe("MonteCarloSS()", lambda: nm.MonteCarloSS())
    if mc is None:
        return
    informe("mc.setBeamEnergy(ToSI.keV(30))", lambda: mc.setBeamEnergy(epq.ToSI.keV(30.0)))
    informe("mc.setElectronGun(GaussianBeam)", lambda: mc.setElectronGun(nm.GaussianBeam(1.0e-9)))
    informe("mc.getChamber()", lambda: mc.getChamber())
    informe("mc.getChamber().getSubRegions()", lambda: mc.getChamber().getSubRegions())
    informe("MultiPlaneShape.createSubstrate([0,0,-1], 1e-3)",
            lambda: nm.MultiPlaneShape.createSubstrate(
                jpype.JArray(jpype.JDouble)([0.0, 0.0, -1.0]), 1.0e-3))

    shape = nm.MultiPlaneShape.createSubstrate(
        jpype.JArray(jpype.JDouble)([0.0, 0.0, -1.0]), 1.0e-3)
    msm = nm.BasicMaterialModel(mat)
    region_cls = jpype.JClass(NISTMONTE + ".MonteCarloSS$Region")
    informe("MonteCarloSS$Region(chamber, shape, msm)",
            lambda: region_cls(mc.getChamber(), shape, msm))
    region = informe("MonteCarloSS$Region reutilizable",
                     lambda: region_cls(mc.getChamber(), shape, msm))
    if region is not None:
        informe("chamber.addSubRegion(region)",
                lambda: mc.getChamber().addSubRegion(region))
        informe("chamber.getSubRegions().size()",
                lambda: mc.getChamber().getSubRegions().size())

    brem = informe("BremsstrahlungXRayGeneration3.create(mc)",
                   lambda: nm3.BremsstrahlungXRayGeneration3.create(mc))
    if brem is not None:
        informe("brem.getEventCount()", lambda: brem.getEventCount())
        informe("mc.runMultipleTrajectories(50)", lambda: mc.runMultipleTrajectories(50))
        informe("brem.getEventCount() tras 50 trayectorias", lambda: brem.getEventCount())
        informe("primer evento getEnergy() [J]", lambda: brem.getXRay(0).getEnergy())
        informe("primer evento getIntensity() [fotones]",
                lambda: brem.getXRay(0).getIntensity())
        informe("primer evento getEnergy()/ToSI.eV(1) [eV]",
                lambda: brem.getXRay(0).getEnergy() / epq.ToSI.eV(1.0))
        informe("primer evento getPosition()", lambda: brem.getXRay(0).getPosition())
        informe("evento es BremsstrahlungXRay",
                lambda: brem.getXRay(0).getClass().getName())
    informe("XRayTransport3.create(mc, endPoint, brem)",
            lambda: nm3.XRayTransport3.create(
                mc, jpype.JArray(jpype.JDouble)([0.0, 0.0, 0.03]), brem))


def main():
    tee = Tee(OUTPUT_PATH)
    sys.stdout = tee
    try:
        print("DIAGNOSTICO DE API - NIST EPQ mediante JPype")
        print("=" * 78)
        print(dtsa2_env.describe())
        print("jpype           : %s" % jpype.__version__)

        bridge = epq_bridge.start_epq_jvm()
        try:
            epq, nm, nm3 = bridge.epq, bridge.nm, bridge.nm3
            print("Acceso a paquetes EPQLibrary / NISTMonte / Gen3: OK")

            for nombre in CLASES:
                volcar_clase(nombre)

            print("\n" + "=" * 78)
            print("CLASES DE PRIMER NIVEL DISPONIBLES EN LOS JAR")
            print("=" * 78)
            paquetes = (
                dtsa2_env.NISTMONTE_PACKAGE,
                dtsa2_env.GEN3_PACKAGE,
                dtsa2_env.EPQ_PACKAGE,
                dtsa2_env.EPQ_PACKAGE + ".Detector",
            )
            for paquete in paquetes:
                print("\n  %s" % paquete)
                print("     %s" % ", ".join(dtsa2_env.listar_clases(paquete)))

            probar_operaciones(epq, nm, nm3)
        finally:
            epq_bridge.shutdown_epq_jvm()
        print("\nDiagnostico finalizado.")
    finally:
        sys.stdout = tee.stdout
        tee.close()
        print("Salida guardada en: %s" % OUTPUT_PATH)


if __name__ == "__main__":
    main()