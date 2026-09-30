"""Native MOC3 display and speech-driven animation. No chat/model service startup."""
import math
import random
import time
from pathlib import Path


EXPRESSIONS = ("neutral", "smile", "happy", "sad", "cry", "angry", "surprised")
# Eye openness, mouth form, brow tilt, brow height, tears, eye smile.
FACES = {
    "neutral": (1, 0, 0, 0, 0, 0), "smile": (.9, .7, 0, .1, 0, .25),
    "happy": (.65, 1, -.15, .3, 0, .8), "sad": (.8, -.7, -.7, .1, 0, 0),
    "cry": (.55, -.8, -.8, .1, 1, .2), "angry": (.7, -.6, .85, -.5, 0, 0),
    "surprised": (1.15, -.15, 0, .7, 0, 0),
}


class AvatarState:
    def __init__(self, clock=time.monotonic, rng=None, lip_gain=5):
        self.clock = clock
        self.rng = rng or random.Random()
        self.expression = "neutral"
        self.level = 0.0
        self.level_at = 0.0
        self.lip_gain = max(.5, min(20, float(lip_gain)))
        self.values = {}
        self.started = clock()
        self.last = self.started
        self.blink_at = self.started + self.rng.uniform(2.8, 5.5)
        self.hair_position = self.hair_velocity = 0.0

    def set_expression(self, name):
        self.expression = name if name in EXPRESSIONS else "neutral"

    def audio_level(self, level):
        self.level = min(1.0, max(0.0, float(level)) * self.lip_gain) ** .65 if math.isfinite(float(level)) else 0.0
        self.level_at = self.clock()

    def pose(self, x=0.0, y=0.0, follow=True):
        now = self.clock()
        dt = min(.1, max(0.0, now - self.last))
        self.last = now
        t = now - self.started
        x = max(-1.0, min(1.0, x)) if follow else 0.0
        y = max(-1.0, min(1.0, y)) if follow else 0.0
        blink = 1.0
        if now >= self.blink_at:
            age = now - self.blink_at
            blink = max(0.0, min(1.0, abs(age - .095) / .095))
            if age >= .22:
                self.blink_at = now + self.rng.uniform(2.8, 5.5)
        eye, mouth, brow, height, tears, eye_smile = FACES[self.expression]
        # The level is updated only during WAV playback; a stale callback never leaves the mouth open.
        audio = self.level if now - self.level_at < .16 else 0.0
        target = {
            "ParamAngleX": x * 20, "ParamAngleY": -y * 15,
            "ParamAngleZ": -x * 5 + audio * math.sin(t * 5) * .6,
            "ParamEyeBallX": x * .65, "ParamEyeBallY": -y * .5,
            "ParamEyeLOpen": eye * blink, "ParamEyeROpen": eye * blink,
            "ParamEyeSmile": eye_smile, "ParamMouthOpenY": audio,
            "ParamMouthForm": mouth, "ParamBrowForm": brow, "ParamBrowY": height,
            "ParamTears": tears, "ParamBodyAngleZ": -x * .7 + math.sin(t * .65) * .16,
            "ParamBodyAngleX": x * 7 + math.sin(t * .55) * .8,
            "ParamBreath": (math.sin(t * 1.7) + 1) * .35,
            "ParamTailSwing": math.sin(t * .85 - 1.2) * .25,
            "ParamArmSwingVL": math.sin(t * 1.1) * (.08 + audio * .16),
            "ParamArmSwingVR": math.sin(t * 1.1 + .6) * (.08 + audio * .16),
            "ParamLegVL": x * .18 + math.sin(t * .55) * .08,
            "ParamLegVR": x * .18 + math.sin(t * .55) * .08,
            "ParamKneeVL": math.sin(t * .55) * .12,
            "ParamKneeVR": -math.sin(t * .55) * .12,
        }
        previous_head = self.values.get("ParamAngleX", 0.0)
        for key, value in target.items():
            # Fast blink/lip response; slower head/face transitions avoid snapping between sentences.
            speed = 35 if key in ("ParamEyeLOpen", "ParamEyeROpen", "ParamMouthOpenY") else 20 if key.startswith("ParamEyeBall") else 4 if key.startswith("ParamAngle") else 7
            previous = self.values.get(key, 0.0 if key.startswith(("ParamAngle", "ParamEyeBall", "ParamBodyAngle", "ParamLeg", "ParamKnee")) else value)
            self.values[key] = previous + (value - previous) * (1 - math.exp(-speed * dt))
        # Secondary BACK hair follows head velocity; front bangs never slide independently over skin.
        drive = max(-.8, min(.8, -(self.values['ParamAngleX'] - previous_head) / max(dt, .001) * .014))
        for _ in range(4):
            step = dt / 4
            self.hair_velocity += (38 * (drive - self.hair_position) - 11 * self.hair_velocity) * step
            self.hair_position += self.hair_velocity * step
        self.values['ParamHairSwing'] = max(-1.0, min(1.0, self.hair_position))
        return dict(self.values)


