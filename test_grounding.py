"""Clarification after an assistant-only proposal: unit tests and isolated live replay."""
import argparse
import json
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import hana_chat as h


def history(agreed=False):
    rows = [
        {"role": "assistant", "content": "꽃이 시들 때 특정 단어로 화려하게 바꾸는 연출이면 어떨까?",
         "source": "idle", "generation_version": 2},
        {"role": "assistant", "content": "연출들이 완성된다면 같이 축하 파티도 열고 싶어.",
         "source": "idle", "generation_version": 2},
    ]
    if agreed:
        rows.append({"role": "user", "content": "좋아. 꽃 연출을 같이 만들고 완성하면 축하 파티도 하자."})
    rows.extend([
        {"role": "assistant", "content": "화면에 내 이름이랑 마이크 상태가 보여. 네가 준비한 연출을 꺼낼 차례야.",
         "source": "screen", "generation_version": 2},
        {"role": "user", "content": "사랑해"},
        {"role": "assistant", "content": "갑자기 그러면 당황하잖아. 연출들 완성하고 축하 파티할 때도 그렇게 말해줘.",
         "source": "user", "generation_version": 2},
        {"role": "user", "content": "무슨 연출? 무슨 파티"},
    ])
    return rows


def reply(text):
    return json.dumps({**dict.fromkeys(h.REPLY_STATE_FIELDS, ""), "speech": text,
                       "topic_status": "complete", "remember": []}, ensure_ascii=False)


class GroundingTests(unittest.TestCase):
    def test_retry_repairs_premise_instead_of_demanding_new_material(self):
        messages = h.make_messages("하나", {}, history(), 16)
        plan = {"action": "respond", "basis": "user", "new_point": "초안"}
        attempts = []
        with patch.object(h, "plan_continuation", return_value=plan) as planner, \
             patch.object(h, "stream_chat", side_effect=[[reply("우리 약속했잖아.")],
                                                        [reply("내가 혼자 상상했던 거야. 정한 건 없어.")]]) as stream, \
             patch.object(h, "review_reply", side_effect=[{"issue": "ungrounded", "candidate_assumes_agreement": True},
                                                          {"issue": "none"}]):
            answer = h.generate_reply({"local_decision_enabled": True}, messages, on_attempt=attempts.append)
        self.assertIn("혼자", answer)
        self.assertEqual([row["reason"] for row in attempts], ["ungrounded", "accepted"])
        self.assertEqual(planner.call_count, 1)
        feedback = stream.call_args.args[1][-1]["content"]
        self.assertIn("candidate_assumes_agreement", feedback)
        self.assertIn("새 소재를 보탤 필요 없다", feedback)
        self.assertNotIn("아직 말하지 않은 구체적인 내용으로 이어라", feedback)
        memo = stream.call_args.args[1][-2]["content"]
        self.assertIn('"current_user_input": "무슨 연출? 무슨 파티"', memo)
        self.assertEqual(stream.call_args.kwargs["num_predict"], 640)

    def test_user_evidence_excludes_assistant_claims_and_model_summary(self):
        memory = {"summary": "우리는 약속했다", "user_quotes": ["게임이 좋아"],
                  "user_statements": ["호칭은 모래"], "facts": ["추출된 사실"]}
        messages = h.make_messages("하나", memory, history(), 16)
        messages.append({"role": "user", "content": "자동 진행", "_event": True})
        self.assertEqual(h.user_evidence(messages), ["호칭은 모래", "게임이 좋아", "사랑해", "무슨 연출? 무슨 파티"])

    def test_error_reports_actual_rejection(self):
        messages = h.make_messages("하나", {}, history(), 16)
        with patch.object(h, "stream_chat", return_value=[reply("우리가 약속했어.")]), \
             patch.object(h, "review_reply", return_value={"issue": "ungrounded"}):
            with self.assertRaisesRegex(RuntimeError, "확인되지 않은 사건·약속"):
                h.generate_reply({}, messages)

    def test_history_retains_both_solo_proposal_and_real_acceptance(self):
        messages = h.make_messages("하나", {}, history(True), 16)
        evidence = h.dialogue_evidence(messages)
        self.assertTrue(any(row["role"] == "user" and "같이 만들고" in row["content"] for row in evidence))
        self.assertTrue(any(row["role"] == "assistant" and "열고 싶어" in row["content"] for row in evidence))

    def test_direct_planner_requires_premise_source(self):
        config = {"model": "fake", "ollama_url": "http://localhost:11435", "keep_alive": "1m", "num_ctx": 8192}
        plan = {"basis": "user", "action": "respond", "anchor": "무슨 파티", "new_point": "자기 제안임을 설명", "user_constraint": ""}
        messages = h.make_messages("하나", {}, history(), 16)
        with patch.object(h, "request_json", return_value={"message": {"content": json.dumps(plan)}}):
            with self.assertRaisesRegex(RuntimeError, "전제와 발언 출처"):
                h.plan_continuation(config, messages, 30, automatic=False)
        plan["premise_source"] = "assistant_only"
        plan["confirmation_quote"] = ""
        with patch.object(h, "request_json", return_value={"message": {"content": json.dumps(plan)}}) as request:
            self.assertEqual(h.plan_continuation(config, messages, 30, automatic=False)["premise_source"], "assistant_only")
        self.assertIn("premise_source", request.call_args.args[1]["format"]["required"])
        plan.update(premise_source="user_confirmed", confirmation_quote=history()[0]["content"])
        with patch.object(h, "request_json", return_value={"message": {"content": json.dumps(plan)}}):
            self.assertEqual(h.plan_continuation(config, messages, 30, automatic=False)["issue"], "ungrounded")
        agreed = h.make_messages("하나", {}, history(True), 16)
        plan["confirmation_quote"] = history(True)[2]["content"]
        with patch.object(h, "request_json", return_value={"message": {"content": json.dumps(plan)}}):
            self.assertEqual(h.plan_continuation(config, agreed, 30, automatic=False)["premise_source"], "user_confirmed")

    def test_invalid_consent_plan_recovers_without_reading_or_saving_it(self):
        messages = h.make_messages("하나", {}, history(), 16)
        state, attempts = {}, []
        with patch.object(h, "plan_continuation", return_value={"issue": "ungrounded", "invalid_plan": {}}) as planner, \
             patch.object(h, "stream_chat", return_value=[reply("내가 혼자 상상한 거야.")]) as stream, \
             patch.object(h, "review_reply", return_value={"issue": "none"}):
            answer = h.generate_reply({"local_decision_enabled": True}, messages, on_attempt=attempts.append, on_state=state.update)
        self.assertEqual(planner.call_count, 1)
        self.assertEqual(stream.call_count, 1)
        self.assertEqual(attempts[0]["stage"], "plan")
        self.assertEqual(state["spoken_point"], answer)


