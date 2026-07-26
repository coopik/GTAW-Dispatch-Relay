from __future__ import annotations

import queue
import threading

import numpy as np
import sounddevice as sd


class AudioPlayer:
    def __init__(self, cfg: dict):
        cfg = cfg or {}
        self.device = cfg.get("device")
        self.volume = float(cfg.get("volume", 1.0))
        self.max_queue = int(cfg.get("max_queue", 12))
        self._q: "queue.Queue" = queue.Queue(maxsize=self.max_queue)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def enqueue(self, samples: np.ndarray, sr: int) -> bool:
        try:
            self._q.put_nowait((samples, sr))
            return True
        except queue.Full:
            return False

    def pending(self) -> int:
        return self._q.qsize()

    def flush(self) -> None:
        try:
            while True:
                self._q.get_nowait()
                self._q.task_done()
        except queue.Empty:
            pass
        try:
            sd.stop()
        except Exception:
            pass

    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                samples, sr = self._q.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                data = np.clip(samples * self.volume, -1.0, 1.0)
                if sr > 0:
                    data = np.concatenate(
                        [data, np.zeros(int(sr * 0.35), dtype=data.dtype)]
                    )
                sd.play(data, sr, device=self.device)
                sd.wait()
            except Exception as e:
                print(f"[player] playback error: {e}")
            finally:
                self._q.task_done()

    def stop(self) -> None:
        self._stop.set()
        try:
            sd.stop()
        except Exception:
            pass
