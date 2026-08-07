#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from modules import llm as llm_mod  # noqa: E402
from modules import mdc_parser  # noqa: E402

FIELDS = [
    "lookup", "found", "name", "owner", "plate", "model", "colour", "color",
    "registration", "stolen", "wanted", "has_warrants", "warrant_items",
    "caution_codes", "criminal_points", "felony_count", "misdemeanor_count",
    "arrests", "license", "vehicles", "aliases",
]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Parse a saved MDC page and print what dispatch would say.")
    ap.add_argument("html", help="an MDC record page saved from your browser (Ctrl+S)")
    ap.add_argument("--plate", action="store_true",
                    help="the page is a DMV/plate page instead of a person record")
    ap.add_argument("--callsign", default="25T15", help="callsign to answer")
    ap.add_argument("--target", default=None,
                    help="the name or plate that was asked for")
    ap.add_argument("--speak", action="store_true",
                    help="read the reply out loud (real TTS + radio effect)")
    ap.add_argument("--no-alert", action="store_true",
                    help="with --speak, skip the alert tone")
    args = ap.parse_args()

    if not os.path.exists(args.html):
        print("No such file:", args.html)
        return 1
    try:
        import bs4  # noqa: F401
    except Exception:
        print("This needs beautifulsoup4:  pip install beautifulsoup4")
        return 1

    html = io.open(args.html, encoding="utf-8", errors="ignore").read()
    result = (mdc_parser.parse_plate_result(html) if args.plate
              else mdc_parser.parse_name_result(html))
    if args.target:
        result["target"] = args.target

    print("=" * 62)
    print("WHAT THE PARSER READ")
    print("-" * 62)
    for key in FIELDS:
        if key in result:
            print("  %-18s %s" % (key + ":", result.get(key)))
    print("-" * 62)
    dispatch = llm_mod.build_mdc_response(result, callsign=args.callsign)
    print("DISPATCH: " + dispatch)
    print("=" * 62)

    if args.speak and dispatch:
        import yaml
        from speak_util import speak_lines

        cfg_path = os.path.join(_ROOT, "config.yaml")
        with open(cfg_path, "r", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
        return speak_lines(cfg, [dispatch], alert=not args.no_alert)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
