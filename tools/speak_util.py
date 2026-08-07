#!/usr/bin/env python3
# Shared audio playback for the offline test tools. Speaks exactly the way the
# app does: TTS -> radio effect -> optional alert tone -> sound device.
from __future__ import annotations

import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _prepend_alert(cfg: dict, samples, sr: int):
    try:
        from main import AlertSound, SCRIPT_DIR

        alert = AlertSound(cfg.get("alert", {}) or {}, base_dir=SCRIPT_DIR)
        return alert.prepend(samples, sr)
    except Exception as exc:
        print("   (alert tone skipped: %s)" % exc)
        return samples


def speak_lines(cfg: dict, texts, alert: bool = True) -> int:
    """Speak each dispatch line out loud. Returns 0 on success."""
    texts = [t for t in texts if t and t.strip()]
    if not texts:
        return 0

    try:
        from modules.tts import TTSEngine
        from modules.radiofx import RadioFX
        from modules.player import AudioPlayer
    except Exception as exc:
        print("-" * 60)
        print("Cannot play audio: %s" % exc)
        print("Install the audio packages first:")
        print("   py -m pip install -r requirements.txt")
        return 1

    try:
        from modules.llm import spell_plates, strip_ten_codes
    except Exception:  # pragma: no cover - defensive
        def strip_ten_codes(t):
            return t

        def spell_plates(t):
            return t

    print("-" * 60)
    tts = TTSEngine(cfg.get("tts", {}) or {})
    fx = RadioFX(cfg.get("radiofx", {}) or {})
    player = AudioPlayer(cfg.get("playback", {}) or {})
    rc = 0
    try:
        for text in texts:
            spoken = spell_plates(strip_ten_codes(text))
            print("SPEAKING: %s" % spoken)
            try:
                samples, sr = tts.synthesize(spoken)
                samples, sr = fx.apply(samples, sr)
                if alert:
                    samples = _prepend_alert(cfg, samples, sr)
                if not player.enqueue(samples, sr):
                    print("   (playback queue full - dropped)")
                    rc = 1
            except Exception as exc:
                print("   TTS/FX error: %s" % exc)
                rc = 1

        queue_obj = getattr(player, "_q", None)
        if queue_obj is not None:
            queue_obj.join()
        else:  # pragma: no cover - defensive
            while player.pending():
                time.sleep(0.2)
            time.sleep(2.0)
    finally:
        try:
            player.stop()
        except Exception:
            pass
    return rc
