from __future__ import annotations

import queue
import re
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import scrolledtext

from hana_chat import (
    CONFIG_FILE,
    DATA_DIR,
    MEMORY_FILE,
    PROMPT_FILE,
    ROOT,
    ScreenContext,
    ScreenWatcher,
    SentenceBuffer,
    SpeechRecognizer,
    GPTSoVITSTTSWorker,
    TTSWorker,
    append_jsonl,
    default_memory,
    ensure_ollama,
    load_history,
    load_latest_session_history,
    load_json,
    list_visible_windows,
    make_messages,
    new_session_file,
    now,
    read_config,
    request_json,
    save_json,
    save_memory_snapshot,
    sanitize_model_answer,
    is_repetitive_answer,
    start_memory_compaction,
    stream_chat,
    stop_ollama,
)


class MicLoop:
    def __init__(self, recognizer: SpeechRecognizer, tts, on_text, on_error, config: dict) -> None:
        self.recognizer = recognizer
        self.tts = tts
        self.on_text = on_text
        self.on_error = on_error
        self.threshold = float(config.get("mic_threshold", 0.015))
        self.chunk_seconds = float(config.get("mic_chunk_seconds", 0.5))
        self.silence_seconds = float(config.get("mic_silence_seconds", 1.0))
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=0.6)
        self.thread = None

    def running(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    def _run(self) -> None:
        try:
            import numpy as np
            import sounddevice as sd

            sample_rate = 16_000
            chunk_size = int(sample_rate * self.chunk_seconds)
            silence_chunks = max(1, int(self.silence_seconds / self.chunk_seconds))
            self.recognizer._load()
            frames = []
            silence_count = 0
            speaking = False
            while not self.stop_event.is_set():
                if self.tts and self.tts.speaking.is_set():
                    time.sleep(0.15)
                    continue
                audio = sd.rec(chunk_size, samplerate=sample_rate, channels=1, dtype="float32")
                sd.wait()
                samples = audio[:, 0]
                energy = float(np.sqrt(np.mean(np.square(samples))))
                if energy >= self.threshold:
                    frames.append(samples)
                    speaking = True
                    silence_count = 0
                    continue
                if not speaking:
                    continue
                frames.append(samples)
                silence_count += 1
                if silence_count < silence_chunks:
                    continue
                clip = np.concatenate(frames)
                frames = []
                silence_count = 0
                speaking = False
                text = self.recognizer.transcribe_audio(clip)
                if text and not self.stop_event.is_set():
                    self.on_text(text)
        except Exception as error:
            self.on_error(str(error))


class HanaApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("하나")
        self.root.geometry("1050x720")
        self.root.minsize(820, 560)
        self.root.configure(bg="#111827")
        self.config = read_config()
        self.ollama_process = None
        self.ollama_error = ""
        try:
            self.ollama_process = ensure_ollama(self.config)
        except Exception as error:
            self.ollama_error = f"Ollama 자동 시작 실패: {error}"
        self.prompt = PROMPT_FILE.read_text(encoding="utf-8") if PROMPT_FILE.exists() else "너는 하나야."
        self.memory = load_json(MEMORY_FILE, default_memory())
        self.history_file = new_session_file()
        self.history = load_history(self.history_file)
        if not self.history and self.memory.get("recent_conversation"):
            self.history = [
                dict(item)
                for item in self.memory["recent_conversation"][-12:]
                if isinstance(item, dict) and item.get("role") in {"user", "assistant"} and item.get("content")
            ]
        if not self.memory.get("recent_conversation") and not self.history:
            previous_history = load_latest_session_history(self.history_file)
            if previous_history:
                save_memory_snapshot(self.memory, previous_history)
        self.user_turns = sum(1 for item in self.history if item["role"] == "user")
        self.stop_event = threading.Event()
        self.chat_busy = threading.Event()
        self.chat_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.runtime_log = DATA_DIR / "hana_runtime.jsonl"
        self.last_user_activity_at = time.monotonic()
        self.last_response_at = time.monotonic()
        self.last_auto_requested_at = self.last_response_at
        self.last_idle_requested_at = 0.0
        self.idle_scene_attempts = 0
        self.recent_auto_answers: list[str] = [
            str(item["content"])
            for item in self.history
            if item.get("role") == "assistant" and item.get("content")
        ][-6:]
        self.screen_context = ScreenContext()
        self.tts = self._create_tts()
        self.tts_status = ""
        self.recognizer = SpeechRecognizer(self.config)
        self.mic = MicLoop(self.recognizer, self.tts, self._on_mic_text, self._on_mic_error, self.config)
        self.watcher = ScreenWatcher(
            self.config,
            self.screen_context,
            self._on_screen_observation,
            self._on_screen_error,
            lambda: self.chat_busy.is_set() or not self.chat_queue.empty(),
        )
        self._build_ui()
        if self.ollama_error:
            self.root.after(0, lambda message=self.ollama_error: self._system(message))
        if self.tts and hasattr(self.tts, "set_status_callback"):
            self.tts.set_status_callback(self._post_tts_status)
        if self.tts and hasattr(self.tts, "prewarm"):
            self.tts_status = "음성 모델 로딩 중..."
            self.tts.prewarm(self._post_tts_status)
        self.chat_thread = threading.Thread(target=self._chat_loop, daemon=True)
        self.chat_thread.start()
        self.idle_thread = threading.Thread(target=self._idle_loop, daemon=True)
        self.idle_thread.start()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(200, self._start_services)

    def _create_tts(self):
        if not self.config.get("tts_enabled"):
            return None
        if self.config.get("tts_engine") == "gpt_sovits":
            try:
                return GPTSoVITSTTSWorker(self.config, DATA_DIR)
            except Exception as error:
                print(f"하나 음성: GPT-SoVITS 준비 실패 ({error})")
        model = ROOT / self.config.get("piper_model", "voices/ko_KR-kss-medium.onnx")
        espeak = Path(self.config.get("piper_espeak_data", "").replace("%USERPROFILE%", str(Path.home())))
        if not model.exists() or not espeak.exists():
            return None
        try:
            return TTSWorker(model, DATA_DIR, float(self.config["tts_length_scale"]), espeak)
        except Exception:
            return None

    def _build_ui(self) -> None:
        self.avatar_frame = tk.Frame(self.root, bg="#172033", width=300)
        self.avatar_frame.pack(side="left", fill="y")
        self.avatar_frame.pack_propagate(False)
        self._load_avatar()

        main = tk.Frame(self.root, bg="#111827")
        main.pack(side="right", fill="both", expand=True)

        header = tk.Frame(main, bg="#111827")
        header.pack(fill="x", padx=18, pady=(14, 8))
        tk.Label(header, text="하나", fg="#f8fafc", bg="#111827", font=("맑은 고딕", 20, "bold")).pack(side="left")
        self.status = tk.Label(header, text="준비 중...", fg="#93c5fd", bg="#111827", font=("맑은 고딕", 10))
        self.status.pack(side="left", padx=14)

        self.chat = scrolledtext.ScrolledText(
            main,
            wrap="word",
            state="disabled",
            bg="#0b1220",
            fg="#e5e7eb",
            insertbackground="#f8fafc",
            font=("맑은 고딕", 12),
            padx=14,
            pady=14,
        )
        self.chat.pack(fill="both", expand=True, padx=18, pady=(0, 10))
        self.chat.tag_configure("user", foreground="#93c5fd", spacing1=8)
        self.chat.tag_configure("hana", foreground="#f9a8d4", spacing1=8)
        self.chat.tag_configure("system", foreground="#94a3b8", spacing1=5)

        controls = tk.Frame(main, bg="#111827")
        controls.pack(fill="x", padx=18, pady=(0, 8))
        self.entry = tk.Entry(controls, bg="#1f2937", fg="#f8fafc", insertbackground="#f8fafc", font=("맑은 고딕", 12))
        self.entry.pack(side="left", fill="x", expand=True, ipady=8)
        self.entry.bind("<Return>", lambda _event: self._send_text())
        tk.Button(controls, text="보내기", command=self._send_text, bg="#2563eb", fg="white", relief="flat", padx=16).pack(side="left", padx=(8, 0))

        buttons = tk.Frame(main, bg="#111827")
        buttons.pack(fill="x", padx=18, pady=(0, 14))
        self.mic_button = tk.Button(buttons, command=self._toggle_mic, relief="flat", padx=10)
        self.mic_button.pack(side="left")
        self.watch_button = tk.Button(buttons, command=self._toggle_watch, relief="flat", padx=10)
        self.watch_button.pack(side="left", padx=8)
        tk.Button(buttons, text="화면 설정", command=self._configure_screen, relief="flat", padx=10).pack(side="left", padx=(0, 8))
        self.voice_button = tk.Button(buttons, command=self._toggle_voice, relief="flat", padx=10)
        self.voice_button.pack(side="left")

    def _load_avatar(self) -> None:
        path = ROOT / "assets" / "hana_reference.jpg"
        try:
            from PIL import Image, ImageTk

            image = Image.open(path)
            image.thumbnail((280, 520))
            self.avatar_photo = ImageTk.PhotoImage(image)
            tk.Label(self.avatar_frame, image=self.avatar_photo, bg="#172033").pack(expand=True)
        except Exception:
            tk.Label(self.avatar_frame, text="하나", fg="#f9a8d4", bg="#172033", font=("맑은 고딕", 34, "bold")).pack(expand=True)

    def _start_services(self) -> None:
        if self.config.get("mic_enabled", True):
            self.mic.start()
        if self.config.get("screen_enabled", True) and self._has_model(self.config.get("vision_model")):
            self.watcher.start()
        self._update_buttons()
        self._system("하나가 방송을 시작했어. 마이크와 화면을 보고 있어.")

    def _has_model(self, model: str | None) -> bool:
        if not model:
            return False
        try:
            models = request_json(self.config["ollama_url"].rstrip("/") + "/api/tags", timeout=2).get("models", [])
            return model in {item.get("name") for item in models}
        except Exception:
            return False

    def _on_mic_text(self, text: str) -> None:
        self.root.after(0, lambda: self._queue_user(text, "음성"))

    def _on_mic_error(self, error: str) -> None:
        self.root.after(0, lambda: self._system(f"마이크를 사용할 수 없어: {error}"))

    def _on_screen_observation(self, observation: str) -> None:
        def handle() -> None:
            self.status.configure(text=f"화면 읽음: {observation[:32]}")
            self.idle_scene_attempts = 0
            self.recent_auto_answers.clear()
            if not self.config.get("screen_proactive", True):
                return
            if self.chat_busy.is_set() or not self.chat_queue.empty() or self._tts_busy():
                return
            self.chat_queue.put(("screen", observation))

        self.root.after(0, handle)

    def _on_screen_error(self, error: str) -> None:
        self.root.after(0, lambda: self._system(f"화면을 읽을 수 없어: {error or '알 수 없는 오류'}"))

    def _on_tts_status(self, message: str) -> None:
        self.tts_status = message
        if message:
            self.status.configure(text=message)

    def _post_tts_status(self, message: str) -> None:
        if not self.stop_event.is_set():
            self.root.after(0, lambda: self._on_tts_status(message))

    def _runtime_log(self, message: str) -> None:
        try:
            append_jsonl(self.runtime_log, {"message": message, "created_at": now()})
        except OSError:
            pass

    def _idle_loop(self) -> None:
        delay = max(1.0, float(self.config.get("talk_after_speech_seconds", 3)))
        max_scene_attempts = max(1, int(self.config.get("max_idle_comments_per_scene", 3)))
        while not self.stop_event.wait(1.0):
            try:
                if not self.config.get("idle_talk_enabled", True):
                    continue
                if self.chat_busy.is_set():
                    continue
                if not self.chat_queue.empty():
                    continue
                if self._tts_busy():
                    continue
                if self.watcher.running() and not self.screen_context.read():
                    continue
                if self.idle_scene_attempts >= max_scene_attempts:
                    continue
                reference = max(self.last_response_at, self.last_auto_requested_at)
                if self.tts and self.tts.enabled:
                    reference = max(reference, self.tts.last_finished_at)
                requested_at = time.monotonic()
                if requested_at - reference < delay:
                    continue
                self.last_auto_requested_at = requested_at
                self.last_idle_requested_at = requested_at
                self.idle_scene_attempts += 1
                self._runtime_log("idle request queued")
                self.chat_queue.put(("idle", ""))
            except Exception as error:
                self._runtime_log(f"idle loop recovered: {type(error).__name__}: {error}")
                self.stop_event.wait(1.0)

    def _tts_busy(self) -> bool:
        return bool(self.tts and (self.tts.speaking.is_set() or not self.tts.items.empty()))

    def _queue_user(self, text: str, source: str = "입력") -> None:
        text = text.strip()
        if not text:
            return
        self.last_user_activity_at = time.monotonic()
        self.idle_scene_attempts = 0
        self.recent_auto_answers.clear()
        self._line("너", text, "user")
        self.chat_queue.put(("user", text))

    def _send_text(self) -> None:
        text = self.entry.get().strip()
        self.entry.delete(0, tk.END)
        self._queue_user(text)

    def _chat_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                kind, payload = self.chat_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self.chat_busy.set()
                self.watcher.wait_for_request(float(self.config.get("vision_response_timeout", 30)) + 1)
                if kind == "user":
                    self._answer_user(payload)
                elif kind == "screen":
                    if not self.chat_queue.empty():
                        continue
                    self._answer_screen(payload)
                else:
                    self._answer_idle()
            except Exception as error:
                self._runtime_log(f"chat loop error: {type(error).__name__}: {error}")
                self.root.after(0, lambda error=error: self._system(f"응답을 만들 수 없어: {error}"))
            finally:
                self.chat_busy.clear()

    def _answer_user(self, text: str) -> None:
        append_jsonl(self.history_file, {"role": "user", "content": text, "created_at": now()})
        self.history.append({"role": "user", "content": text, "created_at": now()})
        screen_context = self.screen_context.prompt()
        if self._is_screen_question(text):
            direct_observation = self.watcher.answer_question(text)
            if direct_observation:
                self.screen_context.update(direct_observation)
                screen_context = self.screen_context.prompt()
        messages = make_messages(self.prompt, self.memory, self.history, int(self.config["recent_messages"]), screen_context)
        self._stream_answer(messages, persist=True)
        self.user_turns += 1
        interval = int(self.config.get("summary_every_user_turns", 8))
        if self.config.get("auto_memory", True) and interval > 0 and self.user_turns % interval == 0:
            start_memory_compaction(self.config, self.memory, self.history)

    def _is_screen_question(self, text: str) -> bool:
        markers = ("화면", "보이", "보여", "뭐가", "공부", "읽어", "맞춰", "게임")
        return any(marker in text for marker in markers) and self.watcher.running()

    def _answer_screen(self, observation: str) -> None:
        messages = make_messages(self.prompt, self.memory, self.history, int(self.config["recent_messages"]), self.screen_context.prompt())
        messages.append(
            {
                "role": "user",
                "content": (
                    "너는 지금 실제 방송 중인 하나야. 방금 직접 확인한 화면 관찰 메모를 바탕으로, "
                    "보고서나 AI 답변이 아니라 방송에서 입 밖으로 나올 자연스러운 한두 문장을 바로 말해. "
                    "장면을 본 하나의 반응이나 감정을 먼저 보여주고, 확인된 사실 하나와 그에 따른 생각을 자연스럽게 이어. "
                    "관찰 메모에 '확실히 읽힌 글자'로 적히지 않은 텍스트는 화면에 있다고 말하지 마. 화면 관찰 메모에 없는 내용을 만들거나 화면 메모를 분석 보고서처럼 설명하지 말고, 이 요청 자체와 분석 과정·목록·마크다운은 출력하지 마. "
                    "최근 하나의 자동 발언과 같은 사실·감정·문장 구조를 되풀이하지 마. 새로 이어갈 내용이 없으면 [SILENT]만 출력해.\n\n"
                    + self._recent_auto_context()
                    + "\n\n"
                    + observation
                ),
            }
        )
        answer = self._stream_and_speak(
            messages,
            control_text=messages[-1]["content"],
            avoid_repetition=True,
            recent_answers=self.recent_auto_answers,
        )
        if not answer:
            return
        created_at = now()
        append_jsonl(self.history_file, {"role": "assistant", "content": answer, "created_at": created_at})
        self.history.append({"role": "assistant", "content": answer, "created_at": created_at})
        save_memory_snapshot(self.memory, self.history, self.screen_context.prompt())
        self.last_response_at = time.monotonic()

    def _answer_idle(self) -> None:
        if self.last_user_activity_at > self.last_idle_requested_at:
            return
        messages = make_messages(
            self.prompt,
            self.memory,
            self.history,
            int(self.config["recent_messages"]),
            self.screen_context.prompt(),
        )
        messages.append(
            {
                "role": "user",
                "content": (
                    "지금 보고 있는 장면과 방금까지의 대화에서 이어지는 생각 하나를 골라, 하나가 실제로 입 밖에 낼 자연스러운 한두 문장으로 말해. "
                    "화면을 보고서처럼 요약하지 말고, 먼저 하나의 반응이나 감정을 보여준 뒤 구체적인 장면 하나와 그 장면에서 떠오른 판단·기억·기대를 자연스럽게 이어. "
                    "이미 말한 사실을 다시 읽지 말고, 같은 장면이면 생각을 조금 발전시키고 의미 있는 변화가 없으면 억지로 새 사건을 만들지 마. "
                    "프로그램 내부의 처리 과정이나 이 요청 자체를 설명하지 말고, 사용자의 목적을 함부로 정하지 마. "
                    "질문을 꼭 피할 필요는 없지만 매번 질문으로 끝내지는 말고, 하나의 생각이 자연스럽게 끝나게 해. "
                    "최근 하나의 자동 발언과 같은 사실·감정·문장 구조를 되풀이하지 마. 새로 이어갈 내용이 없으면 [SILENT]만 출력해. "
                    "이 요청을 되풀이하거나 설명하지 말고, 실제 대사만 출력해.\n\n"
                    + self._recent_auto_context()
                ),
            }
        )
        answer = self._stream_and_speak(
            messages,
            control_text=messages[-1]["content"],
            avoid_repetition=True,
            recent_answers=self.recent_auto_answers,
            timeout=float(self.config.get("idle_response_timeout", 45)),
        )
        if not answer:
            self._runtime_log("idle response was empty")
            return
        self._runtime_log(f"idle response received: {len(answer)} chars")
        created_at = now()
        append_jsonl(self.history_file, {"role": "assistant", "content": answer, "created_at": created_at})
        self.history.append({"role": "assistant", "content": answer, "created_at": created_at})
        save_memory_snapshot(self.memory, self.history, self.screen_context.prompt())
        self.last_response_at = time.monotonic()

    def _stream_and_speak(
        self,
        messages: list[dict],
        num_predict: int | None = None,
        timeout: float = 180,
        control_text: str = "",
        avoid_repetition: bool = False,
        recent_answers: list[str] | None = None,
    ) -> str:
        full = "".join(stream_chat(self.config, messages, num_predict=num_predict, timeout=timeout))
        if control_text and re.search(r"(?:\[\s*SILENT\s*\]|<\s*SILENT\s*>|\bSILENT\b)", full, re.I):
            return ""
        answer = sanitize_model_answer(full, control_text=control_text)
        if answer and avoid_repetition and recent_answers and is_repetitive_answer(answer, recent_answers):
            answer = ""
        if not answer:
            self._runtime_log("discarded leaked or invalid model output")
            retry_messages = list(messages) + [
                {
                    "role": "user",
                    "content": "방금 출력은 직전 발언과 겹치거나 내부 지시문을 되풀이해서 버려졌어. 최근 발언의 내용과 표현을 반복하지 말고, 지금 화면에서 아직 말하지 않은 구체적인 생각만 한두 문장으로 말해. 정말 새로 이어갈 내용이 없으면 [SILENT]만 출력해.",
                }
            ]
            retry = "".join(stream_chat(self.config, retry_messages, num_predict=num_predict, timeout=timeout))
            if control_text and re.search(r"(?:\[\s*SILENT\s*\]|<\s*SILENT\s*>|\bSILENT\b)", retry, re.I):
                return ""
            answer = sanitize_model_answer(retry, control_text=control_text)
            if answer and avoid_repetition and recent_answers and is_repetitive_answer(answer, recent_answers):
                answer = ""
        if not answer:
            self._runtime_log("discarded second invalid model output")
            return ""

        self.root.after(0, lambda answer=answer: self._line("하나", answer, "hana"))
        sentence_buffer = SentenceBuffer()
        for sentence in sentence_buffer.feed(answer):
            self._speak(sentence)
        for sentence in sentence_buffer.flush():
            self._speak(sentence)
        if avoid_repetition:
            self.recent_auto_answers.append(answer)
            del self.recent_auto_answers[:-6]
        return answer

    def _recent_auto_context(self) -> str:
        if not self.recent_auto_answers:
            return "[최근 자동 발언]\n없음"
        lines = [f"- {answer}" for answer in self.recent_auto_answers[-5:]]
        return "[최근 자동 발언]\n" + "\n".join(lines)

    def _stream_answer(self, messages: list[dict], persist: bool) -> None:
        full = self._stream_and_speak(messages)
        self.last_response_at = time.monotonic()
        if persist and full.strip():
            answer = full.strip()
            append_jsonl(self.history_file, {"role": "assistant", "content": answer, "created_at": now()})
            self.history.append({"role": "assistant", "content": answer, "created_at": now()})
            save_memory_snapshot(self.memory, self.history, self.screen_context.prompt())

    def _speak(self, text: str) -> None:
        if self.tts:
            self.tts.submit(text)

    def _line(self, speaker: str, text: str, tag: str) -> None:
        self._start_line(speaker, tag)
        self._append_text(text)
        self._finish_line()

    def _start_line(self, speaker: str, tag: str) -> None:
        self.chat.configure(state="normal")
        self.chat.insert(tk.END, f"{speaker} > ", tag)
        self.chat.configure(state="disabled")
        self.chat.see(tk.END)

    def _append_text(self, text: str) -> None:
        self.chat.configure(state="normal")
        self.chat.insert(tk.END, text)
        self.chat.configure(state="disabled")
        self.chat.see(tk.END)

    def _finish_line(self) -> None:
        self._append_text("\n\n")

    def _system(self, text: str) -> None:
        self._line("상태", text, "system")

    def _toggle_mic(self) -> None:
        if self.mic.running():
            self.mic.stop()
        else:
            self.mic.start()
        self._update_buttons()

    def _toggle_watch(self) -> None:
        if self.watcher.running():
            self.watcher.stop()
            self.screen_context.update("")
        elif self._has_model(self.config.get("vision_model")):
            self.watcher.start()
        else:
            self._system(f"화면 모델 {self.config.get('vision_model')}이 없어.")
        self._update_buttons()

    def _configure_screen(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("화면 보기 설정")
        dialog.geometry("520x460")
        dialog.transient(self.root)
        dialog.grab_set()

        mode = tk.StringVar(value=self.config.get("screen_capture_mode", "screen"))
        tk.Label(dialog, text="하나가 볼 화면", font=("맑은 고딕", 12, "bold")).pack(anchor="w", padx=18, pady=(16, 8))
        tk.Radiobutton(dialog, text="전체 화면", variable=mode, value="screen").pack(anchor="w", padx=18)
        tk.Radiobutton(dialog, text="열려 있는 창 하나", variable=mode, value="window").pack(anchor="w", padx=18)

        listbox = tk.Listbox(dialog, height=14, exportselection=False)
        listbox.pack(fill="both", expand=True, padx=18, pady=10)
        window_titles: list[str] = []

        def refresh() -> None:
            window_titles.clear()
            window_titles.extend(title for title, _bounds, _hwnd in list_visible_windows())
            listbox.delete(0, tk.END)
            for title in window_titles:
                listbox.insert(tk.END, title)
            selected = self.config.get("screen_window_title", "")
            if selected in window_titles:
                listbox.selection_set(window_titles.index(selected))
                listbox.see(window_titles.index(selected))

        def update_state(*_args) -> None:
            listbox.configure(state="normal" if mode.get() == "window" else "disabled")

        def apply() -> None:
            selected_title = self.config.get("screen_window_title", "")
            if mode.get() == "window":
                selection = listbox.curselection()
                if not selection:
                    self._system("볼 창을 하나 선택해줘.")
                    return
                selected_title = window_titles[selection[0]]
            else:
                selected_title = ""
            self.config["screen_capture_mode"] = mode.get()
            self.config["screen_window_title"] = selected_title
            self.watcher.set_capture_target(mode.get(), selected_title)
            save_json(CONFIG_FILE, self.config)
            self._system(
                "전체 화면을 볼게."
                if mode.get() == "screen"
                else f"이제 '{selected_title}' 창을 볼게. 창이 닫히면 바탕화면으로 전환할게."
            )
            self._update_buttons()
            dialog.destroy()

        mode.trace_add("write", update_state)
        refresh()
        update_state()
        footer = tk.Frame(dialog)
        footer.pack(fill="x", padx=18, pady=(0, 16))
        tk.Button(footer, text="목록 새로고침", command=refresh, relief="flat", padx=10).pack(side="left")
        tk.Button(footer, text="적용", command=apply, bg="#2563eb", fg="white", relief="flat", padx=18).pack(side="right")

    def _toggle_voice(self) -> None:
        if self.tts:
            self.tts.enabled = not self.tts.enabled
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.mic_button.configure(text=f"마이크 {'켜짐' if self.mic.running() else '꺼짐'}")
        if self.watcher.running():
            capture_label = "창" if self.config.get("screen_capture_mode") == "window" else "전체"
            self.watch_button.configure(text=f"화면({capture_label}) 켜짐")
        else:
            self.watch_button.configure(text="화면 꺼짐")
        self.voice_button.configure(text=f"음성 {'켜짐' if self.tts and self.tts.enabled else '꺼짐'}")
        parts = []
        if self.mic.running():
            parts.append("마이크")
        if self.watcher.running():
            parts.append("화면")
        if self.tts and self.tts.enabled:
            parts.append("음성")
        self.status.configure(text=self.tts_status or " · ".join(parts) or "대기 중")
        if not self.stop_event.is_set():
            self.root.after(1000, self._update_buttons)

    def close(self) -> None:
        if self.stop_event.is_set():
            return
        save_memory_snapshot(self.memory, self.history, self.screen_context.prompt())
        self.stop_event.set()
        self.mic.stop()
        self.watcher.stop()
        if self.tts:
            self.tts.close()
        stop_ollama(self.ollama_process)
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    HanaApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
