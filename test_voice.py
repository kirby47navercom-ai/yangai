"""Device-free voice tests; --live synthesizes local samples without playing them."""
import argparse
import io
import json
import shutil
import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import hana_chat as h
import hana_app as a
import hana_voice as v
from test_hana import reply


class VoiceTests(unittest.TestCase):
    def test_untrusted_controls_and_toggles_are_bounded(self):
        self.assertEqual(v.normalize_voice({'tone': [], 'position': '../file'}), {'tone': 'neutral', 'position': 'center'})
        self.assertEqual(v.normalize_voice({'tone': 'angry', 'position': 'left'},
            {'voice_expression_enabled': False, 'voice_spatial_enabled': False}), {'tone': 'neutral', 'position': 'center'})
        self.assertEqual(v.strength({'amount': float('nan')}, 'amount'), 1)
        self.assertEqual(v.strength({'amount': 50}, 'amount'), 1)

    def test_close_spatial_position_and_peak(self):
        rate = 24000
        samples = np.sin(np.arange(rate) * 2 * np.pi * 220 / rate).astype(np.float32) * 0.8
        config = {'voice_spatial_strength': 1}
        left, pose = v.spatial_audio(samples, rate, {'position': 'left'}, config, v.POSITIONS['left'])
        right, _ = v.spatial_audio(samples, rate, {'position': 'right'}, config, v.POSITIONS['right'])
        center, _ = v.spatial_audio(samples, rate, {}, config)
        legacy_far, _ = v.spatial_audio(samples, rate, {'position': 'far'}, config)
        rms = lambda data: np.sqrt(np.mean(data.astype(float) ** 2, axis=0))
        self.assertGreater(rms(left)[0], rms(left)[1] * 1.8)
        self.assertGreater(rms(right)[1], rms(right)[0] * 1.8)
        self.assertTrue(np.array_equal(legacy_far, center))
        self.assertNotIn('far', v.VOICE_SCHEMA['properties']['position']['enum'])
        self.assertLessEqual(np.max(np.abs(left.astype(int))), 30146)
        self.assertEqual(pose, v.POSITIONS['left'])
        self.assertEqual(left.shape, (rate, 2))
        self.assertTrue(np.all(left[0] == 0) and np.all(left[-1] == 0))
        muted, _ = v.spatial_audio(np.zeros(2), rate, {}, config)
        self.assertFalse(muted.any())

    def test_dry_positions_have_no_echo_or_room_tail(self):
        rate = 32000
        samples = np.zeros(rate)
        samples[rate // 2] = 0.8
        for position in v.POSITIONS:
            pcm, _ = v.spatial_audio(samples, rate, {'position': position}, {}, 0.6)
            nonzero = np.flatnonzero(np.any(pcm != 0, axis=1))
            self.assertTrue(len(nonzero))
            self.assertGreaterEqual(nonzero.min(), rate // 2)
            self.assertLess(nonzero.max(), rate // 2 + int(rate * 0.001))
        centered, _ = v.spatial_audio(samples, rate, {}, {})
        self.assertTrue(np.array_equal(centered[:, 0], centered[:, 1]))
        self.assertEqual(np.count_nonzero(centered[:, 0]), 1)

    def test_whisper_is_aperiodic_not_just_quieter_and_preserves_silence(self):
        rate = 24000
        samples = (np.sin(np.arange(rate) * 2 * np.pi * 200 / rate) * 0.4).astype(np.float32)
        samples[:rate // 10] = samples[-rate // 10:] = 0
        whisper = v.whisper_audio(samples, rate)
        self.assertEqual(len(whisper), len(samples))
        self.assertTrue(np.isfinite(whisper).all())
        self.assertFalse(whisper[:rate // 10].any())
        self.assertFalse(whisper[-rate // 20:].any())
        segment = whisper[rate // 4:3 * rate // 4]
        pitch_period = rate // 200
        periodicity = np.corrcoef(segment[:-pitch_period], segment[pitch_period:])[0, 1]
        self.assertLess(abs(periodicity), 0.5)
        self.assertTrue(np.array_equal(v.whisper_audio(samples, rate, 0), samples))

    def test_cancelled_render_does_not_read_or_change_file(self):
        cancel = threading.Event()
        cancel.set()
        self.assertEqual(v.render_voice_wav(Path('nonexistent.wav'), {}, {}, cancel=cancel), 0)

    def test_disabled_effects_bypass_and_failed_effects_preserve_speech(self):
        config = {'voice_expression_enabled': False, 'voice_spatial_enabled': False}
        self.assertEqual(v.render_voice_wav(Path('nonexistent.wav'), {}, config), 0)
        messages = []
        worker = SimpleNamespace(config={}, voice_pose=-1, _status=messages.append)
        with patch.object(h, 'render_voice_wav', side_effect=RuntimeError('test')):
            h.apply_voice_effects(worker, Path('speech.wav'), {}, threading.Event())
        self.assertEqual(worker.voice_pose, 0)
        self.assertIn('원래 음성', messages[0])

    def test_real_pitch_shift_preserves_duration(self):
        ffmpeg = h.configured_ffmpeg(h.read_config())
        if not ffmpeg:
            self.skipTest('Local FFmpeg is not installed')
        rate = 24000
        signal = (np.sin(np.arange(rate * 2) * 2 * np.pi * 220 / rate) * 12000).astype('<i2')
        peaks = []
        with tempfile.TemporaryDirectory() as directory:
            for tone in ('serious', 'neutral', 'bright'):
                path = Path(directory) / (tone + '.wav')
                with wave.open(str(path), 'wb') as wav:
                    wav.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
                    wav.writeframes(signal.tobytes())
                v.render_voice_wav(path, {'tone': tone}, {}, ffmpeg=ffmpeg)
                with wave.open(str(path), 'rb') as wav:
                    self.assertAlmostEqual(wav.getnframes() / rate, 2, delta=0.05)
                    pcm = np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2').reshape(-1, 2)[:, 0]
                middle = pcm[rate // 2:rate * 3 // 2].astype(float)
                spectrum = np.abs(np.fft.rfft(middle * np.hanning(len(middle))))
                peaks.append(np.fft.rfftfreq(len(middle), 1 / rate)[np.argmax(spectrum)])
        self.assertLess(peaks[0], 212)
        self.assertAlmostEqual(peaks[1], 220, delta=1)
        self.assertGreater(peaks[2], 230)

    def test_answer_and_delivery_travel_together_as_one_utterance(self):
        voice = {'tone': 'soft', 'position': 'close_left'}
        state = {}
        answer = '조금만 가까이 갈게. 이번에는 작게 이야기할게.'
        with patch.object(h, 'stream_chat', return_value=[reply(answer, voice=voice)]):
            h.generate_reply({'semantic_repeat_check': False}, [], on_state=state.update)
        self.assertEqual(state['voice'], voice)
        app = a.HanaApp.__new__(a.HanaApp)
        app.config = {'model': 'test'}
        app.memory, app.recent_auto_answers = {}, []
        app.stop_event, app.last_user_activity_at = threading.Event(), 0
        app.root = SimpleNamespace(after=lambda _, callback: callback())
        app._line = lambda *args: None
        sent = []
        app.tts = SimpleNamespace(submit=lambda *args: sent.append(args))
        def generate(*args, **kwargs):
            kwargs['on_state'](state)
            return answer
        with patch.object(a, 'generate_reply', generate):
            self.assertEqual(app._stream_and_speak([]), answer)
        self.assertEqual(sent, [(answer, voice)])

    def test_synthesis_uses_emotional_reference_and_short_fragment_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('python.exe', 'ref.wav', 'tts.yaml', '【生气】화내는 참조.wav'):
                (root / name).touch()
            config = {'gpt_sovits_root': str(root), 'gpt_sovits_python': str(root / 'python.exe'),
                      'gpt_sovits_config': str(root / 'tts.yaml'), 'gpt_sovits_ref_audio': str(root / 'ref.wav'),
                      'gpt_sovits_ref_text': '보통 목소리'}
            worker = h.GPTSoVITSTTSWorker(config, root)
            try:
                with patch.object(worker, '_ensure_server'), patch.object(h, 'urlopen', return_value=io.BytesIO(b'fake')) as request, \
                     patch.object(h, 'render_voice_wav', return_value=0), patch.object(h, 'play_wav_file'):
                    worker._speak('첫 문장이야. 다음 문장도 함께야.', threading.Event(), {'tone': 'angry'})
                payload = json.loads(request.call_args.args[0].data)
                self.assertEqual(Path(payload['ref_audio_path']).name, '【生气】화내는 참조.wav')
                self.assertEqual(payload['prompt_text'], '화내는 참조')
                self.assertEqual(payload['fragment_interval'], 0.12)
                self.assertGreater(payload['speed_factor'], 1)
                self.assertIn('다음 문장', payload['text'])
                self.assertEqual(request.call_count, 1)
            finally:
                worker.close()


def load_runtime(built=False):
    project = Path(__file__).resolve().parent
    if built:
        from PyInstaller.archive.readers import CArchiveReader
        archive = CArchiveReader(str(project / 'dist/Hana/Hana.exe'))
        pyz = archive.open_embedded_archive(next(name for name in archive.toc if name.endswith('.pyz')))
        exec(pyz.extract('hana_voice'), v.__dict__)
        exec(pyz.extract('hana_chat'), h.__dict__)
        h.ROOT = project / 'dist/Hana'
        h.CONFIG_FILE = h.ROOT / 'config.json'
        h.PROMPT_FILE = h.ROOT / 'hana_prompt.txt'
    return project


def live(built=False):
    project = load_runtime(built)
    config = h.read_config()
    output = project / 'data/diagnostics' / ('voice-close-built' if built else 'voice-close-source')
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(h.resolve_tts_path(config['gpt_sovits_config']), output / 'tts-test.yaml')
    config.update(gpt_sovits_config=str(output / 'tts-test.yaml'), gpt_sovits_port=19881)
    worker = h.GPTSoVITSTTSWorker(config, output)
    rows = []
    current = {}
    def inspect(path, cancel):
        with wave.open(str(path)) as wav:
            rate, frames, channels = wav.getframerate(), wav.getnframes(), wav.getnchannels()
            pcm = np.frombuffer(wav.readframes(frames), dtype='<i2').reshape(-1, channels).astype(float)
        assert channels == 2 and frames > rate // 2
        rms = np.sqrt(np.mean(pcm ** 2, axis=0))
        assert rms.min() > 1 and np.max(np.abs(pcm)) <= 30147
        block = int(rate * 0.02)
        mono = pcm.mean(axis=1)
        levels = np.sqrt(np.mean(mono[:len(mono) // block * block].reshape(-1, block) ** 2, axis=1))
        active = np.flatnonzero(levels > 150)
        longest = run = 0
        for quiet in levels[active[0]:active[-1] + 1] < 150:
            run = run + 1 if quiet else 0
            longest = max(run, longest)
        row = {**current, 'duration_seconds': round(frames / rate, 3),
               'rms_left': round(rms[0], 2), 'rms_right': round(rms[1], 2),
               'peak': float(np.max(np.abs(pcm))), 'max_internal_quiet_seconds': round(longest * 0.02, 2),
               'playback_tested': False}
        shutil.copy2(path, output / (current['tone'] + '.wav'))
        rows.append(row)
    try:
        assert not worker._server_ready(), 'Test port already in use'
        worker._ensure_server()
        with patch.object(h, 'play_wav_file', inspect):
            for tone, position in [('neutral', 'center'), ('bright', 'right'), ('serious', 'left'),
                                   ('soft', 'close_left'), ('angry', 'center'), ('whisper', 'close_right')]:
                current.update(tone=tone, position=position)
                start = time.monotonic()
                worker._speak('아까 그 장면은 조금 아쉬웠어. 그래도 이번에는 끝까지 같이 지켜볼게.',
                              threading.Event(), current)
                rows[-1]['synthesis_and_effect_seconds'] = round(time.monotonic() - start, 3)
                h.save_json(output / 'results.json', rows)
                print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    finally:
        worker.close()
        if worker.server_process:
            worker.server_process.wait(timeout=15)
    from faster_whisper.audio import decode_audio
    recognizer = h.SpeechRecognizer(config)
    for row in rows:
        # These are known speech files. Normal-voice VAD discards unvoiced whispers;
        # validate intelligibility without changing the production microphone VAD.
        segments, _ = recognizer._load().transcribe(
            decode_audio(str(output / (row['tone'] + '.wav')), sampling_rate=16000),
            language='ko', beam_size=1, vad_filter=False)
        row['transcript'] = ' '.join(segment.text.strip() for segment in segments)
        row['transcription_vad'] = False
        h.save_json(output / 'results.json', rows)
        print(json.dumps({'tone': row['tone'], 'transcript': row['transcript']}, ensure_ascii=False), flush=True)
        assert '아쉬' in row['transcript'] and '이번' in row['transcript'], 'One of the two spoken clauses is missing'


def live_model(built=False):
    project = load_runtime(built)
    config = {**h.read_config(), 'ollama_url': 'http://127.0.0.1:11435'}
    owned = h.ensure_ollama(config)
    prompt = h.PROMPT_FILE.read_text(encoding='utf-8')
    rows = []
    try:
        cases = h.make_messages(prompt, {}, [{'role': 'user', 'content': '가까이 와서 작은 목소리로 얘기해 줘.'}], 16, '')
        for candidate, expected in [
            ('(가까이 다가가 귓속말로) 사실은 나도 조금 긴장했어.', 'non_speech'),
            ('조금 가까이 갈게. 사실은 나도 조금 긴장했어.', 'none')]:
            result = h.review_reply(config, cases, candidate, False, 60)
            assert result['issue'] == expected, result
        for tone, text in [
            ('bright', '드디어 그 보스 잡았어! 같이 신나게 축하해 줘!'),
            ('serious', '오늘 좀 힘들었어. 진지하고 낮고 차분한 목소리로 이야기해 줘.'),
            ('whisper', '하나야 왼쪽 귀 가까이에서 오늘도 수고했어, 라고 속삭여 줘.')]:
            state = {}
            messages = h.make_messages(prompt, {}, [{'role': 'user', 'content': text}], 16, '')
            started = time.monotonic()
            attempts = []
            def record_attempt(event):
                attempts.append(event)
                h.save_json(project / 'data/diagnostics/voice-model-attempts.json', {'user': text, 'attempts': attempts})
            answer = h.generate_reply(config, messages, on_state=state.update, on_attempt=record_attempt)
            row = {'user': text, 'answer': answer, 'voice': state.get('voice'),
                   'seconds': round(time.monotonic() - started, 2)}
            rows.append(row)
            h.save_json(project / 'data/diagnostics/voice-model.json', rows)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            assert state['voice']['tone'] == tone, row
            if tone == 'whisper':
                assert state['voice']['position'] == 'close_left', row
        # No user utterance requesting a voice mode this turn: the character may
        # choose a delivery for its own continuation, without keyword replacement.
        history = [
            {'role': 'user', 'content': '다들 잠든 시간이네. 오늘은 우리 둘만의 조용한 비밀 방송이야.'},
            {'role': 'assistant', 'content': '괜히 나까지 살금살금 말하게 되네. 이런 시간은 좀 특별해.', 'generation_version': 2}]
        messages = h.make_messages(prompt, {}, history, 16, '')
        control = h.broadcast_instruction('idle')
        state = {}
        answer = h.generate_reply(config, messages + [{'role': 'user', 'content': control, '_event': True}],
                                  control_text=control, on_state=state.update)
        assert state['voice']['position'] in v.POSITIONS
        row = {'automatic': True, 'answer': answer, 'voice': state['voice']}
        rows.append(row)
        h.save_json(project / 'data/diagnostics/voice-model.json', rows)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    finally:
        h.stop_ollama(owned)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--built', action='store_true')
    parser.add_argument('--live-model', action='store_true')
    args = parser.parse_args()
    if args.live:
        live(args.built)
    elif args.live_model:
        live_model(args.built)
    else:
        unittest.main(argv=[__file__])