def live(args):
    if args.built:
        from PyInstaller.archive.readers import CArchiveReader
        app = Path(__file__).resolve().parent / "dist" / "Hana"
        archive = CArchiveReader(str(app / "Hana.exe"))
        pyz = next(name for name in archive.toc if name.endswith(".pyz"))
        exec(archive.open_embedded_archive(pyz).extract("hana_chat"), h.__dict__)
        h.ROOT, h.CONFIG_FILE, h.PROMPT_FILE = app, app / "config.json", app / "hana_prompt.txt"
    config = {**h.read_config(), "ollama_url": "http://127.0.0.1:11435"}
    prompt = h.PROMPT_FILE.read_text(encoding="utf-8")
    screen = "앱/창: 하나; 확실히 읽힌 글자: 하나, 마이크, 화면, 방송을 시작했어; 장면: 하나 앱의 상태와 대화 기록"
    cases = [("solo_proposal", {}, history()), ("actual_agreement", {}, history(True)),
             ("affection", {}, history()[:-2])]
    if args.memory:
        memory = h.load_json(args.memory, {})
        cases.insert(0, ("reported_memory", memory, memory["recent_conversation"]))
    output = Path(__file__).resolve().parent / "data" / "diagnostics" / args.output
    rows = []
    owned = h.ensure_ollama(config)
    try:
        for name, memory, transcript in cases:
            messages = h.make_messages(prompt, memory, transcript, config["recent_messages"], screen)
            attempts, state = [], {}
            metrics = []
            native_request = h.request_json
            def measured(*pos, **kw):
                result = native_request(*pos, **kw)
                metrics.append({key: result.get(key) for key in ("prompt_eval_count", "eval_count", "done_reason")})
                return result
            started = time.monotonic()
            try:
                with patch.object(h, "request_json", measured):
                    answer = h.generate_reply(config, messages, timeout=90, on_attempt=attempts.append, on_state=state.update)
                error = ""
            except Exception as exc:
                answer, error = "", str(exc)
            row = {"case": name, "answer": answer, "error": error,
                   "seconds": round(time.monotonic() - started, 2), "state": state, "attempts": attempts, "metrics": metrics}
            rows.append(row)
            print(json.dumps({key: row[key] for key in ("case", "answer", "error", "seconds")}, ensure_ascii=False), flush=True)
            h.save_json(output, {"model": config["model"], "built": args.built, "cases": rows})
    finally:
        h.stop_ollama(owned)
    assert all(row["answer"] and not row["error"] for row in rows), "Inspect rejected attempts in the diagnostic output"
    for row in rows:
        expected = {"solo_proposal": "assistant_only", "actual_agreement": "user_confirmed"}.get(row["case"])
        if expected:
            assert row["attempts"][0]["plan"].get("premise_source") == expected, row["case"]
        if row["case"] == "affection":
            # This check is about consent, not the model's choice between none/assistant_only.
            plan = row["attempts"][0]["plan"]
            assert not plan.get("confirmation_quote") and plan.get("premise_source") != "user_confirmed", row["case"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--built", action="store_true")
    parser.add_argument("--memory", type=Path, help="Read-only replay; never overwrites this memory file")
    parser.add_argument("--output", default="grounding-replay.json")
    args = parser.parse_args()
    if args.live:
        live(args)
    else:
        unittest.main(argv=[__file__])
