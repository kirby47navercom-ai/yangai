"""Render our model into GL artifacts, not desktop screenshots or microphone recordings."""
import json
import math
import random
import sys
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from hana_avatar import AvatarState, FACES, create_avatar
from OpenGL import GL
from PIL import Image

root = tk.Tk()
root.geometry("1024x1536-5000-5000")
state = AvatarState()
errors = []
folder = ROOT / "assets/live2d/hana-v8-live"
frame = create_avatar(root, folder / "umamo/hana.model3.json", state, errors.append)
frame.pack(fill="both", expand=True)
root.update()

def render(name, values, scale=1, offset=(0, 0)):
    assert not errors, errors
    assert frame.model is not None
    frame.tkMakeCurrent()
    frame.model.ResetParameters()
    frame.model.SetScale(scale)
    frame.model.SetOffset(*offset)
    frame.manual_pose = values
    frame.redraw()
    GL.glFinish()
    pixels = GL.glReadPixels(0, 0, frame.winfo_width(), frame.winfo_height(), GL.GL_RGBA, GL.GL_UNSIGNED_BYTE)
    image = Image.frombytes("RGBA", (frame.winfo_width(), frame.winfo_height()), pixels).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    if name:
        image.save(folder / "qa" / ("runtime-" + name + ".png"))
    return image

try:
    assert not errors, errors
    ids = set(frame.model.GetParamIds())
    assert "ParamMouthOpenY" in ids and "ParamEyeLOpen" in ids
    neutral = render("neutral", {"ParamEyeLOpen": 1, "ParamEyeROpen": 1})
    contact = Image.new('RGBA', (470 * 4, 435 * 2), '#172033')
    for i, (name, (eye, mouth, brow, height, tears, smile)) in enumerate(FACES.items()):
        face = render(name + "-face", {"ParamEyeLOpen": eye, "ParamEyeROpen": eye, "ParamMouthForm": mouth,
              "ParamBrowForm": brow, "ParamBrowY": height, "ParamTears": tears, "ParamEyeSmile": smile}, 3, (0, -1.8))
        contact.paste(face.crop((210, 220, 680, 655)), (i % 4 * 470, i // 4 * 435))
    contact.save(folder / 'qa/runtime-expressions.png')
    render("blink-face", {"ParamEyeLOpen": 0, "ParamEyeROpen": 0}, 3, (0, -1.8))
    render("talk-face", {"ParamEyeLOpen": 1, "ParamEyeROpen": 1, "ParamMouthOpenY": .7}, 3, (0, -1.8))
    for direction in (-1, 1):
        image = render("motion-" + str(direction), {"ParamEyeLOpen": 1, "ParamEyeROpen": 1,
            "ParamAngleX": direction * 20, "ParamAngleY": direction * 15, "ParamEyeBallX": direction,
            "ParamEyeBallY": direction, "ParamHairSwing": direction, "ParamTailSwing": direction,
            "ParamBodyAngleX": direction * 7, "ParamLegVL": direction, "ParamLegVR": direction,
            "ParamKneeVL": -direction, "ParamKneeVR": direction,
            "ParamArmSwingVL": direction, "ParamArmSwingVR": -direction, "ParamBreath": 1})
        assert image.tobytes() != neutral.tobytes()
        image.crop((240, 690, 1010, 1536)).save(folder/'qa'/('runtime-lower-body-'+str(direction)+'.png'))
    combined=Image.new('RGBA',(512*3,768*2),'#172033')
    for i,(yaw,pitch,eye,openness,form) in enumerate([(-20,-15,1,.7,1),(20,-15,0,0,-1),
            (-20,15,0,.7,-1),(20,15,1,.7,1),(0,0,1,.03,0),(0,0,1,.12,0)]):
        image=render('combined-'+str(i),{'ParamAngleX':yaw,'ParamAngleY':pitch,'ParamAngleZ':-yaw/4,
            'ParamBodyAngleX':yaw*.35,'ParamEyeLOpen':eye,'ParamEyeROpen':eye,
            'ParamMouthOpenY':openness,'ParamMouthForm':form,'ParamHairSwing':yaw/30},2,(0,-1.3))
        combined.paste(image.resize((512,768)),(i%3*512,i//3*768))
    combined.save(folder/'qa/runtime-combined-poses.png')
    directions=Image.new('RGBA',(470*3,435*3),'#172033')
    for i,(yaw,pitch) in enumerate((x,y) for y in (-15,0,15) for x in (-20,0,20)):
        pose={'ParamEyeLOpen':1,'ParamEyeROpen':1,'ParamAngleX':yaw,'ParamAngleY':pitch,
              'ParamAngleZ':-yaw/4,'ParamEyeBallX':yaw/30,'ParamEyeBallY':pitch/30,'ParamHairSwing':yaw/20}
        face=render('head-'+str(i),pose,3,(0,-1.8))
        directions.paste(face.crop((210,220,680,655)),(i%3*470,i//3*435))
    directions.save(folder/'qa/runtime-head-directions.png')
    clock, frames = [0.0], []
    animation = AvatarState(clock=lambda: clock[0], rng=random.Random(4))
    for i in range(96):
        clock[0] = i / 12
        animation.set_expression(('neutral', 'happy', 'angry', 'cry')[i // 24])
        # Synthetic level for an explicit silent animation preview, not a claim of audible TTS validation.
        animation.audio_level(max(0, math.sin(i * .65)) * .16)
        frames.append(render(None, animation.pose(math.sin(i / 18), math.sin(i / 21) * .5)).resize((512, 768)))
    frames[0].save(folder / 'qa/motion-preview.webp', save_all=True, append_images=frames[1:], duration=83, loop=0, quality=85)
    (folder / "qa/runtime.json").write_text(json.dumps({"officialCoreConsistency": True, "rendered": True,
        "parameters": len(ids), "visualReview": False}, indent=2) + "\n", encoding="utf-8")
    print("Native model render checks: PASS", len(ids), "parameters")
finally:
    root.destroy()
