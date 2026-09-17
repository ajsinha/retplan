#!/usr/bin/env python3
"""Add a folder to LibreOffice's Trusted File Locations.

Scoped, reversible, and done through LibreOffice's own configuration API rather
than by hand-editing registrymodifications.xcu - which LibreOffice rewrites on
exit and would otherwise clobber.

    python3 tools/trust_folder.py [folder]        # default: this repository
    python3 tools/trust_folder.py --list
    python3 tools/trust_folder.py --remove [folder]

LibreOffice must be closed: a running instance owns the profile and will
overwrite the change when it exits.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "build"))

import uno
import unohelp as U

PORT = 2104
NODE = "/org.openoffice.Office.Common/Security/Scripting"


def _running_default_profile():
    try:
        out = subprocess.run(["pgrep", "-a", "soffice"], capture_output=True,
                             text=True).stdout
    except Exception:
        return False
    return any("UserInstallation" not in line for line in out.splitlines() if line.strip())


def _office():
    """Start soffice on the DEFAULT profile so we edit the real settings."""
    if U._port_open(PORT):
        return None
    cmd = [U.SOFFICE, "--headless", "--invisible", "--nologo", "--nodefault",
           "--norestore", f"--accept=socket,host=127.0.0.1,port={PORT};urp;"]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        if U._port_open(PORT):
            return proc
        time.sleep(0.5)
    raise RuntimeError("soffice did not start")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    folder = os.path.abspath(args[0]) if args else ROOT
    url = uno.systemPathToFileUrl(folder).rstrip("/")

    if _running_default_profile():
        print("LibreOffice is running. Close it completely and try again -\n"
              "it owns the profile and will overwrite this change on exit.")
        return 2

    proc = _office()
    try:
        ctx, _ = U.connect(PORT)
        cp = ctx.ServiceManager.createInstanceWithContext(
            "com.sun.star.configuration.ConfigurationProvider", ctx)
        cfg = cp.createInstanceWithArguments(
            "com.sun.star.configuration.ConfigurationUpdateAccess", U.pv(nodepath=NODE))
        current = list(cfg.getPropertyValue("SecureURL") or ())
        level = cfg.getPropertyValue("MacroSecurityLevel")

        if "--list" in flags:
            print(f"macro security level : {level}")
            print("trusted locations    :")
            for u in current or ["(none)"]:
                print("   ", u)
            return 0

        if "--remove" in flags:
            new = [u for u in current if u.rstrip("/") != url]
            action = "removed from"
        else:
            new = current if url in [u.rstrip("/") for u in current] else current + [url]
            action = "already in" if new == current else "added to"

        if new != current:
            # configmgr rejects a bare tuple for a []string property; it has to be
            # handed over as an explicitly typed Any.
            uno.invoke(cfg, "setPropertyValue",
                       ("SecureURL", uno.Any("[]string", tuple(new))))
            cfg.commitChanges()
        print(f"{folder}\n  {action} LibreOffice's trusted file locations")
        print(f"  macro security level stays at {level} (unchanged)")
        print("  trusted locations now:")
        for u in new or ["(none)"]:
            print("   ", u)
        return 0
    finally:
        try:
            ctx, desktop = U.connect(PORT)
            desktop.terminate()               # flush the profile cleanly
        except Exception:
            pass
        time.sleep(2)
        if proc:
            proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
