# Maple 로컬 대화 동료

Qwen3 + Ollama + Piper로 동작하는 저지연 텍스트·음성 대화 프로그램이야.

## 처음 한 번

`setup_maple.bat`을 더블클릭해. Qwen 모델과 한국어 Piper 음성을 내려받아.

Piper는 Maple 프로세스 안에서 직접 실행돼. 별도 음성 서버나 `D:` 드라이브 매핑은 사용하지 않아.

그 다음 `start_maple.bat`을 실행하면 돼.

## 명령어

- `/remember 내용` — 오래 기억할 사실 저장
- `/memory` — 저장된 기억 확인
- `/voice on` / `/voice off` — 음성 켜기·끄기
- `/clear-memory` — 장기 기억과 대화 기록 삭제
- `/exit` — 종료

대화 기록은 `data/history.jsonl`, 장기 기억은 `data/memory.json`에 저장돼. 8번 대화마다 오래된 대화를 짧게 요약해 기억에 보태고, 최근 대화는 즉시 문맥에 넣어.

캐릭터와 관계 설정은 `character_prompt.txt`, 속도와 모델은 `config.json`에서 바꿀 수 있어. 답변 기능보다 캐릭터 대화가 먼저 오도록 프롬프트를 구성해뒀어.

기본 모델은 캐릭터성을 위해 `qwen3:4b`로 맞춰뒀어. 더 빠른 응답이 우선이면 `config.json`의 모델을 `qwen3:1.7b`로 바꿀 수 있지만, 말투와 관계 유지력은 4B 쪽이 좋아.
