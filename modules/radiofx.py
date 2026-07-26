from __future__ import annotations

import numpy as np
from scipy.signal import butter, lfilter


def _bandpass(samples: np.ndarray, sr: int, low: float, high: float) -> np.ndarray:
    nyq = 0.5 * sr
    low_n = max(low / nyq, 1e-4)
    high_n = min(high / nyq, 0.999)
    if high_n <= low_n:
        return samples
    b, a = butter(4, [low_n, high_n], btype="band")
    return lfilter(b, a, samples)


class RadioFX:
    def __init__(self, cfg: dict):
        cfg = cfg or {}
        self.enabled = bool(cfg.get("enabled", True))
        self.intensity = float(cfg.get("intensity", 0.6))
        self.low = float(cfg.get("bandpass_low_hz", 300))
        self.high = float(cfg.get("bandpass_high_hz", 3000))
        self.noise_level = float(cfg.get("noise_level", 0.004))
        self.distortion = float(cfg.get("distortion", 0.35))
        self.key_click = bool(cfg.get("key_click", True))

    def apply(self, samples: np.ndarray, sr: int) -> tuple[np.ndarray, int]:
        if not self.enabled or samples.size == 0:
            return samples.astype(np.float32), sr

        x = samples.astype(np.float32).copy()
        x = _bandpass(x, sr, self.low, self.high).astype(np.float32)

        drive = 1.0 + self.distortion * self.intensity * 8.0
        x = np.tanh(x * drive)
        bits = int(round(16 - self.distortion * self.intensity * 8))
        bits = max(4, min(16, bits))
        levels = float(2 ** bits)
        x = np.round(x * levels) / levels

        noise_amp = self.noise_level * (0.5 + self.intensity)
        if noise_amp > 0:
            x = x + np.random.normal(0.0, noise_amp, size=x.shape).astype(np.float32)

        if self.key_click:
            burst = self._static_burst(sr, 0.08)
            tail = burst[: int(sr * 0.05)]
            x = np.concatenate([burst, x, tail])

        peak = float(np.max(np.abs(x))) or 1.0
        x = (x / peak) * 0.97
        return x.astype(np.float32), sr

    @staticmethod
    def _static_burst(sr: int, dur: float) -> np.ndarray:
        n = max(1, int(sr * dur))
        env = np.linspace(1.0, 0.0, n) ** 2
        return (np.random.normal(0.0, 0.25, n) * env).astype(np.float32)
