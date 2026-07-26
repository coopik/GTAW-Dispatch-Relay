#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml  # noqa: E402

from modules.flagger import Flagger  # noqa: E402
from modules import llm as llm_mod  # noqa: E402


def main() -> int:
    args = [a for a in sys.argv[1:]]
    force_all = False
    if "--all" in args:
        force_all = True
        args = [a for a in args if a != "--all"]

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "config.yaml"), "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    fcfg = dict(cfg.get("flagging", {}) or {})
    if force_all:
        fcfg["code_six"] = dict(fcfg.get("code_six", {}) or {}, scope="all")
        fcfg["cad_updates"] = dict(fcfg.get("cad_updates", {}) or {}, scope="all")

    flagger = Flagger(fcfg)
    lcfg = dict(cfg.get("llm", {}) or {}, api_key="")
    processor = llm_mod.LLMProcessor(lcfg)

    if args:
        lines = args
    else:
        lines = [ln.rstrip("\n") for ln in sys.stdin.read().splitlines()]
    lines = [ln for ln in lines if ln.strip()]

    if not lines:
        print("No input. Pass text as arguments or pipe it on stdin.")
        return 1

    print("=" * 60)
    print("INPUT (%d line(s)):" % len(lines))
    for ln in lines:
        print("   " + ln)
    print("-" * 60)
    own = flagger.own_callsigns
    print("own_callsigns: %s   code6 scope: %s   cad scope: %s"
          % (own or "(none)", flagger.code6_scope, flagger.cad_scope))
    print("dedup_cooldown_sec: %g" % flagger.dedup_cooldown)
    print("-" * 60)

    flags = flagger.process(lines)
    if not flags:
        print("RESULT: nothing flagged  (this text would be IGNORED)")
        return 0

    for f in flags:
        ftype = f.get("type", "?")
        raw = f.get("raw") or f.get("body") or ""
        print("FLAGGED [%s]  %s" % (ftype.upper(), raw))
        try:
            dispatch = processor.process(f)
        except Exception as exc:  # pragma: no cover - defensive
            dispatch = "(dispatch build error: %s)" % exc
        if dispatch:
            print("   DISPATCH: %s" % dispatch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
