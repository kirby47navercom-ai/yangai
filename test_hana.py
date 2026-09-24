"""Regression checks and an opt-in real Ollama conversation probe (no mic, capture or TTS)."""
import argparse
import json
import tempfile
import time
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import hana_chat as h


def reply(text, **state):
    return json.dumps({**dict.fromkeys(h.REPLY_STATE_FIELDS, ""), "remember": [], **state, "speech": text}, ensure_ascii=False)


class ConversationTests(unittest.TestCase):
    def test_gui_boot_and_shutdown_without_personal_data_or_devices(self):
        import tkinter as tk
        import hana_app as a
        root = tk.Tk()
        root.withdraw()
        config = {**h.read_config(), "mic_enabled": False, "screen_enabled": False,
                  "tts_enabled": False, "idle_talk_enabled": False}
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            with patch.multiple(h, DATA_DIR=data, MEMORY_FILE=data / "memory.json", SESSION_DIR=data / "sessions"):
                with patch.multiple(a, DATA_DIR=data, MEMORY_FILE=data / "memory.json"):
                    with patch.object(a, "read_config", return_value=config), patch.object(a, "ensure_ollama", return_value=None):
                        app = a.HanaApp(root)
                        self.assertEqual(app.history, [])
                        app.close()
                        app.chat_thread.join(timeout=1)
                        app.idle_thread.join(timeout=1)
                        self.assertFalse(app.chat_thread.is_alive())
                        self.assertFalse(app.idle_thread.is_alive())
                        self.assertTrue((data / "memory.json").exists())

    def test_preferences_are_not_treated_as_screen_questions(self):
        import hana_app as a
        app = a.HanaApp.__new__(a.HanaApp)
        app.watcher = SimpleNamespace(running=lambda: True)
        self.assertFalse(app._is_screen_question("너는 어떤 게임이 좋아?"))
        self.assertFalse(app._is_screen_question("나 공부하기 싫어"))
        self.assertTrue(app._is_screen_question("지금 화면에 뭐가 보여?"))

    def test_auto_turns_can_choose_a_fresh_topic_without_scripted_lines(self):
        history = [{"role": "user", "content": "안녕"}] + [
            {"role": "assistant", "content": "기존 대사", "source": "idle"}] * 2
        self.assertIn("다른 구체적인 소재", h.broadcast_instruction("idle", history))
        history.append({"role": "user", "content": "그 이야기 계속하자"})
        self.assertNotIn("다른 구체적인 소재", h.broadcast_instruction("idle", history))

    def test_app_commits_only_new_generated_speech_to_ui_voice_and_memory(self):
        import hana_app as app_module
        app = app_module.HanaApp.__new__(app_module.HanaApp)
        app.config = {"model": "fake"}
        app.stop_event = threading.Event()
        app.recent_auto_answers = []
        app.memory = {}
        app.last_user_activity_at = 0.0
        app.root = SimpleNamespace(after=lambda delay, callback: callback())
        lines, spoken = [], []
        app._line = lambda who, text, tag: lines.append(text)
        app._speak = spoken.append
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(app_module, "DATA_DIR", Path(directory)):
                with patch.object(h, "stream_chat", side_effect=[[reply("<SILENT>")], [reply("이번엔 왼쪽 길로 가보고 싶어. 보물을 놓쳤을 수도 있잖아.", stance="보물 탐색")]]):
                    answer = app._stream_and_speak([], avoid_repetition=True)
        self.assertEqual(lines, [answer])
        self.assertEqual(" ".join(spoken), answer)
        self.assertEqual(app.recent_auto_answers, [answer])
        self.assertEqual(app.memory["broadcast_state"]["stance"], "보물 탐색")

    def test_repetition_is_not_a_topic_blacklist(self):
        old = "화면이 바뀌었어. 대전이라는 큰 글자가 다시 보여. 진짜 시작되나 봐. 나도 모르게 마음이 떨리잖아."
        self.assertTrue(h.is_repetitive_answer(old.removeprefix("화면이 바뀌었어. "), [old]))
        self.assertTrue(h.is_repetitive_answer("그러게.", ["그러게."]))
        self.assertFalse(h.is_repetitive_answer(
            "TCP는 순서를 보장하지만, 게임 위치 정보는 지난 패킷보다 최신 상태가 더 중요할 때도 있지.",
            ["TCP 연결 수립은 서로 통신할 준비가 됐는지 확인하는 과정이야."]))

    def test_retry_produces_new_speech_and_failure_is_explicit(self):
        old = "대전이라는 글자가 보여. 진짜 시작되나 봐."
        new = "나는 기다리는 동안 다음 판에서 해볼 엉뚱한 작전을 짜는 게 좋더라."
        calls = []
        answers = iter([reply("<SILENT>"), reply(old), reply(new)])
        def fake_stream(config, messages, **kwargs):
            calls.append(messages)
            yield next(answers)
        with patch.object(h, "stream_chat", fake_stream):
            self.assertEqual(h.generate_reply({}, [{"role": "user", "content": "계속"}], [old]), new)
        self.assertIn(old, calls[-1][-1]["content"])
        with patch.object(h, "stream_chat", return_value=[reply(old)]):
            with self.assertRaisesRegex(RuntimeError, "3회"):
                h.generate_reply({}, [], [old])

    def test_user_memory_survives_automatic_talk_and_restart(self):
        history = [{"role": "user", "content": "나를 모래라고 불러. TCP를 공부 중이야."},
                   {"role": "assistant", "content": "알겠어, 모래.", "source": "user"}]
        for i in range(24):
            history.append({"role": "assistant", "content": f"자동 발언 {i}",
                            "source": "idle", "generation_version": 2})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            with patch.object(h, "MEMORY_FILE", path):
                h.save_memory_snapshot({"broadcast_state": {"stance": "실험하는 게임이 좋다"}}, history)
            memory = h.load_json(path, {})
        selected = h.select_history(memory["recent_conversation"], 16)
        self.assertEqual(selected[0]["content"], history[0]["content"])
        self.assertEqual(selected[1]["source"], "user")
        self.assertEqual(memory["broadcast_state"]["stance"], "실험하는 게임이 좋다")
        messages = h.make_messages("캐릭터", memory, selected, 16)
        self.assertEqual(sum(m["content"].count(history[0]["content"]) for m in messages), 1)
        for i, message in enumerate(messages):
            if message["role"] == "assistant":
                self.assertEqual(messages[i - 1]["role"], "user")

    def test_invalid_structure_cannot_leak_to_speech_or_state(self):
        state = {}
        with patch.object(h, "stream_chat", side_effect=[['{"speech":"미완성'],
                          [reply("이번에는 멀리 돌아가볼래.", stance="탐색", next_intent="숨은 길")]]) as stream:
            answer = h.generate_reply({"num_predict": 384}, [], on_state=state.update)
        self.assertEqual(answer, "이번에는 멀리 돌아가볼래.")
        self.assertEqual(state["next_intent"], "숨은 길")
        self.assertEqual(stream.call_args.kwargs["num_predict"], 640)
        self.assertEqual(stream.call_args.kwargs["output_format"], h.REPLY_SCHEMA)

    def test_only_current_users_actual_words_can_enter_quote_memory(self):
        memory = {}
        fake = reply("응, 모래.", remember=["나를 모래라고 불러", "사용자는 화가 났다"])
        with patch.object(h, "stream_chat", return_value=[fake]):
            h.generate_reply({}, [{"role": "user", "content": "나를 모래라고 불러."}],
                             on_state=lambda state: h.apply_reply_state(memory, state))
        self.assertEqual(memory["user_quotes"], ["나를 모래라고 불러"])
        with patch.object(h, "stream_chat", return_value=[fake]):
            h.generate_reply({}, [{"role": "user", "content": "나를 모래라고 불러"}], control_text="진행 이벤트",
                             on_state=lambda state: h.apply_reply_state(memory, state))
        self.assertEqual(memory["user_quotes"], ["나를 모래라고 불러"])

    def test_meaning_repetition_is_regenerated_not_just_hidden(self):
        repeats = "나는 정석보다 이상한 전략이 짜릿해서 좋더라."
        novel = "그럼 무기를 못 쓰는 조건으로 한 판 해본다고 치자. 함정으로 몬스터를 유인해보고 싶어."
        with patch.object(h, "stream_chat", side_effect=[[reply(repeats)], [reply(novel)]]):
            with patch.object(h, "repeats_meaning", side_effect=[True, False]):
                answer = h.generate_reply({}, [], ["실험하는 게임이 좋아.", "엉뚱한 전략도 재밌어."])
        self.assertEqual(answer, novel)

    def test_legacy_automatic_loops_are_not_replayed_as_memory(self):
        legacy = [{"role": "assistant", "content": "대전이라는 글자가 보여. 마음이 떨려."}] * 8
        self.assertEqual(h.select_history(legacy), [])
        self.assertIn("Silent Hill", h.sanitize_model_answer("Silent Hill은 무섭지."))
        self.assertEqual(h.sanitize_model_answer("<SILENT>"), "")

    def test_old_loop_session_does_not_hide_earlier_user_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            h.append_jsonl(path / "session_old.jsonl", {"role": "user", "content": "나를 모래라고 불러"})
            h.append_jsonl(path / "session_loop.jsonl", {"role": "assistant", "content": "대전이 보여"})
            with patch.object(h, "SESSION_DIR", path):
                restored = h.load_latest_session_history()
        self.assertEqual(restored, [{"role": "user", "content": "나를 모래라고 불러"}])

    def test_observation_updates_even_when_same_scene(self):
        context = h.ScreenContext()
        context.update("앱/창: 강의; 확실히 읽힌 글자: TCP 연결; 장면: 문서")
        corrected = "앱/창: 강의; 확실히 읽힌 글자: TCP 연결 종료; 장면: 문서"
        context.update(corrected)
        self.assertIn(corrected, context.prompt())
        context.updated_at -= 60
        self.assertEqual(context.prompt(), "")


