"""Bounded voice delivery and lightweight headphone spatialization; no voice assets."""
import math
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
    "afraid": (0.7, 1.03, 0.76), "whisper": (0.0, 0.92, 0.64),
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
    return 1.0 + (TONES[tone][1] - 1.0) * strength(config, "voice_expression_strength")


def whisper_audio(mono, rate, amount=0.9):
    """Dry DSP whisper: aperiodic excitation shaped by the speech spectral envelope."""
    # ponytail: spectral conversion, not an actor's learned whisper performance. A whisper
    # reference/model is needed for natural breath, mouth sounds and speaker fidelity.
    if amount <= 0:
        return mono
    size = 2 ** int(np.ceil(np.log2(rate * 0.032)))
    hop = size // 4
    window = np.hanning(size)
    source = np.pad(mono, (size, size))
    output = np.zeros_like(source, dtype=np.float64)
    weights = np.zeros_like(output)
    bins = max(1, int(200 * size / rate))
    kernel = np.convolve(np.ones(bins), np.ones(bins))
    kernel /= kernel.sum()
    frequencies = np.fft.rfftfreq(size, 1 / rate)
    tilt = np.clip(frequencies / 500, 0.15, 3) ** 0.5
    random = np.random.default_rng(0)
    for start in range(0, len(source) - size + 1, hop):
        frame = source[start:start + size] * window
        energy = np.mean(frame ** 2)
        if energy > 1e-10:
            spectrum = np.fft.rfft(frame)
            logs = np.log(np.maximum(np.abs(spectrum), 1e-8))
            pad = len(kernel) // 2
            envelope = np.exp(np.convolve(np.pad(logs, (pad, pad), mode='edge'), kernel, mode='valid'))
            noise = np.fft.rfft(random.standard_normal(size) * window)
            shaped = np.fft.irfft(envelope * tilt * noise / np.maximum(np.abs(noise), 1e-8), size)
            shaped *= np.sqrt(energy / max(np.mean(shaped ** 2), 1e-12))
            output[start:start + size] += shaped * window
        weights[start:start + size] += window ** 2
    output = (output / np.maximum(weights, 1e-8))[size:size + len(mono)]
    # Do not introduce breath/hiss into the original silence or extend the waveform.
    gate_size = max(1, int(rate * 0.003))
    gate = np.convolve(np.abs(mono), np.ones(gate_size) / gate_size, mode='full')[:len(mono)]
    output *= np.clip(gate / 0.003, 0, 1)
    return mono * (1 - amount) + output * amount


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
    level = 0.86 + (TONES[voice["tone"]][2] - 0.86) * strength(config, "voice_expression_strength")
    if voice["tone"] == "whisper":
        mono = whisper_audio(mono, rate, strength(config, "voice_whisper_strength", 0.9))
    # ponytail: direct ITD/ILD approximates close binaural microphones, not full HRTF.
    # A sub-millisecond inter-ear offset is not a second copy mixed into either ear.
    frames = np.arange(len(mono))
    channels = []
    for side in (-1, 1):
        far_ear = np.maximum(0.0, -side * pans)
        delayed = np.interp(frames - far_ear * rate * 0.00025, frames, mono, left=0.0)
        ear_gain = np.sqrt((1 + side * pans) / 2)
        channels.append(delayed * ear_gain * level)
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


def render_voice_wav(path, voice, config, previous=0.0, ffmpeg=None, cancel=None):
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
