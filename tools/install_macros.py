#!/usr/bin/env python3
"""Install the macro module and the engine package into the LibreOffice profile.

Copies, never symlinks, so the installed code is exactly what the user can read.
"""
from __future__ import annotations

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))


def target_dir():
    for base in (os.path.expanduser("~/.config/libreoffice/4/user"),
                 os.path.expanduser("~/.var/app/org.libreoffice.LibreOffice/config/"
                                    "libreoffice/4/user")):
        if os.path.isdir(base):
            return os.path.join(base, "Scripts", "python")
    return os.path.join(os.path.expanduser("~/.config/libreoffice/4/user"),
                        "Scripts", "python")


def install_to(dest):
    os.makedirs(dest, exist_ok=True)
    shutil.copy2(os.path.join(ROOT, "macros", "retplan_macros.py"), dest)
    pkg_dst = os.path.join(dest, "retplan")
    if os.path.isdir(pkg_dst):
        shutil.rmtree(pkg_dst)
    shutil.copytree(os.path.join(ROOT, "retplan"), pkg_dst,
                    ignore=shutil.ignore_patterns("__pycache__"))
    return dest


def main():
    dest = sys.argv[1] if len(sys.argv) > 1 else target_dir()
    install_to(dest)
    print(f"installed macros to {dest}")
    print("  retplan_macros.py and the retplan package")
    try:
        import numpy
        print(f"  numpy {numpy.__version__} available - vectorised engine enabled")
    except ImportError:
        print("  WARNING: numpy not found for this interpreter; the engine needs it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
