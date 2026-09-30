"""Device-free checks for mouse/blink/expression and the actual WAV playback callback."""
import math
import random
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import numpy as np
import hana_chat as chat
import hana_app as app_module
from hana_avatar import AvatarState, EXPRESSIONS


class AvatarTests(unittest.TestCase):
    def test_live_surface_in_the_actual_gui_without_starting_devices_or_models(self):
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        app = None
        config = {**chat.read_config(), 'mic_enabled': False, 'screen_enabled': False,
                  'tts_enabled': False, 'idle_talk_enabled': False}
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            try:
                with patch.multiple(chat, DATA_DIR=data, MEMORY_FILE=data / 'memory.json', SESSION_DIR=data / 'sessions'), \
                     patch.multiple(app_module, DATA_DIR=data, MEMORY_FILE=data / 'memory.json'), \
                     patch.object(app_module, 'read_config', return_value=config), \
                     patch.object(app_module, 'ensure_ollama', return_value=None):
                    app = app_module.HanaApp(root)
                    root.geometry('1050x720-5000-5000')
                    root.deiconify()
                    root.update()
                    self.assertIsNotNone(app.avatar_widget)
                    self.assertIsNotNone(app.avatar_widget.model)
                    self.assertFalse(app.avatar_widget.failed)
                    def accepted(*args, **kwargs):
                        kwargs['on_state']({'expression': 'cry'})
                        return '슬픈 이야기라 조금 울컥했어.'
                    with patch.object(app_module, 'generate_reply', accepted):
                        app._stream_and_speak([])
                    self.assertEqual(app.avatar_state.expression, 'cry')
                    root.update()
                    app.close()
                    app = None
            finally:
                if app:
                    app.close()
                try:
                    root.destroy()
                except tk.TclError:
                    pass
    def test_mouse_blink_expressions_and_stale_audio(self):
        clock = [0.0]
        state = AvatarState(clock=lambda: clock[0], rng=random.Random(3))
        pose = state.pose(20, -20)
        self.assertEqual(pose['ParamAngleX'], 0)
        self.assertEqual(pose['ParamAngleY'], 0)
        for _ in range(20):
            clock[0] += .05
            pose = state.pose(20, -20)
        self.assertGreater(pose['ParamAngleX'], 19)
        self.assertGreater(pose['ParamAngleY'], 14)
        self.assertEqual(pose['ParamMouthOpenY'], 0)
        clock[0] = state.blink_at + .095
        self.assertLess(state.pose()['ParamEyeLOpen'], .05)
        clock[0] += .3
        self.assertGreater(state.pose()['ParamEyeLOpen'], .9)
        state.audio_level(.2)
        clock[0] += .05
        self.assertGreater(state.pose()['ParamMouthOpenY'], .7)
        clock[0] += .3
        self.assertLess(state.pose()['ParamMouthOpenY'], .05)
        for name in EXPRESSIONS:
            state.set_expression(name)
            for _ in range(10):
                clock[0] += .05
                pose = state.pose(follow=False)
            self.assertTrue(all(math.isfinite(v) for v in pose.values()))
            if name == 'cry':
                self.assertGreater(pose['ParamTears'], .95)
            if name == 'angry':
                self.assertGreater(pose['ParamBrowForm'], .75)
        state.set_expression([])
        self.assertEqual(state.expression, 'neutral')
        state.audio_level(float('nan'))
        self.assertEqual(state.level, 0)

    def test_eye_led_head_motion_and_back_hair_settle_without_idle_sliding(self):
        clock = [0.0]
        state = AvatarState(clock=lambda: clock[0], rng=random.Random(4))
        state.pose()
        for _ in range(3):
            clock[0] += 1/30
            pose = state.pose(1, 0)
        self.assertGreater(pose['ParamEyeBallX']/.65, pose['ParamAngleX']/20)
        self.assertLess(abs(pose['ParamAngleZ']), 5)
        self.assertGreater(abs(pose['ParamHairSwing']), .01)
        for _ in range(240):
            clock[0] += 1/30
            pose = state.pose(1, 0)
            self.assertTrue(all(math.isfinite(v) for v in pose.values()))
            self.assertLessEqual(abs(pose['ParamHairSwing']), 1)
        self.assertLess(abs(pose['ParamHairSwing']), .001)

    def test_live_body_and_connected_legs_are_driven_without_losing_head_range(self):
        clock = [0.0]
        state = AvatarState(clock=lambda: clock[0], rng=random.Random(4))
        self.assertEqual(state.pose(1, -1)['ParamBodyAngleX'], 0)
        for _ in range(90):
            clock[0] += 1/30
            pose = state.pose(1, -1)
        self.assertGreater(pose['ParamAngleX'], 19.9)
        self.assertGreater(pose['ParamAngleY'], 14.9)
        self.assertGreater(pose['ParamBodyAngleX'], 6)
        self.assertGreater(pose['ParamLegVL'], .1)
        self.assertAlmostEqual(pose['ParamLegVL'], pose['ParamLegVR'])
        self.assertAlmostEqual(pose['ParamKneeVL'], -pose['ParamKneeVR'])

    def test_playback_levels_follow_pcm_not_synthesis_or_cancelled_audio(self):
        import winsound
        clock, rows = [0.0], []
        pcm = np.concatenate([np.zeros(1200), np.full(1200, .25), np.zeros(1200)])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.wav'
            with wave.open(str(path), 'wb') as wav:
                wav.setparams((2, 2, 24000, 0, 'NONE', 'not compressed'))
                wav.writeframes((np.repeat(pcm, 2) * 32767).astype('<i2').tobytes())
            before = path.read_bytes()
            with patch.object(winsound, 'PlaySound') as output, patch.object(chat.time, 'monotonic', lambda: clock[0]), \
                 patch.object(chat.time, 'sleep', lambda dt: clock.__setitem__(0, clock[0] + dt)):
                chat.play_wav_file(path, on_level=lambda level: rows.append((clock[0], level)))
                self.assertEqual(output.call_count, 2)
                self.assertEqual(rows[0][1], 0)
                self.assertTrue(any(abs(level - .25) < .001 for _, level in rows))
                self.assertEqual(rows[-1][1], 0)
                cancel = threading.Event()
                cancel.set()
                output.reset_mock()
                chat.play_wav_file(path, cancel, lambda level: rows.append((clock[0], level)))
                output.assert_not_called()
                self.assertEqual(rows[-1][1], 0)
            self.assertEqual(path.read_bytes(), before)

    def test_accepted_model_expression_is_not_a_keyword_match(self):
        from test_hana import reply
        state = {}
        with patch.object(chat, 'stream_chat', return_value=[reply('슬픈 영화지만 나는 결말이 마음에 들었어.', expression='smile')]):
            chat.generate_reply({'semantic_repeat_check': False}, [], on_state=state.update)
        self.assertEqual(state['expression'], 'smile')
        with patch.object(chat, 'stream_chat', return_value=[reply('고마워.', expression=['cry'])]):
            chat.generate_reply({'semantic_repeat_check': False}, [], on_state=state.update)
        self.assertEqual(state['expression'], 'neutral')


if __name__ == '__main__':
    unittest.main()
