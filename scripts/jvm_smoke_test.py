# -*- coding: utf-8 -*-
"""
jvm_smoke_test.py

Verificacion minima de que JPype puede iniciar y cerrar la JVM del runtime
Temurin 26 distribuido con NIST DTSA-II. No carga todavia el JAR de EPQ.

Uso:
    venv/Scripts/python.exe scripts/jvm_smoke_test.py
"""

import os
import sys

import jpype

RUNTIME_JVM = (
    r"C:\Users\USUARIO\AppData\Local\NIST\NIST DTSA-II Polaris 2026-06-24"
    r"\java-runtime\bin\server\jvm.dll"
)


def main():
    if not os.path.isfile(RUNTIME_JVM):
        raise FileNotFoundError("No se encontro jvm.dll en: %s" % RUNTIME_JVM)

    jpype.startJVM(RUNTIME_JVM, "-Xmx1g")
    try:
        system = jpype.JClass("java.lang.System")
        print("[OK] JVM iniciada. jpype=%s" % jpype.__version__)
        print("[OK] java.version=%s" % system.getProperty("java.version"))
        print("[OK] java.home=%s" % system.getProperty("java.home"))
        print("[OK] jpype.getDefaultJVMPath()=%s" % jpype.getDefaultJVMPath())
    finally:
        jpype.shutdownJVM()
        print("[OK] JVM cerrada. isJVMStarted=%s" % jpype.isJVMStarted())


if __name__ == "__main__":
    sys.exit(main())