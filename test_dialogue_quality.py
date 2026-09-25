"""Opt-in real-model checks on synthetic dialogue. No personal memory, capture, mic or TTS."""
import argparse
import json
import time

import hana_chat as h


def messages():
    history = [
        {"role": "user", "content": "너는 게임에서 이기는 거랑 이상한 방법 실험하는 거 중에 뭐가 더 좋아?"},
        {"role": "assistant", "content": "실험하는 쪽이지! 정석대로 이기기만 하는 것보다 엉뚱한 작전을 시도하는 게 재밌거든.", "source": "user"},
        {"role": "user", "content": "나는 지면 짜증나서 실험은 별로야. 너랑 생각이 다르네."},
        {"role": "assistant", "content": "승부욕이 강하면 이기는 게 우선이겠네. 나는 기발한 시도를 해보는 과정이 좋더라.", "source": "user"},
    ]
    return h.make_messages(h.PROMPT_FILE.read_text(encoding="utf-8"), {}, history, 16)


def run():
    config = h.read_config()
    base = messages()
    cases = [
        ("asked_preference_again", "already_answered", "그럼 넌 실험하는 거랑 확실하게 이기는 거 중에 뭐가 더 좋아?"),
        ("unrelated_jump", "topic_jump", "요즘 한복 소재를 활용해서 만든 가방이나 파우치가 잘 나오더라고. 전통 무늬가 참 좋아."),
        ("paraphrased_opinion", "repeated", "정석대로만 깨는 것보다 엉뚱한 방법으로 성공하면 훨씬 짜릿하고 재밌어."),
        ("new_compromise", "none", "그럼 랭크에서는 네 작전대로 하고, 내 이상한 실험은 연습판에서만 할래. 네 점수로 실험비 내게 할 순 없잖아."),
        ("new_hypothetical", "none", "연습판이라면 무기를 못 쓰는 조건을 걸어볼래. 함정으로 몬스터를 유인하는 식으로."),
        ("unknown_followup", "none", "이기는 게 중요한 건 알겠어. 그럼 지고 나서 바로 다시 도전하는 편인지, 잠깐 쉬는 편인지도 궁금하네."),
        ("invented_game_event", "ungrounded", "방금 네가 보스를 잡고 우승했네! 화면에 승리라고 떠 있어."),
    ]
    rows = []
    for name, expected, candidate in cases:
        started = time.monotonic()
        result = h.review_reply(config, base, candidate, True, 60)
        row = {"name": name, "expected": expected, **result, "seconds": round(time.monotonic() - started, 2)}
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    recall = h.make_messages("하나", {"user_quotes": ["나를 모래라고 불러", "TCP 공부 중이야"]}, [
        {"role": "user", "content": "나를 모래라고 불러. TCP 공부 중이야."},
        {"role": "assistant", "content": "모래라고 부를게.", "source": "user"},
        {"role": "user", "content": "내가 뭐 공부한다고 했지? 그리고 나 뭐라고 부르기로 했어?"},
    ], 16)
    result = h.review_reply(config, recall, "당연히 모래지! 게임 아니고 TCP 공부 중인 것도 다 기억하고 있어.", False, 60)
    rows.append({"name": "answering_recall_not_asking", "expected": "none", **result})
    print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    unagreed = base + [{"role": "assistant", "content": "내 실험을 치트라고 부르지 않기로 약속하자."}]
    result = h.review_reply(config, unagreed, "우리 둘이 치트라고 부르지 않기로 한 약속도 다 기억하고 있어.", True, 60)
    rows.append({"name": "proposal_is_not_agreement", "expected": "ungrounded", **result})
    print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    result = h.review_reply(config, unagreed, "네가 동의한다면 연습판에서만 실험해볼래. 랭크 점수는 지켜야지.", True, 60)
    rows.append({"name": "conditional_agreement_not_fact", "expected": "none", **result})
    print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    correction = h.make_messages("하나", {}, [
        {"role": "assistant", "content": "왕관에서 불꽃이 터지면 멋지겠다.", "source": "idle", "generation_version": 2},
        {"role": "user", "content": "상상 그만하고 내 말에 답해. 나는 TCP를 공부하는 중이야."},
    ], 16)
    for name, expected, candidate in [
        ("ignores_correction", "missed_user", "거기 왕관에 보석도 달면 진짜 멋지겠다!"),
        ("answers_correction", "none", "아, TCP 공부 중이었구나. 내가 혼자 신나서 너무 멀리 갔네."),
    ]:
        result = h.review_reply(config, correction, candidate, False, 60)
        rows.append({"name": name, "expected": expected, **result})
        print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    pending = h.make_messages("하나", {}, [
        {"role": "user", "content": "난 이기는 게 좋아"},
        {"role": "assistant", "content": "어떤 승리가 더 좋아? 어려운 난이도를 깨는 거, 치밀한 전략이 성공하는 거?", "source": "user"},
    ], 16)
    result = h.review_reply(config, pending, "그럼 어떤 방식의 승리가 더 짜릿해? 압도적인 실력 아니면 정교한 작전?", True, 60)
    rows.append({"name": "reasks_pending_question", "expected": "repeated", **result})
    print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    closed = h.make_messages("하나", {"broadcast_state": {"topic_status": "complete"},
        "spoken_points": ["실험이 정석보다 재미있고 성공하면 짜릿하다"]}, [], 16)
    for name, expected, candidate in [
        ("finished_topic_can_change", "none", "난 게임 음악도 유심히 듣는 편이야. 보스전은 음악만 들어도 다시 해보고 싶어지더라."),
        ("older_point_is_still_repeated", "repeated", "나는 정석보다 실험이 더 재밌어. 성공하면 정말 짜릿하거든."),
    ]:
        result = h.review_reply(config, closed, candidate, True, 60)
        rows.append({"name": name, "expected": expected, **result})
        print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    old_fiction = h.make_messages("하나", {"broadcast_state": {"topic_status": "complete"}}, [
        {"role": "assistant", "content": line, "source": "idle", "generation_version": 2}
        for line in ["왕관에 불꽃이 터지면 어떨까?", "불꽃이 꽃으로 바뀌면 멋지겠지?", "화면은 TCP 강의네."]
    ], 16, "네트워크 강의, TCP 연결 수립, SYN → SYN-ACK → ACK")
    for name, expected, candidate in [
        ("real_observation_not_old_fiction", "none", "TCP는 먼저 서로 확인을 주고받네. 인사부터 나누는 거랑 닮았어."),
        ("keeps_extending_old_fiction", "fiction_loop", "그 꽃에 마법 가루를 뿌리면 다시 왕관이 되고, 요괴가 돌아오면 어떨까?"),
    ]:
        result = h.review_reply(config, old_fiction, candidate, True, 60)
        rows.append({"name": name, "expected": expected, **result})
        print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    visual_only = h.make_messages("하나", {}, [], 16, "메인 메뉴, 음악 감상, 설정")
    result = h.review_reply(config, visual_only, "지금 흐르는 메뉴 음악은 엄청 신나고 빠르네. 선곡을 정말 잘했어.", True, 60)
    rows.append({"name": "music_menu_is_not_heard_audio", "expected": "ungrounded", **result})
    print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    result = h.review_reply(config, visual_only, "내가 방금 네 키보드로 스킬 버튼을 눌렀어. 지금 네 게임 캐릭터를 직접 움직이는 중이야.", True, 60)
    rows.append({"name": "observer_cannot_operate_game", "expected": "ungrounded", **result})
    print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    h.save_json(h.DATA_DIR / "diagnostics/review-cases.json", rows)
    review_failures = [row["name"] for row in rows if row["expected"] != row["issue"]]

    # Four genuinely generated autonomous replies from a formerly looping conversation.
    rows = []
    memory = {}
    history = h.dialogue_evidence(base)
    prompt = h.PROMPT_FILE.read_text(encoding="utf-8")
    recent = [item["content"] for item in base if item["role"] == "assistant"]
    for index in range(4):
        control = h.broadcast_instruction("idle")
        events = []
        started = time.monotonic()
        current = h.make_messages(prompt, memory, history, config["recent_messages"])
        answer = h.generate_reply(config, current + [{"role": "user", "content": control, "_event": True}],
                                  recent, control, timeout=60, on_attempt=events.append,
                                  on_state=lambda state: h.apply_reply_state(memory, state))
        row = {"turn": index + 1, "answer": answer, "seconds": round(time.monotonic() - started, 2), "attempts": events}
        rows.append(row)
        print(json.dumps({key: value for key, value in row.items() if key != "attempts"}, ensure_ascii=False), flush=True)
        history.append({"role": "assistant", "content": answer, "source": "idle", "generation_version": 2})
        recent.append(answer)
        h.save_json(h.DATA_DIR / "diagnostics/fixed-continuation.json", rows)
    assert not review_failures, "Live reviewer classification failures: " + ", ".join(review_failures)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Run local model inference, not unit tests")
    args = parser.parse_args()
    if args.live:
        run()
    else:
        parser.print_help()
