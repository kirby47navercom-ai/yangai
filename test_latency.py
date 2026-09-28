"""Deadline/startup regressions and a bounded, opt-in local-model startup probe."""
import argparse
import io
import json
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import hana_app as a
import hana_chat as h
from test_hana import reply


class LatencyTests(unittest.TestCase):
    def test_owned_server_uses_cache_defaults_without_changing_parent_environment(self):
        with patch.dict(h.os.environ, {}, clear=True), patch.object(h, "_find_ollama", return_value=Path("ollama.exe")), \
             patch.object(h, "request_json", side_effect=[OSError("offline"), {}]), \
             patch.object(h.subprocess, "Popen") as process:
            process.return_value.poll.return_value = None
            self.assertIs(h.ensure_ollama({"ollama_url": "http://127.0.0.1:11435"}), process.return_value)
            self.assertEqual(process.call_args.kwargs["env"]["OLLAMA_FLASH_ATTENTION"], "1")
            self.assertEqual(process.call_args.kwargs["env"]["OLLAMA_KV_CACHE_TYPE"], "q8_0")
            self.assertNotIn("OLLAMA_KV_CACHE_TYPE", h.os.environ)

    def test_symbol_only_observation_is_not_screen_evidence(self):
        with patch.object(h, "request_json", return_value={"message": {"content": "@@@@@@@@"}}):
            with self.assertRaises(RuntimeError):
                h.one_shot({"model": "fake", "keep_alive": "1m", "num_ctx": 8192,
                            "ollama_url": "http://localhost"}, [{"role": "user", "content": "screen"}], images=["image"])

    def test_plan_speech_and_review_share_one_deadline(self):
        clock = [0.0]
        budgets = []
        def plan(*args, **kwargs):
            budgets.append(args[2]); clock[0] += 4
            return {"action": "respond", "basis": "user"}
        def speech(*args, **kwargs):
            budgets.append(kwargs["timeout"]); clock[0] += 4
            yield reply("알겠어.")
        def review(*args):
            budgets.append(args[-1]); clock[0] += 3
            return {"issue": "none"}
        states = []
        with patch.object(h.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(h, "plan_continuation", plan), patch.object(h, "stream_chat", speech), \
             patch.object(h, "review_reply", review):
            with self.assertRaises(TimeoutError):
                h.generate_reply({"local_decision_enabled": True}, [], timeout=10, on_state=states.append)
        self.assertEqual(budgets, [10, 6, 2])
        self.assertEqual(states, [])

    def test_retries_cannot_restart_timeout(self):
        clock = [0.0]
        def speech(*args, **kwargs):
            clock[0] += 6
            yield reply("같은 말")
        with patch.object(h.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(h, "stream_chat", speech), patch.object(h, "review_reply") as review:
            with self.assertRaises(TimeoutError):
                h.generate_reply({"semantic_repeat_check": False}, [], ["같은 말"], timeout=10)
        review.assert_not_called()

    def test_continuous_stream_cannot_extend_deadline(self):
        response = io.BytesIO(b'{"message":{"content":"a"}}\n' * 10)
        config = {"model": "fake", "keep_alive": "1m", "num_ctx": 8192,
                  "num_predict": 384, "temperature": 1, "top_p": .95, "ollama_url": "http://localhost"}
        with patch.object(h, "urlopen", return_value=response), \
             patch.object(h.time, "monotonic", side_effect=[0, 1, 2, 11]):
            with self.assertRaises(TimeoutError):
                list(h.stream_chat(config, [], timeout=10))
        self.assertTrue(response.closed)

    def test_expired_first_observation_does_not_block_speech_forever(self):
        app = a.HanaApp.__new__(a.HanaApp)
        app.config = {"vision_response_timeout": 30}
        app.last_user_activity_at = 0; app.last_idle_requested_at = 1
        app.watcher = SimpleNamespace(running=lambda: True, last_error="", started_at=0)
        app.screen_context = SimpleNamespace(prompt=lambda: "")
        app.pending_screen = False
        with patch.object(a.time, "monotonic", return_value=10), patch.object(app, "_answer_broadcast") as speak:
            app._answer_idle(); speak.assert_not_called()
        with patch.object(a.time, "monotonic", return_value=32), patch.object(app, "_answer_broadcast") as speak:
            app._answer_idle(); speak.assert_called_once_with("idle")

    def test_previous_session_is_memory_not_current_broadcast(self):
        app = a.HanaApp.__new__(a.HanaApp)
        app.config = {"recent_messages": 16}
        app.prompt = "하나"
        app.memory = {"facts": ["사용자는 모래"], "broadcast_state": {"topic": "옛날 파티"}}
        app.history = [{"role": "user", "content": "무슨 파티?"}]
        app.session_history_start = 1; app.screen_event_id = 0; app.recent_auto_answers = []
        app.screen_context = SimpleNamespace(prompt=lambda: "현재 강의 화면")
        with patch.object(app, "_stream_and_speak", return_value="") as speak, patch.object(app, "_remember_answer"):
            app._answer_broadcast("screen")
        messages = speak.call_args.args[0]
        self.assertEqual(h.dialogue_evidence(messages), [])
        self.assertEqual(messages[0]["_state"], {})
        self.assertEqual(messages[0]["_memory"]["facts"], ["사용자는 모래"])
        self.assertEqual(app.memory["broadcast_state"]["topic"], "옛날 파티")
        self.assertEqual(app.history[0]["content"], "무슨 파티?")


def live_probe(built=False, image_path=None):
    root = Path(__file__).resolve().parent
    if built:
        import marshal
        from PyInstaller.archive.readers import CArchiveReader
        archive = CArchiveReader(str(root / "dist/Hana/Hana.exe"))
        pyz = next(name for name in archive.toc if name.endswith(".pyz"))
        h.__file__ = str(root / "dist/Hana/hana_chat.py")
        exec(archive.open_embedded_archive(pyz).extract("hana_chat"), h.__dict__)
        exec(marshal.loads(archive.extract("hana_app")), a.__dict__)
    config = h.read_config()
    config["ollama_url"] = "http://127.0.0.1:11435"
    original_request = h.request_json
    def measured_request(url, payload=None, timeout=30):
        result = original_request(url, payload, timeout)
        if payload and url.endswith("/api/chat"):
            print(json.dumps({"request_model": payload["model"], **{key: result.get(key) for key in
                ("load_duration", "prompt_eval_duration", "eval_duration", "prompt_eval_count", "eval_count")},
                "resident": original_request(config["ollama_url"] + "/api/ps").get("models", []),
                "vision_result": result if payload["model"] == config["vision_model"] else None}, ensure_ascii=False), flush=True)
        return result
    h.request_json = measured_request
    owned = h.ensure_ollama(config)
    tts = None
    startup = time.monotonic()
    try:
        app = a.HanaApp.__new__(a.HanaApp)
        app.config = config; app.prompt = h.PROMPT_FILE.read_text(encoding="utf-8")
        # Read only: the actual previous session is needed to reproduce the restart fault.
        app.memory = h.load_json(root / "dist/Hana/data/memory.json", {})
        app.history = list(app.memory.get("recent_conversation", []))
        app.session_history_start = len(app.history)
        app.recent_auto_answers = [x["content"] for x in app.history if x["role"] == "assistant"][-6:]
        app.screen_event_id = 1; app.pending_screen = True
        app.screen_context = h.ScreenContext()
        app.stop_event = threading.Event(); app.last_user_activity_at = 0
        app.watcher = SimpleNamespace(capture_revision=0)
        app.root = SimpleNamespace(after=lambda _, callback: callback())
        app._runtime_log = lambda message: print(message, flush=True)
        spoken = []
        app._line = lambda *args: None
        app._speak = lambda text, voice=None: spoken.append(text)
        app._remember_answer = lambda text, source: app.history.append(
            {"role": "assistant", "content": text, "source": source, "generation_version": 2}) if text else None
        rows = []
        observation = "앱/창: 하나; 확실히 읽힌 글자: 하나, 마이크, 화면, 음성; 장면: 캐릭터 그림과 빈 대화창"
        if image_path:
            from PIL import Image
            import shutil
            config["gpt_sovits_port"] = 9883
            yaml = root / "data/diagnostics/latency-media/config.yaml"
            yaml.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(h.ROOT / config["gpt_sovits_config"], yaml)
            config["gpt_sovits_config"] = str(yaml)
            tts = h.GPTSoVITSTTSWorker(config, root / "data/diagnostics/latency-media")
            tts.prewarm(lambda status: print(json.dumps({"tts_status": status}, ensure_ascii=False), flush=True))
            watcher = h.ScreenWatcher(config, h.ScreenContext())
            with Image.open(image_path) as image, patch.object(watcher, "_capture_image", return_value=(image.convert("RGB"), time.monotonic())):
                try:
                    observation = watcher.answer_question("실제로 보이는 큰 글자와 화면 종류만 짧게 적어.")
                except Exception as exc:
                    observation = ""
                    print(json.dumps({"vision_error": str(exc)}, ensure_ascii=False), flush=True)
            print(json.dumps({"vision_seconds": round(time.monotonic()-startup, 2), "observation": observation}, ensure_ascii=False), flush=True)
        def attempt_log(_path, event):
            print(json.dumps({"attempt": event.get("attempt"), "reason": event.get("reason")}, ensure_ascii=False), flush=True)
        # Fixed known observation avoids recording the user's desktop or microphone.
        for index in range(2):
            app.screen_context.update(observation)
            started = time.monotonic(); error = ""
            try:
                with patch.object(a, "append_jsonl", attempt_log):
                    app._answer_broadcast("screen" if index == 0 and observation else "idle")
            except Exception as exc:
                error = str(exc)
            row = {"turn": index + 1, "packaged": built, "seconds": round(time.monotonic()-started, 2),
                   "tts_submitted": len(spoken) > index, "speech": spoken[index] if len(spoken)>index else "", "error": error}
            if tts and row["speech"]:
                audio_started = time.monotonic(); wav = []
                def inspect_wave(path, cancel):
                    import wave
                    with wave.open(str(path), "rb") as audio:
                        wav.append({"frames": audio.getnframes(), "channels": audio.getnchannels(),
                                    "rate": audio.getframerate()})
                with patch.object(h, "play_wav_file", inspect_wave):
                    tts._speak(row["speech"], threading.Event())
                row.update(tts_seconds=round(time.monotonic()-audio_started, 2), wav=wav,
                           startup_to_wave_seconds=round(time.monotonic()-startup, 2), audible_playback=False)
            rows.append(row); print(json.dumps(row, ensure_ascii=False), flush=True)
            if error: break
        output = "startup-latency-built.json" if built else "startup-latency.json"
        h.save_json(root / "data/diagnostics" / output, rows)
        if len(rows) != 2 or any(row["error"] or not row["tts_submitted"] or
                                (tts and not row.get("wav")) for row in rows):
            raise RuntimeError("Live latency probe failed; inspect the private diagnostic output")
    finally:
        if tts: tts.close()
        h.stop_ollama(owned)
        h.request_json = original_request


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--built", action="store_true")
    parser.add_argument("--image", type=Path, help="Analyze a supplied screenshot and synthesize muted WAVs; no live capture")
    args, rest = parser.parse_known_args()
    live_probe(args.built, args.image) if args.live else unittest.main(argv=[__file__, *rest])