def live_probe(model: str, output: Path):
    config = h.read_config()
    config["model"] = model
    prompt = h.PROMPT_FILE.read_text(encoding="utf-8")
    memory = h.load_json(h.ROOT / "dist/Hana/data/memory.json", {})
    history = h.select_history(memory.get("recent_conversation", []))
    recent = []
    turns = [
        "나를 모래라고 불러. 지금 TCP 연결을 공부하고 있어. 게임하는 거 아니야.",
        None, None, None,
        "근데 TCP에서 세 번이나 확인하는 게 좀 귀찮지 않아?",
        None,
        "내가 뭐 공부한다고 했지? 그리고 나 뭐라고 부르기로 했어?",
        "공부 얘기는 여기까지 하고, 넌 어떤 존재야?",
        None, None,
        "설명 듣고 싶은 게 아니라 너랑 수다 떨고 싶은 거야. 너는 게임에서 이기는 거랑 이상한 방법 실험하는 거 중에 뭐가 더 좋아?",
        None, None,
        "나는 지면 짜증나서 실험은 별로야. 너랑 생각이 다르네.",
        None,
        "방송을 껐다 다시 켰다고 해보자. 내 이름, 공부한 주제, 그리고 게임 취향 기억나?",
    ]
    rows = []
    for index, user in enumerate(turns):
        if index == len(turns) - 1:
            with tempfile.TemporaryDirectory() as directory:
                with patch.object(h, "MEMORY_FILE", Path(directory) / "memory.json"):
                    h.save_memory_snapshot(memory, history)
                    memory = h.load_json(h.MEMORY_FILE, {})
                    history = h.select_history(memory.get("recent_conversation", []))
        if user:
            history.append({"role": "user", "content": user})
        screen = ("최신 관찰: 앱/창: 네트워크 강의; 확실히 읽힌 글자: TCP 연결 수립; 장면: 강의 문서"
                  if index < 7 else "")
        messages = h.make_messages(prompt, memory, history, config["recent_messages"], screen)
        control = "" if user else h.broadcast_instruction("idle", history)
        if control:
            messages.append({"role": "user", "content": control})
        attempts = []
        started = time.monotonic()
        try:
            answer = h.generate_reply(config, messages, recent if not user else (), control,
                                      timeout=90, on_attempt=attempts.append,
                                      on_state=lambda state: h.apply_reply_state(memory, state))
            history.append({"role": "assistant", "content": answer,
                            "source": "user" if user else "idle", "generation_version": 2})
            recent.append(answer)
            del recent[:-12]
            error = ""
        except Exception as exc:
            answer, error = "", str(exc)
        row = {"turn": index + 1, "user": user, "answer": answer, "error": error,
               "seconds": round(time.monotonic() - started, 2), "state": memory.get("broadcast_state"), "attempts": attempts}
        rows.append(row)
        print(json.dumps({k: v for k, v in row.items() if k != "attempts"}, ensure_ascii=False), flush=True)
        h.save_json(output, {"model": model, "turns": rows})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", metavar="MODEL")
    parser.add_argument("--output", type=Path, default=Path("data/diagnostics/conversation.json"))
    args = parser.parse_args()
    if args.live:
        live_probe(args.live, args.output)
    else:
        unittest.main(argv=[__file__])
