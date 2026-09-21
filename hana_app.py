from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import scrolledtext

from hana_chat import (
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
    load_history,
    load_latest_session_history,
    load_json,
    make_messages,
    new_session_file,
    now,
    read_config,
    request_json,
    save_json,
    save_memory_snapshot,
    start_memory_compaction,
    stream_chat,
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
        self.prompt = PROMPT_FILE.read_text(encoding="utf-8") if PROMPT_FILE.exists() else "너는 하나야."
        self.memory = load_json(MEMORY_FILE, default_memory())
        self.history_file = new_session_file()
        self.history = load_history(self.history_file)
        if not self.memory.get("recent_conversation") and not self.history:
            previous_history = load_latest_session_history(self.history_file)
            if previous_history:
                save_memory_snapshot(self.memory, previous_history)
        self.user_turns = sum(1 for item in self.history if item["role"] == "user")
        self.stop_event = threading.Event()
        self.chat_busy = threading.Event()
        self.chat_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.last_user_activity_at = time.monotonic()
        self.last_response_at = time.monotonic()
        self.last_auto_requested_at = self.last_response_at
        self.last_idle_requested_at = 0.0
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
        )
        self._build_ui()
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
        self.root.after(0, lambda: self.status.configure(text=f"화면 읽음: {observation[:32]}"))

    def _on_screen_error(self, error: str) -> None:
        self.root.after(0, lambda: self._system(f"화면을 읽을 수 없어: {error or '알 수 없는 오류'}"))

    def _on_tts_status(self, message: str) -> None:
        self.tts_status = message
        if message:
            self.status.configure(text=message)

    def _post_tts_status(self, message: str) -> None:
        if not self.stop_event.is_set():
            self.root.after(0, lambda: self._on_tts_status(message))

    def _idle_loop(self) -> None:
        delay = max(1.0, float(self.config.get("talk_after_speech_seconds", 3)))
        while not self.stop_event.wait(1.0):
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
            reference = max(self.last_response_at, self.last_auto_requested_at)
            if self.tts and self.tts.enabled:
                reference = max(reference, self.tts.last_finished_at)
            requested_at = time.monotonic()
            if requested_at - reference < delay:
                continue
            self.last_auto_requested_at = requested_at
            self.last_idle_requested_at = requested_at
            self.chat_queue.put(("idle", ""))

    def _tts_busy(self) -> bool:
        return bool(self.tts and (self.tts.speaking.is_set() or not self.tts.items.empty()))

    def _queue_user(self, text: str, source: str = "입력") -> None:
        text = text.strip()
        if not text:
            return
        self.last_user_activity_at = time.monotonic()
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
                if kind == "user":
                    self._answer_user(payload)
                else:
                    self._answer_idle()
            except Exception as error:
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
                    "방송 중인 하나가 방금 화면을 직접 봤어. 채팅이나 사용자 입력을 기다리지 말고, "
                    "화면에 실제로 보이는 장면·앱·게임 상태·읽을 수 있는 글자 중 하나를 골라 "
                    "게임 버튜버다운 짧은 방송 멘트를 한두 문장으로 반드시 먼저 말해. "
                    "반복되는 화면이어도 현재 장면에 대한 감상이나 다음 흐름에 대한 기대를 말하고, "
                    "[SILENT]를 출력하지 마. 화면에 없는 내용은 만들지 마.\n\n"
                    + observation
                ),
            }
        )
        answer = self._stream_and_speak(messages)
        if not answer:
            return

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
                    "하나가 방금 말을 마치고 3초 쉬었어. 방송을 계속 이어가야 해. "
                    "사용자나 채팅이 먼저 말을 걸 때까지 기다리지 말고, 하나가 지금 보고 있는 화면과 "
                    "직전 하나의 말과 지금까지의 방송 흐름을 바탕으로 게임 버튜버다운 짧은 멘트를 한두 문장으로 반드시 자연스럽게 해. "
                    "화면을 언급한다면 무엇이 보이는지만 읽지 말고, 그 장면을 보며 하나가 든 감정·판단·다음 기대까지 한 단계 이어서 말해. "
                    "같은 장면이면 앞에서 시작한 생각을 발전시키고, 화면이 바뀌면 방금 전 흐름과 연결해서 말해. "
                    "화면에 특별한 일이 없으면 지금 방송 분위기나 하나의 가벼운 생각을 말하고, 질문으로 끝내지 마. "
                    "[SILENT]는 출력하지 마."
                ),
            }
        )
        answer = self._stream_and_speak(messages)
        if not answer:
            return
        created_at = now()
        append_jsonl(self.history_file, {"role": "assistant", "content": answer, "created_at": created_at})
        self.history.append({"role": "assistant", "content": answer, "created_at": created_at})
        save_memory_snapshot(self.memory, self.history, self.screen_context.prompt())
        self.last_response_at = time.monotonic()

    def _stream_and_speak(self, messages: list[dict]) -> str:
        full = ""
        sentence_buffer = SentenceBuffer()
        started = False
        try:
            for piece in stream_chat(self.config, messages):
                full += piece
                if piece and not started:
                    started = True
                    self.root.after(0, lambda: self._start_line("하나", "hana"))
                self.root.after(0, lambda piece=piece: self._append_text(piece))
                for sentence in sentence_buffer.feed(piece):
                    self._speak(sentence)
            for sentence in sentence_buffer.flush():
                self._speak(sentence)
            if started:
                self.root.after(0, self._finish_line)
        except Exception:
            if started:
                self.root.after(0, self._finish_line)
            raise
        return full.strip()

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

    def _toggle_voice(self) -> None:
        if self.tts:
            self.tts.enabled = not self.tts.enabled
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.mic_button.configure(text=f"마이크 {'켜짐' if self.mic.running() else '꺼짐'}")
        self.watch_button.configure(text=f"화면 {'켜짐' if self.watcher.running() else '꺼짐'}")
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
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    HanaApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
