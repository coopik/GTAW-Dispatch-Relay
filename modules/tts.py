from __future__ import annotations

import io
import os
import re
import tempfile
import threading

import numpy as np

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/"

_FFMPEG_READY = False

_DIGIT_WORDS = {
    "0": "oh",
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
}


def verbalize_numbers(text: str) -> str:
    if not text:
        return text

    def _repl(m: "re.Match") -> str:
        return " ".join(_DIGIT_WORDS[d] for d in m.group(0))

    out = re.sub(r"\d+", _repl, text)
    return re.sub(r"\s+", " ", out).strip()


_SPEAK_STRIP = re.compile(r"[|\\/\[\]{}<>~^_=+*#@]+")


def clean_for_speech(text: str) -> str:
    if not text:
        return text
    t = _SPEAK_STRIP.sub(" ", text)
    t = re.sub(r"\s*&\s*", " and ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _ensure_ffmpeg() -> None:
    global _FFMPEG_READY
    if _FFMPEG_READY:
        return
    try:
        import shutil

        from pydub import AudioSegment

        if shutil.which("ffmpeg") is None:
            try:
                import imageio_ffmpeg

                AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()
            except Exception:
                pass
    except Exception:
        pass
    _FFMPEG_READY = True


def _segment_to_float(seg) -> tuple[np.ndarray, int]:
    seg = seg.set_channels(1)
    sr = seg.frame_rate
    samples = np.array(seg.get_array_of_samples()).astype(np.float32)
    max_val = float(1 << (8 * seg.sample_width - 1))
    if max_val > 0:
        samples /= max_val
    return samples, sr


def _decode_mp3_bytes(data: bytes) -> tuple[np.ndarray, int]:
    try:
        import soundfile as sf

        d, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=False)
        if getattr(d, "ndim", 1) > 1:
            d = d.mean(axis=1)
        return d.astype(np.float32), sr
    except Exception:
        pass
    _ensure_ffmpeg()
    from pydub import AudioSegment

    seg = AudioSegment.from_file(io.BytesIO(data), format="mp3")
    return _segment_to_float(seg)


def _read_wav(path: str) -> tuple[np.ndarray, int]:
    import soundfile as sf

    d, sr = sf.read(path, dtype="float32", always_2d=False)
    if getattr(d, "ndim", 1) > 1:
        d = d.mean(axis=1)
    return d.astype(np.float32), sr


