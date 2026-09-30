# -*- coding: utf-8 -*-
"""
epq_bridge.py

Puente JPype hacia las clases Java de NIST EPQ (el motor de simulacion de
DTSA-II). Resuelve el ciclo de vida de la JVM y el acceso a las clases.

Restriccion del entorno
-----------------------
El runtime Java distribuido con DTSA-II es una imagen jlink que NO incluye el
modulo `jdk.zipfs`. Por ese motivo `import jpype.imports` (la emulacion de
imports de Python sobre paquetes Java) falla con FileSystemNotFoundException:
su gestor de paquetes necesita abrir los JAR como sistemas de archivos `jar:`.

Como sustituto se usa la clase JavaPackage, que resuelve cada clase de forma
perezosa mediante jpype.JClass y expone la misma sintaxis de atributos:

    bridge = start_epq_jvm()
    mat = bridge.epq.Material(comp, bridge.epq.ToSI.gPerCC(2.7))
    mc  = bridge.nm.MonteCarloSS()
    brem = bridge.nm3.BremsstrahlungXRayGeneration3.create(mc)
"""

import jpype

import dtsa2_env

# Clases anidadas de interes: JPype las resuelve con el separador '$'.
MONTE_CARLO_REGION = dtsa2_env.NISTMONTE_PACKAGE + ".MonteCarloSS$Region"
MONTE_CARLO_ELECTRON_GUN = dtsa2_env.NISTMONTE_PACKAGE + ".MonteCarloSS$ElectronGun"
BASE_XRAY_GENERATION3 = dtsa2_env.GEN3_PACKAGE + ".BaseXRayGeneration3"
BREMSSTRAHLUNG_XRAY = BASE_XRAY_GENERATION3 + "$BremsstrahlungXRay"
ELEMENT = dtsa2_env.EPQ_PACKAGE + ".Element"

# Argumentos de JVM. El flag de acceso nativo elimina los avisos que emite
# JDK 24+ cuando JPype invoca System.load para cargar su puente JNI.
JVM_ARGS = ("--enable-native-access=ALL-UNNAMED", "-Xmx2g")


class JavaPackage(object):
    """Acceso perezoso a las clases de un paquete Java por nombre cualificado."""

    def __init__(self, prefix):
        self.prefix = prefix
        self._cache = {}

    def __getattr__(self, nombre):
        if nombre.startswith("_"):
            raise AttributeError(nombre)
        cls = self._cache.get(nombre)
        if cls is None:
            try:
                cls = jpype.JClass("%s.%s" % (self.prefix, nombre))
            except Exception as ex:  # noqa: BLE001 - se reetiqueta el error
                raise AttributeError(
                    "No existe la clase %s.%s (%s). Si %s es un subpaquete, "
                    "usar subpaquete('%s')." % (self.prefix, nombre, ex, nombre, nombre))
            self._cache[nombre] = cls
        return cls

    def subpaquete(self, nombre):
        """Devuelve un paquete Java anidado, p. ej. EPQLibrary.Detector."""
        return JavaPackage("%s.%s" % (self.prefix, nombre))

    def __dir__(self):
        return sorted(self._cache)

    def __repr__(self):
        return "<paquete Java %s>" % self.prefix


class EpqBridge(object):
    """Contenedor de los paquetes EPQ utilizados por los scripts del proyecto."""

    def __init__(self):
        self.epq = JavaPackage(dtsa2_env.EPQ_PACKAGE)
        self.nm = JavaPackage(dtsa2_env.NISTMONTE_PACKAGE)
        self.nm3 = JavaPackage(dtsa2_env.GEN3_PACKAGE)
        self.detector = JavaPackage(dtsa2_env.EPQ_PACKAGE + ".Detector")
        self.jdouble_array = jpype.JArray(jpype.JDouble)
        self.jelement_array = jpype.JArray(jpype.JClass(ELEMENT))

    def region_class(self):
        """Devuelve la clase MonteCarloSS.Region."""
        return jpype.JClass(MONTE_CARLO_REGION)


def start_epq_jvm(home=None, jvm_args=None, extra_classpath=None):
    """Inicia la JVM con el classpath de DTSA-II y devuelve el puente.

    Args:
        home (str | None): Directorio de DTSA-II. None para autodetectarlo.
        jvm_args (tuple | None): Argumentos de JVM. None usa JVM_ARGS.
        extra_classpath (list[str] | None): JARs o directorios adicionales.

    Returns:
        EpqBridge: Puente con los paquetes epq, nm y nm3.
    """
    if not jpype.isJVMStarted():
        classpath = dtsa2_env.list_jars(home)
        if extra_classpath:
            classpath = classpath + list(extra_classpath)
        jpype.startJVM(dtsa2_env.find_jvm_dll(home),
                       *(jvm_args if jvm_args is not None else JVM_ARGS),
                       classpath=classpath,
                       convertStrings=True)
    return EpqBridge()


def shutdown_epq_jvm():
    """Detiene la JVM si esta activa."""
    if jpype.isJVMStarted():
        jpype.shutdownJVM()


def ev_to_joule():
    """Energia en julios correspondiente a 1 eV (equivale a ToSI.eV(1.0))."""
    return jpype.JClass(dtsa2_env.EPQ_PACKAGE + ".ToSI").eV(1.0)


def joule_per_ev():
    """Energia en eV correspondiente a 1 J. EPQ trabaja internamente en SI."""
    return 1.0 / ev_to_joule()


def build_composition(epq, simbolos, fracciones):
    """Construye una Composition de EPQ a partir de simbolos quimicos.

    Args:
        epq (JavaPackage): Paquete EPQLibrary.
        simbolos (list[str]): Simbolos de elemento, p. ej. ["Fe", "Ni"].
        fracciones (list[float]): Fracciones masicas o atomicas normalizadas.

    Returns:
        Composition: Composicion de EPQ.
    """
    if len(simbolos) != len(fracciones):
        raise ValueError("simbolos y fracciones deben tener la misma longitud")
    elementos = jpype.JArray(jpype.JClass(ELEMENT))(
        [getattr(epq.Element, s) for s in simbolos])
    return epq.Composition(elementos, jpype.JArray(jpype.JDouble)(fracciones))


def build_material(epq, simbolos, fracciones, densidad_g_cm3):
    """Construye un Material de EPQ (Composicion + densidad).

    Args:
        epq (JavaPackage): Paquete EPQLibrary.
        simbolos (list[str]): Simbolos de elemento.
        fracciones (list[float]): Fracciones normalizadas.
        densidad_g_cm3 (float): Densidad en g/cm3.

    Returns:
        Material: Material de EPQ listo para la simulacion.
    """
    comp = build_composition(epq, simbolos, fracciones)
    return epq.Material(comp, epq.ToSI.gPerCC(densidad_g_cm3))