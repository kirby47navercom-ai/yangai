# Maple 로컬 대화 동료

Qwen3 + Ollama + Piper로 동작하는 저지연 텍스트·음성 대화 프로그램이야. 캐릭터는 대한민국 모에화 버튜버 하나야.

## 처음 한 번

`setup_maple.bat`을 더블클릭해. Qwen 모델과 한국어 Piper 음성을 내려받아.

Piper는 Maple 프로세스 안에서 직접 실행돼. 별도 음성 서버나 `D:` 드라이브 매핑은 사용하지 않아.

그 다음 `start_maple.bat`을 실행하면 돼.

## 명령어

- `/remember 내용` — 오래 기억할 사실 저장
- `/memory` — 저장된 기억 확인
- `/voice on` / `/voice off` — 음성 켜기·끄기
- `/listen` — 마이크로 한 번 듣고 대화하기
- `/watch on` / `/watch off` — 기본 모니터의 게임 화면 관찰 켜기·끄기
- `/clear-memory` — 장기 기억과 대화 기록 삭제
- `/exit` — 종료

대화 기록은 `data/history.jsonl`, 장기 기억은 `data/memory.json`에 저장돼. 8번 대화마다 오래된 대화를 짧게 요약해 기억에 보태고, 최근 대화는 즉시 문맥에 넣어.

캐릭터와 관계 설정은 `hana_prompt.txt`, 속도와 모델은 `config.json`에서 바꿀 수 있어. 답변 기능보다 버튜버 캐릭터 대화가 먼저 오도록 프롬프트를 구성해뒀어. 화면 관찰은 `qwen2.5vl:3b`, 음성 인식은 `faster-whisper`를 사용해.

기본 모델은 최신 발화의 의미와 캐릭터 맥락을 함께 읽도록 `qwen3:8b`로 맞춰뒀어. 답변은 정해진 문장을 고르는 방식이 아니라 매번 Ollama 모델이 현재 대화에서 새로 생성해. 속도가 더 중요하면 `config.json`을 더 작은 Qwen 모델로 바꿀 수 있지만, 캐릭터성과 문맥 유지력은 떨어질 수 있어.
