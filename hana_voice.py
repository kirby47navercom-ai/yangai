"""Bounded voice delivery and lightweight headphone spatialization; no voice assets."""
import math
import tempfile
import wave
from pathlib import Path

import numpy as np


# Synthesis speed, gain. Keep the generated voice's pitch and phase untouched.
TONES = {
    "neutral": (1.0, 0.86), "bright": (1.06, 0.86),
    "serious": (0.95, 0.84), "soft": (0.90, 0.62),
    "angry": (1.07, 0.86), "surprised": (1.08, 0.84),
    "afraid": (1.03, 0.76),
}
# All positions stay at the close microphone. Old 'far' values normalize to center.
POSITIONS = {
    "center": 0.0, "left": -0.65, "right": 0.65,
    "close": 0.0, "close_left": -0.8, "close_right": 0.8,
}
VOICE_SCHEMA = {"type": "object", "properties": {
    "tone": {"type": "string", "enum": list(TONES)},
    "position": {"type": "string", "enum": list(POSITIONS)},
}, "required": ["tone", "position"], "additionalProperties": False}


def normalize_voice(value=None, config=None):
    value = value if isinstance(value, dict) else {}
    config = config or {}
    tone, position = value.get("tone"), value.get("position")
    return {"tone": tone if isinstance(tone, str) and tone in TONES and config.get("voice_expression_enabled", True) else "neutral",
            "position": position if isinstance(position, str) and position in POSITIONS and config.get("voice_spatial_enabled", True) else "center"}


def strength(config, key, default=1.0):
    try:
        number = float(config.get(key, default))
        return max(0.0, min(1.0, number)) if math.isfinite(number) else default
    except (ValueError, TypeError):
        return default


def voice_speed(voice, config):
    tone = normalize_voice(voice, config)["tone"]
    return 1.0 + (TONES[tone][0] - 1.0) * strength(config, "voice_expression_strength")


def spatial_audio(samples, rate, voice, config, previous=0.0):
    """Return dry close-mic stereo PCM and pan, never a room/echo/distance effect."""
    voice = normalize_voice(voice, config)
    mono = np.asarray(samples, dtype=np.float32)
    if mono.ndim == 2:
        mono = mono.mean(axis=1)
    if mono.ndim != 1 or not len(mono) or rate <= 0 or not np.isfinite(mono).all():
        raise ValueError("Invalid generated audio")
    amount = strength(config, "voice_spatial_strength", 0.8) if config.get("voice_spatial_enabled", True) else 0.0
    target = POSITIONS[voice["position"]] * amount
    # No automatic left/right alternation: only a changed delivery request moves the source.
    blend = np.minimum(np.arange(len(mono)) / max(1, int(rate * 0.8)), 1.0)
    blend = blend * blend * (3 - 2 * blend)
    start = previous if amount else 0.0
    pans = start + (target - start) * blend
    level = 0.86 + (TONES[voice["tone"]][1] - 0.86) * strength(config, "voice_expression_strength")
    # Dry amplitude panning only: no delayed samples, pitch shift or room response.
    channels = []
    for side in (-1, 1):
        ear_gain = np.sqrt((1 + side * pans) / 2)
        channels.append(mono * ear_gain * level)
    stereo = np.column_stack(channels)
    fade = min(int(rate * 0.005), len(mono) // 2)
    if fade:
        stereo[:fade] *= np.linspace(0, 1, fade)[:, None]
        stereo[-fade:] *= np.linspace(1, 0, fade)[:, None]
    # Lower only when needed; never normalize a soft delivery back to full volume.
    peak = np.max(np.abs(stereo))
    if peak > 0.92:
        stereo *= 0.92 / peak
    return np.round(stereo * 32767).astype("<i2"), target


def render_voice_wav(path, voice, config, previous=0.0, cancel=None):
    """Modify only the temporary generated WAV. Reference recordings are never edited."""
    voice = normalize_voice(voice, config)
    if cancel is not None and cancel.is_set():
        return previous
    if not config.get("voice_expression_enabled", True) and not config.get("voice_spatial_enabled", True):
        return 0.0
    with wave.open(str(path), "rb") as wav:
        rate, width, channels = wav.getframerate(), wav.getsampwidth(), wav.getnchannels()
        if width != 2 or channels not in (1, 2):
            raise ValueError("Voice processing requires mono/stereo PCM16 WAV")
        raw = wav.readframes(wav.getnframes())
    if cancel is not None and cancel.is_set():
        return previous
    samples = np.frombuffer(raw, dtype="<i2").reshape(-1, channels).astype(np.float32) / 32768
    pcm, pose = spatial_audio(samples, rate, voice, config, previous)
    # Write beside the temporary WAV so a failed conversion cannot damage the original.
    with tempfile.NamedTemporaryFile(suffix=".wav", dir=Path(path).parent, delete=False) as handle:
        output = Path(handle.name)
    try:
        with wave.open(str(output), "wb") as wav:
            wav.setparams((2, 2, rate, 0, "NONE", "not compressed"))
            wav.writeframes(pcm.tobytes())
        output.replace(path)
    finally:
        output.unlink(missing_ok=True)
    return pose
