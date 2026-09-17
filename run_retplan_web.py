#!/usr/bin/env python3
"""RetPlan web application launcher.

    python3 run_retplan_web.py                 # http://127.0.0.1:5007
    python3 run_retplan_web.py --host 0.0.0.0 --port 5007
    python3 run_retplan_web.py --reload         # auto-reload while developing

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5007


def _banner(host: str, port: int, version: str) -> None:
    url = f"http://{host if host != '0.0.0.0' else '127.0.0.1'}:{port}"
    print(f"""
  ┌──────────────────────────────────────────────────────────────┐
  │  RetPlan {version:<12}  retirement planning you can audit    │
  ├──────────────────────────────────────────────────────────────┤
  │  {url:<58}│
  │  Ctrl-C to stop                                              │
  └──────────────────────────────────────────────────────────────┘
""")


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the RetPlan web application.")
    ap.add_argument("--host", default=os.environ.get("RETPLAN_HOST", DEFAULT_HOST))
    ap.add_argument("--port", type=int,
                    default=int(os.environ.get("RETPLAN_PORT", DEFAULT_PORT)))
    ap.add_argument("--reload", action="store_true",
                    help="auto-reload on source changes (development only)")
    ap.add_argument("--log-level", default="info",
                    choices=["critical", "error", "warning", "info", "debug"])
    ap.add_argument("--data-dir", default=os.environ.get("RETPLAN_DATA", "data"))
    args = ap.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    try:
        import uvicorn
    except ImportError:
        print("uvicorn is not installed. Create the environment first:\n"
              "    python3 -m venv .venv\n"
              "    .venv/bin/pip install -r requirements.txt", file=sys.stderr)
        return 2

    from retplan import __version__
    from web.retplan_webapp import RetPlanWebApp

    _banner(args.host, args.port, __version__)
    if args.reload:
        os.environ["RETPLAN_DATA"] = args.data_dir
        uvicorn.run("web.retplan_webapp:create_app", host=args.host, port=args.port,
                    reload=True, factory=True, log_level=args.log_level)
    else:
        app = RetPlanWebApp.get_instance(data_dir=args.data_dir).app
        uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)
    return 0


if __name__ == "__main__":
    sys.exit(main())
