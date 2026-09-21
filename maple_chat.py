from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CONFIG_FILE = ROOT / "config.json"
PROMPT_FILE = ROOT / "character_prompt.txt"
MEMORY_FILE = DATA_DIR / "memory.json"
HISTORY_FILE = DATA_DIR / "history.jsonl"


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def save_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def append_jsonl(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")


def load_history() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    history = []
    try:
        with HISTORY_FILE.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                    if item.get("role") in {"user", "assistant"} and item.get("content"):
                        history.append(item)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return history


def request_json(url: str, payload: dict | None = None, timeout: float = 30) -> dict:
    if payload is None:
        request = Request(url, method="GET")
    else:
        request = Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def read_config() -> dict:
    config = load_json(CONFIG_FILE, {})
    defaults = {
        "model": "qwen3:1.7b",
        "ollama_url": "http://127.0.0.1:11434",
        "piper_model": "voices/ko_KR-kss-medium.onnx",
        "piper_espeak_data": "%USERPROFILE%\\maple_espeak",
        "tts_enabled": True,
        "tts_length_scale": 0.9,
        "num_ctx": 4096,
        "num_predict": 384,
        "temperature": 0.72,
        "top_p": 0.9,
        "keep_alive": "10m",
        "recent_messages": 16,
        "summary_every_user_turns": 8,
        "auto_memory": True,
    }
    defaults.update(config)
    return defaults


def clean_for_speech(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[#*_>~-]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class SentenceBuffer:
    def __init__(self) -> None:
        self.buffer = ""

    def feed(self, text: str) -> list[str]:
        self.buffer += text
        output = []
        while True:
            match = re.search(r"(.+?[。！？!?])\s*", self.buffer, flags=re.S)
            if not match:
                break
            sentence = match.group(1).strip()
            self.buffer = self.buffer[match.end():]
            if sentence:
                output.append(sentence)
        if len(self.buffer) > 140:
            split_at = max(self.buffer.rfind(" ", 0, 140), self.buffer.rfind("\n", 0, 140))
            if split_at > 20:
                output.append(self.buffer[:split_at].strip())
                self.buffer = self.buffer[split_at:].lstrip()
        return output

    def flush(self) -> list[str]:
        text = self.buffer.strip()
        self.buffer = ""
        return [text] if text else []


class TTSWorker:
    def __init__(self, model_path: Path, data_dir: Path, length_scale: float, espeak_data: Path) -> None:
        os.environ["ESPEAK_DATA_PATH"] = str(espeak_data)
        try:
            from piper import PiperVoice
        except ImportError as error:
            raise RuntimeError("Piper 패키지를 찾을 수 없어") from error

        self.voice = PiperVoice.load(str(model_path))
        self.data_dir = data_dir
        self.length_scale = length_scale
        self.items: queue.Queue[str | None] = queue.Queue()
        self.enabled = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def submit(self, text: str) -> None:
        text = clean_for_speech(text)
        if self.enabled and len(text) >= 2:
            self.items.put(text)

    def close(self) -> None:
        self.items.put(None)
        self.thread.join(timeout=2)

    def _run(self) -> None:
        while True:
            text = self.items.get()
            if text is None:
                return
            try:
                self._speak(text)
            except Exception as error:  # TTS failure must not kill the chat.
                self.enabled = False
                print(f"\n[TTS가 꺼졌어: {error}]", flush=True)

    def _speak(self, text: str) -> None:
        with tempfile.NamedTemporaryFile(prefix="maple_", suffix=".wav", dir=self.data_dir, delete=False) as file:
            audio_path = Path(file.name)

        player = shutil.which("ffplay")
        if not player:
            audio_path.unlink(missing_ok=True)
            raise RuntimeError("ffplay를 찾을 수 없어")
        try:
            from piper import SynthesisConfig

            with wave.open(str(audio_path), "wb") as wav_file:
                self.voice.synthesize_wav(
                    text,
                    wav_file,
                    SynthesisConfig(length_scale=self.length_scale),
                )
            subprocess.run(
                [player, "-nodisp", "-autoexit", "-loglevel", "quiet", str(audio_path)],
                check=False,
                timeout=60,
            )
        finally:
            audio_path.unlink(missing_ok=True)


def build_system_prompt(prompt: str, memory: dict) -> str:
    facts = memory.get("facts", [])
    facts_text = "\n".join(f"- {fact}" for fact in facts) or "- 아직 저장된 사실이 없어."
    summary = memory.get("summary", "") or "아직 장기 요약이 없어."
    return (
        prompt.strip()
        + "\n\n[장기 기억]\n"
        + summary
        + "\n\n[사용자에 대해 기억하는 사실]\n"
        + facts_text
        + "\n\n기억은 참고용이야. 현재 사용자의 말과 충돌하면 현재 말을 우선해."
        + "\n\n[이번 응답의 최우선 규칙]"
        + "\n- 반드시 자연스러운 한국어 반말로만 답해. 문장 끝은 ~야, ~지, ~어, ~까?를 사용해."
        + "\n- ~요, ~습니다, ~세요, ~하신가요, ~드릴게요와 고객센터식 표현을 절대 사용하지 마."
        + "\n- 이모지와 형식적인 자기소개를 쓰지 마. 대답 첫 문장부터 반디의 감정과 관계가 느껴지게 해."
        + "\n- 가벼운 대화는 1~3개의 자연스러운 문장으로 답하고, 모든 답을 목록이나 해결책으로 만들지 마."
    )


def make_messages(prompt: str, memory: dict, history: list[dict], recent_count: int) -> list[dict]:
    messages = [{"role": "system", "content": build_system_prompt(prompt, memory)}]
    messages.extend({"role": item["role"], "content": item["content"]} for item in history[-recent_count:])
    return messages


def stream_chat(config: dict, messages: list[dict]):
    payload = {
        "model": config["model"],
        "messages": messages,
        "stream": True,
        "think": False,
        "keep_alive": config["keep_alive"],
        "options": {
            "num_ctx": config["num_ctx"],
            "num_predict": config["num_predict"],
            "temperature": config["temperature"],
            "top_p": config["top_p"],
        },
    }
    request = Request(
        config["ollama_url"].rstrip("/") + "/api/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        response = urlopen(request, timeout=180)
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama 오류 {error.code}: {detail[:300]}") from error
    except URLError as error:
        raise RuntimeError("Ollama가 실행 중이 아니야. 먼저 Ollama를 켜줘.") from error

    with response:
        for raw_line in response:
            if not raw_line.strip():
                continue
            item = json.loads(raw_line.decode("utf-8"))
            piece = item.get("message", {}).get("content", "")
            if piece:
                yield piece
            if item.get("done"):
                break


def one_shot(config: dict, messages: list[dict]) -> str:
    payload = {
        "model": config["model"],
        "messages": messages,
        "stream": False,
        "think": False,
        "keep_alive": config["keep_alive"],
        "options": {"num_ctx": config["num_ctx"], "num_predict": 256, "temperature": 0.2},
    }
    result = request_json(config["ollama_url"].rstrip("/") + "/api/chat", payload, timeout=180)
    return result.get("message", {}).get("content", "").strip()


memory_lock = threading.Lock()


def compact_memory(config: dict, memory: dict, history: list[dict]) -> None:
    if not memory_lock.acquire(blocking=False):
        return
    try:
        transcript = "\n".join(f"{x['role']}: {x['content']}" for x in history[-40:])
        messages = [
            {
                "role": "system",
                "content": "대화에서 앞으로 유용한 사용자 취향, 사실, 진행 중인 일만 한국어로 5줄 이내 요약해. 추측하거나 감정적인 평가는 넣지 마.",
            },
            {"role": "user", "content": transcript},
        ]
        summary = one_shot(config, messages)
        if summary:
            memory["summary"] = summary[:4000]
            memory["updated_at"] = now()
            save_json(MEMORY_FILE, memory)
    except Exception:
        pass
    finally:
        memory_lock.release()


def start_memory_compaction(config: dict, memory: dict, history: list[dict]) -> None:
    threading.Thread(target=compact_memory, args=(config, memory, history.copy()), daemon=True).start()


def print_help() -> None:
    print("\n명령어")
    print("  /remember 내용   장기 기억에 저장")
    print("  /memory          저장된 기억 보기")
    print("  /voice on|off    음성 켜기/끄기")
    print("  /clear-memory    장기 기억과 대화 기록 지우기")
    print("  /exit            종료\n")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    config = read_config()
    prompt = PROMPT_FILE.read_text(encoding="utf-8") if PROMPT_FILE.exists() else "너는 친절한 코딩 동료야."
    memory = load_json(MEMORY_FILE, {"summary": "", "facts": [], "updated_at": ""})
    history = load_history()

    try:
        request_json(config["ollama_url"].rstrip("/") + "/api/tags", timeout=2)
    except Exception:
        print("Ollama가 켜져 있지 않아. Ollama를 실행한 뒤 다시 시작해줘.")
        return

    try:
        models = request_json(config["ollama_url"].rstrip("/") + "/api/tags", timeout=2).get("models", [])
        names = {item.get("name") for item in models}
        if config["model"] not in names:
            print(f"모델 {config['model']}이 없어. setup_maple.ps1을 한 번 실행해줘.")
            return
    except Exception as error:
        print(f"Ollama 모델 확인 실패: {error}")
        return

    tts = None
    piper_model = ROOT / config.get("piper_model", "voices/ko_KR-kss-medium.onnx")
    piper_espeak_data = Path(os.path.expandvars(config.get("piper_espeak_data", "%USERPROFILE%\\maple_espeak")))
    if config.get("tts_enabled") and piper_model.exists() and piper_espeak_data.exists():
        try:
            tts = TTSWorker(piper_model, DATA_DIR, float(config["tts_length_scale"]), piper_espeak_data)
            print("Maple 음성: Piper 준비됨")
        except Exception as error:
            print(f"Maple 음성: 꺼짐 ({error})")
    else:
        print("Maple 음성: 꺼짐 (텍스트 채팅은 바로 사용할 수 있어)")

    print(f"Maple 시작, 모델: {config['model']}")
    print("/help를 입력하면 명령어를 볼 수 있어.\n")

    user_turns = sum(1 for item in history if item["role"] == "user")
    try:
        while True:
            try:
                user_text = input("나 > ").strip()
            except EOFError:
                break
            user_text = user_text.encode("utf-8", errors="replace").decode("utf-8")
            if not user_text:
                continue
            if user_text == "/exit":
                break
            if user_text == "/help":
                print_help()
                continue
            if user_text == "/memory":
                print("\n[요약]\n" + (memory.get("summary") or "없음"))
                print("\n[사실]")
                print("\n".join(f"- {x}" for x in memory.get("facts", [])) or "없음")
                print()
                continue
            if user_text.startswith("/remember "):
                fact = user_text.removeprefix("/remember ").strip()
                if fact and fact not in memory.setdefault("facts", []):
                    memory["facts"].append(fact)
                    memory["updated_at"] = now()
                    save_json(MEMORY_FILE, memory)
                    print("기억해둘게.\n")
                continue
            if user_text == "/clear-memory":
                memory = {"summary": "", "facts": [], "updated_at": now()}
                save_json(MEMORY_FILE, memory)
                HISTORY_FILE.unlink(missing_ok=True)
                history = []
                print("장기 기억과 대화 기록을 지웠어.\n")
                continue
            if user_text.startswith("/voice "):
                value = user_text.split(maxsplit=1)[1].lower()
                if tts is None:
                    print("Piper 음성이 준비되지 않았어. setup_maple.ps1을 한 번 실행해줘.\n")
                else:
                    tts.enabled = value == "on"
                    print(f"음성: {'켜짐' if tts.enabled else '꺼짐'}\n")
                continue

            append_jsonl(HISTORY_FILE, {"role": "user", "content": user_text, "created_at": now()})
            history.append({"role": "user", "content": user_text, "created_at": now()})
            messages = make_messages(prompt, memory, history, int(config["recent_messages"]))
            print("반디 > ", end="", flush=True)
            full_answer = ""
            sentences = SentenceBuffer()
            try:
                for piece in stream_chat(config, messages):
                    print(piece, end="", flush=True)
                    full_answer += piece
                    if tts:
                        for sentence in sentences.feed(piece):
                            tts.submit(sentence)
                if tts:
                    for sentence in sentences.flush():
                        tts.submit(sentence)
                print("\n")
            except Exception as error:
                print(f"\n[응답 실패: {error}]\n")
                continue

            append_jsonl(HISTORY_FILE, {"role": "assistant", "content": full_answer, "created_at": now()})
            history.append({"role": "assistant", "content": full_answer, "created_at": now()})
            user_turns += 1
            interval = int(config["summary_every_user_turns"])
            if config.get("auto_memory") and interval > 0 and user_turns % interval == 0:
                start_memory_compaction(config, memory, history)
    except KeyboardInterrupt:
        print("\n종료할게.")
    finally:
        if tts:
            tts.close()


if __name__ == "__main__":
    main()