class TTSEngine:
    def __init__(self, cfg: dict):
        cfg = cfg or {}
        self.provider = cfg.get("provider", "edge")
        self.speak_digits = bool(cfg.get("speak_digits", True))
        self.cfg = cfg
        self._gclient = None
        self._gtts = None
        if self.provider not in ("edge", "pyttsx3", "elevenlabs", "google"):
            self.provider = "edge"
        if self.provider == "google":
            try:
                self._init_google()
            except Exception:
                self.provider = "edge"

    _FALLBACK_ORDER = ("edge", "pyttsx3")

    def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        text = clean_for_speech(text)
        if self.speak_digits:
            text = verbalize_numbers(text)
        order = [self.provider] + [p for p in self._FALLBACK_ORDER if p != self.provider]
        last_err: Exception | None = None
        for prov in order:
            try:
                out = self._synthesize_with(prov, text)
                if getattr(self, "_active_provider", None) != prov:
                    self._active_provider = prov
                    if prov != self.provider:
                        print(
                            f"[tts] '{self.provider}' unavailable - now speaking with "
                            f"fallback voice '{prov}'. Check your API key / internet "
                            f"if you expected '{self.provider}'."
                        )
                    else:
                        print(f"[tts] voice provider: '{prov}'")
                return out
            except Exception as e:
                last_err = e
                print(f"[tts] provider '{prov}' unavailable ({e}); trying fallback...")
        raise RuntimeError(f"All TTS providers failed. Last error: {last_err}")

    def _synthesize_with(self, provider: str, text: str) -> tuple[np.ndarray, int]:
        if provider == "edge":
            return self._edge(text)
        if provider == "pyttsx3":
            return self._pyttsx3(text)
        if provider == "elevenlabs":
            return self._elevenlabs(text)
        if provider == "google":
            return self._google(text)
        return self._edge(text)

    def _edge(self, text: str) -> tuple[np.ndarray, int]:
        import asyncio

        import edge_tts

        c = self.cfg.get("edge", {}) or {}
        voice = c.get("voice", "en-US-AriaNeural")
        rate = c.get("rate", "+0%")
        pitch = c.get("pitch", "+0Hz")

        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.close()
        try:
            err: dict = {}

            def _worker() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    async def _run():
                        comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
                        await comm.save(tmp.name)

                    loop.run_until_complete(_run())
                except Exception as e:  # noqa: BLE001
                    err["e"] = e
                finally:
                    try:
                        loop.close()
                    except Exception:
                        pass

            th = threading.Thread(target=_worker)
            th.start()
            th.join()
            if err.get("e") is not None:
                raise err["e"]
            with open(tmp.name, "rb") as f:
                data = f.read()
            if not data:
                raise RuntimeError("edge-tts returned no audio")
            return _decode_mp3_bytes(data)
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    def _pyttsx3(self, text: str) -> tuple[np.ndarray, int]:
        import pyttsx3

        c = self.cfg.get("pyttsx3", {}) or {}
        engine = pyttsx3.init()
        if c.get("rate"):
            try:
                engine.setProperty("rate", int(c["rate"]))
            except Exception:
                pass
        want = str(c.get("voice_contains", "zira")).lower()
        try:
            for v in engine.getProperty("voices"):
                if want in (v.name or "").lower() or want in (v.id or "").lower():
                    engine.setProperty("voice", v.id)
                    break
        except Exception:
            pass

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        try:
            engine.save_to_file(text, tmp.name)
            engine.runAndWait()
            return _read_wav(tmp.name)
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    def _elevenlabs(self, text: str) -> tuple[np.ndarray, int]:
        import requests

        c = self.cfg.get("elevenlabs", {}) or {}
        api_key = c.get("api_key") or os.getenv("ELEVENLABS_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "ElevenLabs API key missing (config tts.elevenlabs.api_key or env ELEVENLABS_API_KEY)"
            )
        voice_id = c.get("voice_id", "21m00Tcm4TlvDq8ikWAM")
        resp = requests.post(
            ELEVENLABS_TTS_URL + str(voice_id),
            headers={
                "xi-api-key": api_key,
                "accept": "audio/mpeg",
                "content-type": "application/json",
            },
            json={
                "text": text,
                "model_id": c.get("model_id", "eleven_turbo_v2"),
                "voice_settings": {
                    "stability": c.get("stability", 0.5),
                    "similarity_boost": c.get("similarity_boost", 0.75),
                },
            },
            timeout=30,
        )
        resp.raise_for_status()
        return _decode_mp3_bytes(resp.content)

    def _init_google(self) -> None:
        from google.cloud import texttospeech

        gcfg = self.cfg.get("google", {}) or {}
        creds = gcfg.get("credentials_json")
        if creds:
            os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", creds)
        self._gclient = texttospeech.TextToSpeechClient()
        self._gtts = texttospeech

    def _google(self, text: str) -> tuple[np.ndarray, int]:
        c = self.cfg.get("google", {}) or {}
        synth_input = self._gtts.SynthesisInput(text=text)
        voice = self._gtts.VoiceSelectionParams(
            language_code=c.get("language_code", "en-US"),
            name=c.get("voice_name", "en-US-Neural2-F"),
        )
        audio_config = self._gtts.AudioConfig(
            audio_encoding=self._gtts.AudioEncoding.MP3,
            speaking_rate=c.get("speaking_rate", 1.0),
            pitch=c.get("pitch", 0.0),
        )
        resp = self._gclient.synthesize_speech(
            input=synth_input, voice=voice, audio_config=audio_config
        )
        return _decode_mp3_bytes(resp.audio_content)