def create_avatar(parent, model_path, state, on_error=None):
    """Embed the existing Tk UI's GL surface; no second window or polling process."""
    from pyopengltk import OpenGLFrame
    import live2d.v3 as live2d
    from OpenGL import GL

    class AvatarFrame(OpenGLFrame):
        def __init__(self):
            self.model = None
            self.failed = False
            self.follow_mouse = True
            self.manual_pose = None
            super().__init__(parent, width=300, height=620)
            self.animate = 33

        def initgl(self):
            if self.failed:
                return
            try:
                if self.model is None:
                    path = Path(model_path).resolve()
                    if not path.is_file():
                        raise FileNotFoundError("하나 리깅 모델 파일이 없어요.")
                    live2d.enableLog(False)
                    live2d.init()
                    live2d.glInit()
                    self.model = live2d.LAppModel()
                    native_path = path.as_posix()
                    moc = path.with_name("hana.moc3")
                    if not self.model.HasMocConsistencyFromFile(moc.as_posix()):
                        raise RuntimeError("내보낸 MOC3가 재생기 검증을 통과하지 못했어요. 앱에 연결하지 않아요.")
                    self.model.LoadModelJson(native_path)
                    if self.model.GetParameterCount() == 0:
                        raise RuntimeError("리깅 모델을 읽지 못했어요.")
                    self.model.SetAutoBlinkEnable(False)
                    self.model.SetAutoBreathEnable(False)
                self.model.Resize(self.winfo_width(), self.winfo_height())
            except Exception as error:
                self.failed = True
                self.animate = 0
                if on_error:
                    self.after_idle(lambda error=error: on_error(str(error)))
                else:
                    raise

        def redraw(self):
            if self.failed or not self.model:
                return
            GL.glViewport(0, 0, self.winfo_width(), self.winfo_height())
            # Read-only pointer observation, including while another app owns the cursor.
            px, py = self.winfo_pointerxy()
            x = (px - self.winfo_rootx() - self.winfo_width() / 2) / max(150, self.winfo_screenwidth() / 3)
            y = (py - self.winfo_rooty() - self.winfo_height() * .25) / max(150, self.winfo_screenheight() / 3)
            values = self.manual_pose if self.manual_pose is not None else state.pose(x, y, self.follow_mouse)
            for key, value in values.items():
                self.model.SetParameterValue(key, value, 1)
            self.model.Update()
            live2d.clearBuffer(23 / 255, 32 / 255, 51 / 255, 1)
            self.model.Draw()

        def destroy(self):
            self.animate = 0
            if self.cb:
                self.after_cancel(self.cb)
                self.cb = None
            if self.model:
                self.tkMakeCurrent()
                self.model.DestroyRenderer()
                self.model = None
                live2d.dispose()
            super().destroy()

    return AvatarFrame()


def demo(root=None, model_path=None, check=False):
    import tkinter as tk
    import sys
    root = root or tk.Tk()
    root.title("하나 · 표정 확인")
    root.geometry("620x820")
    state = AvatarState()
    errors, result = [], []
    panel = tk.Frame(root)
    panel.pack(side="bottom", fill="x")
    base = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
    avatar = create_avatar(root, model_path or base / "assets/live2d/hana-v8-live/umamo/hana.model3.json", state, errors.append)
    avatar.pack(fill="both", expand=True)
    for name in EXPRESSIONS:
        tk.Button(panel, text=name, command=lambda n=name: state.set_expression(n)).pack(side="left")
    if check:
        # Exercise the shipped, windowed EXE without starting user devices or model services.
        def verify():
            import json
            try:
                assert not errors, errors
                assert avatar.model is not None
                ids = set(avatar.model.GetParamIds())
                assert set(state.pose()).issubset(ids)
                avatar.manual_pose = {**state.pose(), 'ParamMouthOpenY': .7, 'ParamTears': 1}
                avatar.redraw()
                from OpenGL import GL
                from PIL import Image
                GL.glFinish()
                size = (avatar.winfo_width(), avatar.winfo_height())
                pixels = GL.glReadPixels(0, 0, *size, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE)
                report = {'passed': True, 'parameters': len(ids), 'frozen': getattr(sys, 'frozen', False)}
                output = base / 'data/diagnostics'
                output.mkdir(parents=True, exist_ok=True)
                Image.frombytes('RGBA', size, pixels).transpose(Image.Transpose.FLIP_TOP_BOTTOM).save(output / 'avatar-built.png')
            except Exception as error:
                report = {'passed': False, 'error': str(error)}
                output = base / 'data/diagnostics'
                output.mkdir(parents=True, exist_ok=True)
            (output / 'avatar-built.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
            result.append(report['passed'])
            root.destroy()
        root.geometry('620x820-5000-5000')
        root.after(700, verify)
    root.mainloop()
    return result[0] if result else None


if __name__ == "__main__":
    demo()
