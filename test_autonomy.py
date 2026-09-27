"""Headless real-model multi-turn probe; synthetic inputs, isolated memory, no devices."""
import argparse
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import hana_chat as h


def run(args):
    if getattr(args, "built", False):
        from PyInstaller.archive.readers import CArchiveReader
        app_root = ROOT / "dist" / "Hana"
        archive = CArchiveReader(str(app_root / "Hana.exe"))
        pyz = next(name for name in archive.toc if name.endswith(".pyz"))
        exec(archive.open_embedded_archive(pyz).extract("hana_chat"), h.__dict__)
        # No GUI entry point or personal data is loaded. Only the packaged generator runs.
        h.ROOT = app_root
        h.CONFIG_FILE = app_root / "config.json"
        h.PROMPT_FILE = app_root / "hana_prompt.txt"
    config = h.read_config()
    if args.model:
        config["model"] = args.model
    config["ollama_url"] = "http://127.0.0.1:11435"
    owned = h.ensure_ollama(config)
    prompt = h.PROMPT_FILE.read_text(encoding="utf-8")
    memory = {}
    history = []
    observation = "앱/창: 네트워크 강의; 확실히 읽힌 글자: TCP 연결 수립, SYN → SYN-ACK → ACK; 장면: 정지된 강의 슬라이드"
    screens = {0: observation,
               7: "앱/창: 테스트 게임; 확실히 읽힌 글자: 결과 패배, 보스 체력 1%, 다시 도전; 장면: 결과 화면",
               14: "앱/창: 테스트 게임; 확실히 읽힌 글자: 메인 메뉴, 음악 감상, 설정; 장면: 메뉴 화면"}
    users = {0: "난 모래야. 지금 TCP 공부하고 있어. 강의하듯 설명 말고 그냥 같이 수다 떨어줘.",
             5: "난 실험보다 확실하게 이기는 게 좋아. 너랑 생각이 다른가?",
             11: "위로 말고, 네가 한다면 다시 도전할지 말지 네 생각을 말해줘.",
             18: "아까 내 이름이랑 공부하던 거, 게임 취향 뭐라고 했지?",
             22: "게임 얘기 말고 겨울 얘기 하자. 나는 겨울보다 여름이 좋아."}
    rows = []
    output = ROOT / "data" / "diagnostics" / args.output
    original_request = h.request_json
    metrics = []
    def measured(*pos, **kw):
        result = original_request(*pos, **kw)
        if "prompt_eval_count" in result:
            metrics.append({k: result.get(k) for k in ("prompt_eval_count", "eval_count", "total_duration")})
        return result
    try:
        for index in range(args.turns):
            if index in screens:
                observation = screens[index]
            user = users.get(index)
            if user:
                history.append({"role": "user", "content": user})
            messages = h.make_messages(prompt, memory, history, 16, observation)
            messages[0]["_screen_pending"] = index in screens and not user
            control = "" if user else h.broadcast_instruction("screen" if index in screens else "idle")
            if control:
                messages.append({"role": "user", "content": control, "_event": True})
            events = []
            metrics.clear()
            started = time.monotonic()
            answer, error = "", ""
            try:
                with patch.object(h, "request_json", measured):
                    answer = h.generate_reply(config, messages,
                        [x["content"] for x in history[-12:] if x["role"] == "assistant"] if not user else [],
                        control, timeout=90, on_attempt=events.append,
                        on_state=lambda s: h.apply_reply_state(memory, s))
            except Exception as exc:
                error = str(exc)
            row = {"turn": index + 1, "model": config["model"], "packaged": bool(getattr(args, "built", False)),
                   "user": user, "answer": answer, "error": error,
                   "seconds": round(time.monotonic() - started, 2), "attempts": events,
                   "state": dict(memory.get("broadcast_state", {})), "metrics": list(metrics)}
            rows.append(row)
            h.save_json(output, rows)
            print(json.dumps({k: v for k, v in row.items() if k not in {"attempts", "metrics"}}, ensure_ascii=False), flush=True)
            if answer:
                history.append({"role": "assistant", "content": answer, "source": "user" if user else "idle", "generation_version": 2})
            with patch.object(h, "MEMORY_FILE", output.with_suffix(".memory.json")):
                h.save_memory_snapshot(memory, history)
                if index == 17:
                    memory = h.load_json(h.MEMORY_FILE, {})
                    history = memory["recent_conversation"]
        failures = [r["turn"] for r in rows if r["error"]]
        for row in rows:
            if row["answer"]:
                assert h.usable_assistant_history(row["answer"]), "Control output reached speech"
            if row["attempts"] and not row["error"]:
                plan = row["attempts"][-1]["plan"]
                if row["user"]:
                    assert plan["action"] == "respond", "User input lost"
                elif row["turn"] - 1 in screens:
                    assert plan["basis"] == "screen", "Fresh screen lost"
        if len(rows) >= 19:
            recalled = rows[18]["answer"]
            assert all(word in recalled for word in ("모래", "TCP")), "Restart memory lost"
            assert any(word in recalled for word in ("이기", "승리")), "Preference lost"
        assert not failures, f"Generation failures: {failures} (see output)"
    finally:
        h.stop_ollama(owned)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--turns", type=int, default=24)
    parser.add_argument("--model", help="Override only the test model; config.json is unchanged")
    parser.add_argument("--built", action="store_true", help="Test code inside dist/Hana/Hana.exe without launching its GUI")
    parser.add_argument("--output", default="autonomy-latest.json")
    parser.add_argument("--live", action="store_true", help="Start isolated local model server, no mic/capture/TTS")
    args = parser.parse_args()
    run(args) if args.live else parser.print_help()
