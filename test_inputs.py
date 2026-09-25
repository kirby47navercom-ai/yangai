"""Input path regressions. Devices/models are mocked unless --live is explicitly requested."""
import argparse
import io
import json
import os
import queue
import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import hana_app as a
import hana_chat as h
from test_hana import reply


class InputTests(unittest.TestCase):
    def test_user_interrupt_closes_stream_without_committing_draft(self):
        state = {}
        closed = []
        def stream(*args, **kwargs):
            try:
                yield '{"speech":"unfinished'
            finally:
                closed.append(True)
        with patch.object(h, "stream_chat", stream):
            with patch.object(h, "review_reply") as review:
                cancel = iter([False, True])
                answer = h.generate_reply({"semantic_repeat_check": False}, [], on_state=state.update,
                                           should_cancel=lambda: next(cancel))
        self.assertEqual(answer, "")
        self.assertEqual(state, {})
        self.assertEqual(closed, [True])
        review.assert_not_called()

    def test_screen_event_is_retained_while_tts_and_generation_are_busy(self):
        app = a.HanaApp.__new__(a.HanaApp)
        app.root = SimpleNamespace(after=lambda _, callback: callback())
        app.status = SimpleNamespace(configure=lambda **kwargs: None)
        app.config = {"screen_proactive": True}
        app.chat_busy = threading.Event()
        app.chat_busy.set()
        app.chat_queue = queue.Queue()
        app.pending_screen = False
        app.screen_event_id = 0
        app._tts_busy = lambda: True
        app._runtime_log = lambda text: None
        app._on_screen_observation("새 화면")
        self.assertTrue(app.pending_screen)
        self.assertEqual(app.screen_event_id, 1)
        self.assertTrue(app.chat_queue.empty())

    def test_initial_idle_waits_for_screen_and_pending_screen_wins(self):
        app = a.HanaApp.__new__(a.HanaApp)
        app.last_user_activity_at = 0
        app.last_idle_requested_at = 1
        app.pending_screen = True
        app.watcher = SimpleNamespace(running=lambda: True, last_error="")
        app.screen_context = h.ScreenContext()
        calls = []
        app._answer_broadcast = calls.append
        app._answer_idle()
        self.assertEqual(calls, [])
        app.screen_context.update("앱/창: 강의; 확실히 읽힌 글자: TCP; 장면: 문서")
        app._answer_idle()
        self.assertEqual(calls, ["screen"])

    def test_stt_callback_uses_user_path_and_invalidates_idle(self):
        app = a.HanaApp.__new__(a.HanaApp)
        app.root = SimpleNamespace(after=lambda _, callback: callback())
        app.stop_event = threading.Event()
        app.chat_queue = queue.Queue()
        app.tts = SimpleNamespace(interrupt=lambda: None)
        app._runtime_log = lambda text: None
        lines = []
        app._line = lambda who, text, tag: lines.append((who, text))
        app.last_user_activity_at = 0
        app._on_mic_text("나는 네트워크 공부 중이야")
        self.assertEqual(app.chat_queue.get_nowait(), ("user", "나는 네트워크 공부 중이야"))
        self.assertEqual(lines[0][0], "너 · STT")
        self.assertGreater(app.last_user_activity_at, 0)

    def test_continuous_microphone_records_during_tts_and_transcribes(self):
        # Fake audio blocks through the SAME stream callback and segmentation used by the GUI.
        import sounddevice as sd
        received, statuses = [], []
        ready = threading.Event()
        tts = SimpleNamespace(speaking=threading.Event())
        tts.speaking.set()
        recognizer = SimpleNamespace(_load=lambda: None,
            transcribe_audio=lambda samples: "상상 말고 내 말에 대답해")
        mic = a.MicLoop(recognizer, tts, lambda text: (received.append(text), ready.set()),
                        statuses.append, {"mic_chunk_seconds": .1, "mic_silence_seconds": .2,
                                          "mic_listen_during_tts": True}, on_activity=lambda: statuses.append("active"))
        class Stream:
            def __init__(self, **kwargs):
                self.callback = kwargs["callback"]
            def __enter__(self):
                for energy in [0, .1, .1, 0, 0]:
                    self.callback(np.full((1600, 1), energy, dtype=np.float32), 1600, None, None)
                return self
            def __exit__(self, *args):
                pass
        with patch.object(sd, "InputStream", Stream):
            mic.start()
            self.assertTrue(ready.wait(2))
            mic.stop()
        self.assertEqual(received, ["상상 말고 내 말에 대답해"])
        self.assertIn("active", statuses)
        self.assertFalse(mic.running())

    def test_tts_interruption_cancels_current_and_queued_audio_not_future_reply(self):
        for cls in (h.TTSWorker, h.GPTSoVITSTTSWorker):
            worker = cls.__new__(cls)
            worker.queue_lock = threading.Lock()
            worker.playback_cancel = threading.Event()
            old_cancel = worker.playback_cancel
            worker.items = queue.Queue()
            worker.items.put(("old", old_cancel))
            worker.interrupt()
            self.assertTrue(old_cancel.is_set())
            self.assertTrue(worker.items.empty())
            self.assertFalse(worker.playback_cancel.is_set())

    def test_stale_capture_not_made_fresh_when_slow_analysis_finishes(self):
        ctx = h.ScreenContext()
        ctx.update("오래된 관찰", captured_at=time.monotonic() - 60)
        self.assertEqual(ctx.prompt(), "")
        watcher = h.ScreenWatcher({}, ctx)
        watcher.latest_image = "old image"
        watcher.image_captured_at = time.monotonic() - 60
        self.assertEqual(watcher.latest_image_data(), "")

    def test_fiction_loop_is_regenerated_with_grounded_feedback(self):
        messages = h.make_messages("하나", {}, [], 16, "최신 관찰: TCP 강의")
        messages[0]["_screen_pending"] = True
        plan = {"basis": "screen", "action": "screen", "anchor": "TCP", "new_point": "공부에 반응"}
        attempts = []
        with patch.object(h, "plan_continuation", return_value=plan):
            with patch.object(h, "review_reply", side_effect=[{"issue": "fiction_loop"}, {"issue": "none"}]):
                with patch.object(h, "stream_chat", side_effect=[[reply("왕관에 또 불꽃이 터지면 어떨까?")], [reply("아, 지금은 TCP 강의를 보고 있네.")]]):
                    answer = h.generate_reply({}, messages, ["왕관 얘기", "불꽃 얘기"], "자동", on_attempt=attempts.append)
        self.assertIn("TCP", answer)
        self.assertEqual([x["reason"] for x in attempts], ["fiction_loop", "accepted"])

    def test_action_options_follow_input_not_a_fixed_topic_timer(self):
        config = {"model": "fake", "ollama_url": "http://127.0.0.1:11434", "keep_alive": "1m", "num_ctx": 8192}
        plan = {"basis": "reflection", "user_constraint": "", "anchor": "직전 생각", "action": "conclude", "new_point": "그 생각 마무리"}
        messages = h.make_messages("하나", {"broadcast_state": {"action": "hypothetical", "basis": "screen"}}, [], 16, "현재 강의")
        with patch.object(h, "request_json", return_value={"message": {"content": json.dumps(plan)}}) as call:
            h.plan_continuation(config, messages, 30)
        actions = call.call_args.args[1]["format"]["properties"]["action"]["enum"]
        self.assertNotIn("user", call.call_args.args[1]["format"]["properties"]["basis"]["enum"])
        self.assertNotIn("hypothetical", actions)
        self.assertNotIn("screen", actions)
        self.assertIn("develop", actions)
        messages[0]["_screen_pending"] = True
        with patch.object(h, "request_json", return_value={"message": {"content": json.dumps(plan)}}) as call:
            h.plan_continuation(config, messages, 30)
        self.assertIn("screen", call.call_args.args[1]["format"]["properties"]["action"]["enum"])


