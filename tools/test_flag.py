#!/usr/bin/env python3
# Offline flag tester - see README, "Testing without being in game".
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import yaml  # noqa: E402

from modules.flagger import Flagger  # noqa: E402
from modules import llm as llm_mod  # noqa: E402

USAGE = """Usage: test_flag.py [options] "radio line" ["another line" ...]

  --all             force every flag type on and scope them to "all"
  --speak           read the dispatch reply out loud (real TTS + radio effect)
  --no-alert        with --speak, skip the alert tone
  --config PATH     use another config.yaml
  --config appdata  use the installed app's config in %APPDATA%
"""


def _appdata_config() -> str:
    base = os.environ.get("APPDATA")
    if not base:
        return ""
    return os.path.join(base, "911 Dispatch Relay", "config.yaml")


def _resolve_config(explicit: str) -> str:
    if explicit:
        if explicit.strip().lower() in ("appdata", "installed"):
            return _appdata_config()
        return explicit
    return os.path.join(_ROOT, "config.yaml")


def _scope_report(flagger: Flagger, cfg_path: str) -> None:
    own = ", ".join(flagger.own_callsigns) if flagger.own_callsigns else "(none)"
    print("config: %s" % cfg_path)
    print("own_callsigns: %s   code6 scope: %s   cad scope: %s"
          % (own, flagger.code6_scope, flagger.cad_scope))
    print("dedup_cooldown_sec: %g" % flagger.dedup_cooldown)
    print("mdc lookups: %s   mdc scope: %s"
          % ("on" if flagger.mdc_enabled else "off (pass --all to force it on)",
             flagger.mdc_scope))


def _other_config_note(cfg_path: str) -> None:
    other = _appdata_config()
    if not other or not os.path.exists(other):
        return
    if os.path.abspath(other) == os.path.abspath(cfg_path):
        return
    print("note: the installed app saves its settings to a different file -")
    print("      %s" % other)
    print("      pass --config appdata to test with those settings instead.")


def _why_nothing(flagger: Flagger, lines) -> None:
    text = " ".join(lines).lower()
    if not flagger.mdc_enabled and ("code ten" in text or "code 10" in text
                                    or "plate" in text):
        print("")
        print("Why? MDC lookups are switched off in this config")
        print("(mdc_lookup: enabled: false). Turn them on in Settings ->")
        print("Enable MDC lookups, or pass --all to force them on here.")
    if not flagger.own_callsigns:
        print("")
        print("Why? No call signs are set in this config, and anything scoped to")
        print('"own" only answers your own units. Set them under:')
        print("")
        print("   location:")
        print('     callsigns: ["25T15"]')
        print("")
        print("(in the app: Settings -> Your call signs, then press Save)")
        print("Or pass --all to ignore scope while testing.")


def main() -> int:
    argv = list(sys.argv[1:])
    force_all = False
    speak = False
    alert = True
    cfg_arg = ""
    lines: list[str] = []

    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--all":
            force_all = True
        elif a == "--speak":
            speak = True
        elif a == "--no-alert":
            alert = False
        elif a in ("-h", "--help"):
            print(USAGE)
            return 0
        elif a == "--config":
            i += 1
            cfg_arg = argv[i] if i < len(argv) else ""
        elif a.startswith("--config="):
            cfg_arg = a.split("=", 1)[1]
        else:
            lines.append(a)
        i += 1

    cfg_path = _resolve_config(cfg_arg)
    if not cfg_path or not os.path.exists(cfg_path):
        print("No config file at: %s" % (cfg_path or "(unknown)"))
        return 1
    with open(cfg_path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    fcfg = dict(cfg.get("flagging", {}) or {})
    # The app hands the flagger the call signs and the MDC block, otherwise
    # anything scoped to "own" - and every code ten / plate run - is ignored.
    fcfg["own_callsigns"] = (cfg.get("location", {}) or {}).get("callsigns", []) or []
    fcfg["mdc_lookup"] = dict(cfg.get("mdc_lookup", {}) or {})
    if force_all:
        for key in ("code_six", "code_seven", "cad_updates", "clear", "opg",
                    "end_of_watch", "out_status", "alarms", "panic", "radio"):
            if isinstance(fcfg.get(key), dict):
                fcfg[key] = dict(fcfg[key], scope="all", enabled=True)
        fcfg["mdc_lookup"] = dict(fcfg["mdc_lookup"], enabled=True, scope="all")

    flagger = Flagger(fcfg)
    lcfg = dict(cfg.get("llm", {}) or {}, api_key="")
    processor = llm_mod.LLMProcessor(lcfg)

    if not lines:
        if sys.stdin.isatty():
            print(USAGE)
            return 1
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
    _scope_report(flagger, cfg_path)
    if not cfg_arg:
        _other_config_note(cfg_path)
    print("-" * 60)

    flags = flagger.process(lines)
    if not flags:
        print("RESULT: nothing flagged  (this text would be IGNORED)")
        _why_nothing(flagger, lines)
        return 0

    spoken: list[str] = []
    for f in flags:
        ftype = f.get("type", "?")
        raw = f.get("raw") or f.get("body") or ""
        print("FLAGGED [%s]  %s" % (ftype.upper(), raw))
        if ftype == "mdc":
            print("   LOOKUP: %s %s   (this tool stops here - only the app"
                  " opens the MDC and reads the record)"
                  % (f.get("lookup", "?"), f.get("target", "?")))
        try:
            dispatch = processor.process(f)
        except Exception as exc:  # pragma: no cover - defensive
            dispatch = ""
            print("   (dispatch build error: %s)" % exc)
        if dispatch:
            print("   DISPATCH: %s" % dispatch)
            spoken.append(dispatch)

    if speak:
        if not spoken:
            print("-" * 60)
            print("Nothing to speak - no dispatch reply was built.")
            return 0
        from speak_util import speak_lines

        return speak_lines(cfg, spoken, alert=alert)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
