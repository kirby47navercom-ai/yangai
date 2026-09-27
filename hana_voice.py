"""Bounded voice delivery and lightweight headphone spatialization; no voice assets."""
import math
import os
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np


# Semitones, synthesis speed, gain. Anger changes delivery, not listening volume.
TONES = {
    "neutral": (0.0, 1.0, 0.86), "bright": (1.2, 1.06, 0.86),
    "serious": (-1.0, 0.95, 0.84), "soft": (-0.6, 0.90, 0.62),
    "angry": (0.3, 1.07, 0.86), "surprised": (1.6, 1.08, 0.84),
    "afraid": (0.7, 1.03, 0.76),
}
POSITIONS = {
    "center": (0.0, 1.0), "left": (-0.65, 1.0), "right": (0.65, 1.0),
    "close": (0.0, 0.35), "close_left": (-0.8, 0.35),
    "close_right": (0.8, 0.35), "far": (0.0, 2.3),
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
    return 1.0 + (TONES[tone][1] - 1.0) * strength(config, "voice_expression_strength")


def spatial_audio(samples, rate, voice, config, previous=(0.0, 1.0)):
    """Return stereo PCM and the new pose, with smooth motion and no gain boosts."""
    voice = normalize_voice(voice, config)
    mono = np.asarray(samples, dtype=np.float32)
    if mono.ndim == 2:
        mono = mono.mean(axis=1)
    if mono.ndim != 1 or not len(mono) or rate <= 0 or not np.isfinite(mono).all():
        raise ValueError("Invalid generated audio")
    amount = strength(config, "voice_spatial_strength", 0.8) if config.get("voice_spatial_enabled", True) else 0.0
    pan, distance = POSITIONS[voice["position"]]
    target = (pan * amount, 1.0 + (distance - 1.0) * amount)
    # No automatic left/right alternation: only a changed delivery request moves the source.
    blend = np.minimum(np.arange(len(mono)) / max(1, int(rate * 0.8)), 1.0)
    blend = blend * blend * (3 - 2 * blend)
    start = previous if amount else (0.0, 1.0)
    pans = start[0] + (target[0] - start[0]) * blend
    distances = start[1] + (target[1] - start[1]) * blend
    level = 0.86 + (TONES[voice["tone"]][2] - 0.86) * strength(config, "voice_expression_strength")
    gain = level / np.maximum(1.0, distances)
    # ponytail: ITD/ILD and room cues approximate headphones, not full HRTF/elevation.
    # Upgrade to measured HRTFs if front/back or height localization is required.
    smooth = np.convolve(mono, np.ones(7) / 7, mode="full")[:len(mono)]
    dullness = np.clip((distances - 1.0) * 0.35, 0, 0.65)
    direct = mono * (1 - dullness) + smooth * dullness
    frames = np.arange(len(mono))
    channels = []
    for side in (-1, 1):
        far_ear = np.maximum(0.0, -side * pans)
        shadowed = direct * (1 - 0.22 * far_ear) + smooth * (0.22 * far_ear)
        delayed = np.interp(frames - far_ear * rate * 0.0006, frames, shadowed, left=0.0)
        ear_gain = np.sqrt((1 + side * pans) / 2)
        channel = delayed * ear_gain * gain
        # A distant voice gets a quiet room reflection; close speech stays dry.
        delay = int(rate * (0.019 if side < 0 else 0.026))
        if 0 < delay < len(mono):
            wet = amount * np.clip(distances - 0.5, 0, 1.5) * 0.075
            channel[delay:] += smooth[:-delay] * wet[delay:] * level * 0.5
        channels.append(channel)
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


def render_voice_wav(path, voice, config, previous=(0.0, 1.0), ffmpeg=None, cancel=None):
    """Modify only the temporary generated WAV. Reference recordings are never edited."""
    voice = normalize_voice(voice, config)
    if cancel is not None and cancel.is_set():
        return previous
    if not config.get("voice_expression_enabled", True) and not config.get("voice_spatial_enabled", True):
        return (0.0, 1.0)
    with wave.open(str(path), "rb") as wav:
        rate, width, channels = wav.getframerate(), wav.getsampwidth(), wav.getnchannels()
        if width != 2 or channels not in (1, 2):
            raise ValueError("Voice processing requires mono/stereo PCM16 WAV")
        raw = wav.readframes(wav.getnframes())
    pitch = TONES[voice["tone"]][0] * strength(config, "voice_expression_strength")
    if pitch and ffmpeg:
        ratio = 2 ** (pitch / 12)
        # Existing FFmpeg rubberband preserves duration and vocal formants.
        process = subprocess.Popen([
            str(ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(path),
            "-af", f"rubberband=pitch={ratio:.6f}:formant=preserved", "-ar", str(rate),
            "-ac", "1", "-f", "s16le", "pipe:1"], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            # communicate drains both pipes; bounded waits allow interruption/shutdown.
            for _ in range(100):
                if cancel is not None and cancel.is_set():
                    return previous
                try:
                    processed, error = process.communicate(timeout=0.1)
                    break
                except subprocess.TimeoutExpired:
                    continue
            else:
                raise TimeoutError("Voice pitch processing exceeded 10 seconds")
            if process.returncode or not processed:
                raise RuntimeError("Voice pitch processing failed: " + error.decode(errors="replace")[:200])
            raw, channels = processed, 1
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate()
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