def live():
    """Known Korean waveform -> real STT -> GUI user handler -> real local decision/speech.

    No live mic, desktop screenshot, audible TTS, or personal memory files.
    """
    from PIL import Image, ImageDraw, ImageFont
    import base64
    config = h.read_config()
    os.environ["ESPEAK_DATA_PATH"] = os.path.expandvars(config["piper_espeak_data"])
    from piper import PiperVoice
    with tempfile.TemporaryDirectory() as directory:
        data = Path(directory)
        # Generate a known spoken input in memory/on a temporary file; no recording of the user.
        voice = PiperVoice.load(str(h.ROOT / config["piper_model"]))
        sample = data / "speech.wav"
        original = "하나야, 상상 말고 내 말에 대답해. 나는 지금 네트워크 공부 중이야."
        with wave.open(str(sample), "wb") as output:
            voice.synthesize_wav(original, output)
        from faster_whisper.audio import decode_audio
        recognizer = h.SpeechRecognizer(config)
        started = time.monotonic()
        transcript = recognizer.transcribe_audio(decode_audio(str(sample), sampling_rate=16000))
        print(json.dumps({"stage": "real_stt", "source": original, "transcript": transcript,
                          "seconds": round(time.monotonic() - started, 2)}, ensure_ascii=False), flush=True)
        assert "네트워크" in transcript and "공부" in transcript, "Real STT failed key content"

        app = a.HanaApp.__new__(a.HanaApp)
        app.config = {**config, "auto_memory": False}
        app.root = SimpleNamespace(after=lambda _, callback: callback())
        app.stop_event = threading.Event()
        app.chat_queue = queue.Queue()
        app.tts = None
        app.history_file = data / "session.jsonl"
        app.history = []
        app.memory = h.default_memory()
        app.prompt = h.PROMPT_FILE.read_text(encoding="utf-8")
        app.screen_context = h.ScreenContext()
        app.watcher = SimpleNamespace(running=lambda: False)
        app.user_turns = 0
        app.recent_auto_answers = []
        app.last_user_activity_at = 0
        app._runtime_log = lambda message: None
        app._line = lambda who, text, tag: print(json.dumps({"speaker": who, "text": text}, ensure_ascii=False), flush=True)
        app._speak = lambda text: None
        with patch.multiple(h, DATA_DIR=data, MEMORY_FILE=data / "memory.json"):
            with patch.multiple(a, DATA_DIR=data, MEMORY_FILE=data / "memory.json"):
                app._on_mic_text(transcript)
                kind, text = app.chat_queue.get_nowait()
                assert kind == "user" and text == transcript
                app._answer_user(text)
                events = [json.loads(line) for line in (data / "generation.jsonl").read_text(encoding="utf-8").splitlines()]
                assert events[-1]["plan"]["action"] == "respond"
                print(json.dumps({"stage": "stt_to_decision", "plan": events[-1]["plan"], "accepted": events[-1]["reason"]}, ensure_ascii=False), flush=True)

        # Known, static screen fixture through the real image model, without reading private desktop content.
        image = Image.new("RGB", (1280, 720), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 44)
        for y, text in [(60, "네트워크 강의"), (180, "TCP 연결 수립"), (300, "SYN → SYN-ACK → ACK"), (420, "게임 화면이 아니라 공부 자료입니다.")]:
            draw.text((65, y), text, font=font, fill="black")
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        observation = h.one_shot(config, [{"role": "user", "content": "이 화면에서 실제로 읽히는 큰 글자와 앱 종류를 짧게 적어. 없는 사건은 추측하지 마."}],
                                model=config["vision_model"], images=[base64.b64encode(buffer.getvalue()).decode()], timeout=60)
        print(json.dumps({"stage": "real_vision", "observation": observation}, ensure_ascii=False), flush=True)
        assert "TCP" in observation, "Vision missed large fixture text"
        history = [{"role": "assistant", "content": line, "source": "idle", "generation_version": 2} for line in [
            "요괴가 보물에서 튀어나오면 어떨까?", "화면에 왕관이 생기면 재밌겠지?", "왕관 위로 불꽃이 터지면 멋지겠지?", "불꽃이 꽃으로 변하면 어떨까?"]]
        memory = {"broadcast_state": {"action": "hypothetical", "next_intent": "꽃에 또 장식을 더하기"}}
        for index in range(4):
            messages = h.make_messages(app.prompt, memory, history, 16, observation)
            messages[0]["_screen_pending"] = index == 0
            control = h.broadcast_instruction("screen" if index == 0 else "idle")
            messages.append({"role": "user", "content": control, "_event": True})
            events = []
            answer = h.generate_reply(config, messages, [x["content"] for x in history[-6:]], control,
                                      timeout=90, on_attempt=events.append, on_state=lambda state: h.apply_reply_state(memory, state))
            print(json.dumps({"stage": "grounded_continuation", "turn": index + 1, "answer": answer,
                              "plan": events[-1]["plan"]}, ensure_ascii=False), flush=True)
            assert events[-1]["plan"]["basis"] in {"screen", "reflection"}, "Assistant monologue is not user evidence"
            if index == 0:
                assert events[-1]["plan"]["action"] == "screen" and ("네트워크" in answer or "TCP" in answer), "Fresh screen was ignored"
            history.append({"role": "assistant", "content": answer, "source": "idle", "generation_version": 2})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    live() if args.live else unittest.main(argv=[__file__])
