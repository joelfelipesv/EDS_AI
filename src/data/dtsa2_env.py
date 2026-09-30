# -*- coding: utf-8 -*-
"""
dtsa2_env.py

Resolucion del entorno Java necesario para invocar NIST EPQ (Electron Probe
Quantification) desde Python mediante JPype.

EPQ se distribuye precompilado dentro de NIST DTSA-II. El artefacto
`epq-15.1.50.jar` declara `Build-Jdk-Spec: 26` en su manifiesto, de modo que la
JVM del sistema (Java 8, visible en el PATH) no puede cargar sus clases. Es
obligatorio usar el runtime Temurin 26 que el instalador de DTSA-II deja en
`<DTSA2_HOME>/java-runtime`.

Este modulo centraliza la deteccion de rutas para que los scripts de generacion
y de diagnostico no dupliquen logica.
"""

import glob
import os
import zipfile

# Instalaciones conocidas, de mas reciente a mas antigua.
DTSA2_HOME_CANDIDATES = (
    r"C:\Users\USUARIO\AppData\Local\NIST\NIST DTSA-II Polaris 2026-06-24",
    r"C:\Users\USUARIO\AppData\Local\NIST\NIST DTSA-II Oberon 2024-11-22",
)

# JARs que no aportan clases funcionales: relocalizador de jpackage e instalador.
EXCLUDED_JAR_PREFIXES = ("relocate-",)

EPQ_PACKAGE = "gov.nist.microanalysis.EPQLibrary"
NISTMONTE_PACKAGE = "gov.nist.microanalysis.NISTMonte"
GEN3_PACKAGE = "gov.nist.microanalysis.NISTMonte.Gen3"


def find_dtsa2_home():
    """Devuelve la ruta de la instalacion de DTSA-II que contiene el runtime.

    Se puede forzar una ruta concreta mediante la variable de entorno
    DTSA2_HOME.

    Returns:
        str: Ruta absoluta del directorio de instalacion de DTSA-II.

    Raises:
        FileNotFoundError: Si ninguna candidata contiene un runtime Java.
    """
    override = os.environ.get("DTSA2_HOME")
    candidates = ([override] if override else []) + list(DTSA2_HOME_CANDIDATES)
    for candidate in candidates:
        if candidate and os.path.isfile(os.path.join(candidate, "java-runtime", "release")):
            return candidate
    raise FileNotFoundError(
        "No se encontro una instalacion de NIST DTSA-II con runtime Java en: %s"
        % ", ".join(candidates)
    )


def find_jvm_dll(home=None):
    """Devuelve la ruta de jvm.dll del runtime distribuido con DTSA-II.

    Args:
        home (str | None): Directorio de DTSA-II. Si es None se autodetecta.

    Returns:
        str: Ruta absoluta de jvm.dll.

    Raises:
        FileNotFoundError: Si no existe jvm.dll.
    """
    home = home or find_dtsa2_home()
    jvm = os.path.join(home, "java-runtime", "bin", "server", "jvm.dll")
    if not os.path.isfile(jvm):
        raise FileNotFoundError("No se encontro jvm.dll en: %s" % jvm)
    return jvm


def find_epq_jar(home=None):
    """Devuelve la ruta del JAR que contiene EPQLibrary y NISTMonte.

    En las versiones de DTSA-II Polaris el paquete NISTMonte esta empaquetado
    dentro del propio JAR de EPQ, por lo que un unico artefacto basta para
    simular bremsstrahlung.

    Args:
        home (str | None): Directorio de DTSA-II. Si es None se autodetecta.

    Returns:
        str: Ruta absoluta del JAR de EPQ.

    Raises:
        FileNotFoundError: Si no se encuentra ningun JAR de EPQ.
    """
    home = home or find_dtsa2_home()
    matches = sorted(glob.glob(os.path.join(home, "epq*.jar")))
    if not matches:
        raise FileNotFoundError("No se encontro epq*.jar en: %s" % home)
    return matches[-1]


def list_jars(home=None):
    """Lista todos los JARs utilizables del directorio de DTSA-II.

    Se incluyen todas las dependencias declaradas en el manifiesto de EPQ
    (jama, xstream, derby, jgoodies, jna, ...). Incluir JARs no usados es
    inocuo porque la JVM carga las clases de forma perezosa, y evita errores
    NoClassDefFoundError en rutas de codigo secundarias.

    Args:
        home (str | None): Directorio de DTSA-II. Si es None se autodetecta.

    Returns:
        list[str]: Rutas absolutas de los JARs, ordenadas.
    """
    home = home or find_dtsa2_home()
    jars = []
    for path in sorted(glob.glob(os.path.join(home, "*.jar"))):
        nombre = os.path.basename(path)
        if any(nombre.startswith(prefix) for prefix in EXCLUDED_JAR_PREFIXES):
            continue
        jars.append(path)
    return jars


def classpath(home=None):
    """Devuelve el classpath de DTSA-II en formato del sistema operativo."""
    return os.pathsep.join(list_jars(home))


def listar_clases(paquete, home=None):
    """Enumera las clases de primer nivel de un paquete leyendo los JAR.

    La enumeracion por reflexion no es fiable en este runtime (imagen jlink sin
    jdk.zipfs), por lo que se inspeccionan directamente las entradas de los
    archivos JAR.

    Args:
        paquete (str): Nombre cualificado del paquete, p. ej.
            "gov.nist.microanalysis.NISTMonte".
        home (str | None): Directorio de DTSA-II. Si es None se autodetecta.

    Returns:
        list[str]: Nombres simples de las clases de primer nivel, ordenados.
    """
    prefijo = paquete.replace(".", "/") + "/"
    nombres = set()
    for jar in list_jars(home):
        with zipfile.ZipFile(jar) as archivo:
            for entrada in archivo.namelist():
                if not entrada.startswith(prefijo) or not entrada.endswith(".class"):
                    continue
                resto = entrada[len(prefijo):-len(".class")]
                if "/" in resto:
                    continue  # pertenece a un subpaquete
                nombres.add(resto.split("$")[0])
    return sorted(nombres)


def describe(home=None):
    """Devuelve un resumen legible del entorno Java resuelto."""
    home = home or find_dtsa2_home()
    lineas = [
        "DTSA2_HOME      : %s" % home,
        "jvm.dll         : %s" % find_jvm_dll(home),
        "epq jar         : %s" % find_epq_jar(home),
        "JARs en classpath: %d" % len(list_jars(home)),
    ]
    return "\n".join(lineas)


if __name__ == "__main__":
    print(describe())