"""Locally refine bounded cut masks; never modify or discard source RGBA pixels."""
import json
import sys
from pathlib import Path

import cv2
import numpy as np


def main():
    jobs_path = Path(sys.argv[1])
    jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
    cv2.setNumThreads(2)
    for job in jobs:
        cv2.setRNGSeed(0)
        original = cv2.imdecode(np.fromfile(job["mask"], dtype=np.uint8), cv2.IMREAD_UNCHANGED)[:, :, 3] > 127
        image = cv2.imdecode(np.fromfile(job["image"], dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        visible = image[:, :, 3] > 0
        rgb = image[:, :, :3].astype(np.float32)
        blue, green, red = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
        radius = job.get("radius", 12)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (radius * 2 + 1,) * 2)
        outer = cv2.dilate(original.astype(np.uint8), kernel) > 0
        inner = cv2.erode(original.astype(np.uint8), kernel) > 0
        labels = np.full(original.shape, cv2.GC_BGD, dtype=np.uint8)
        labels[outer & visible] = cv2.GC_PR_BGD
        labels[original & visible] = cv2.GC_PR_FGD
        labels[inner & visible] = cv2.GC_FGD
        mode = job.get("color")
        if mode:
            if mode == "red":
                wanted = (red > green * 1.30) & (red > blue * 1.20)
                reject = (np.minimum(green, blue) > red * .84) | (blue > red * 1.04) | ((green > red * .75) & (red > blue))
            elif mode == "blue":
                wanted = (blue > red * 1.30) & (blue > green * 1.06)
                reject = (red > blue * .83) | (red > green * 1.10)
            elif mode == "skin":
                wanted = (red > green * 1.035) & (green > blue * 1.015) & (red > 170) & (green > red * .62)
                reject = (blue > red * .99) | (green < red * .55) | (red < 110)
            elif mode == "gold":
                wanted = (red > blue * 1.3) & (green > blue * 1.15) & (red < green * 1.65)
                reject = (blue > green * 1.05) | (red > green * 1.8)
            elif mode == "white":
                wanted = (blue > red * .98) & (red > 140) & (blue < red * 1.35)
                reject = (red > blue * 1.04) | (blue > red * 1.5)
            elif mode == "ink":
                wanted = np.max(rgb, axis=2) < 95
                reject = np.min(rgb, axis=2) > 135
            elif mode == "mouth":
                wanted = (red > green * 1.25) & (green < 165)
                reject = (green > 190) | (blue > red)
            elif mode == "bluegray":
                wanted = (blue > red * 1.12) & (red < 210) & (blue < 250)
                reject = (np.min(rgb, axis=2) > 215) | (red > blue)
            else:
                raise ValueError(mode)
            labels[outer & visible & reject] = cv2.GC_BGD
            labels[original & visible & wanted] = cv2.GC_FGD
        assert np.count_nonzero(labels == cv2.GC_FGD) > 0, job["id"]
        cv2.grabCut(image[:, :, :3], labels, None, np.zeros((1, 65)), np.zeros((1, 65)), 3, cv2.GC_INIT_WITH_MASK)
        selected = np.isin(labels, [cv2.GC_FGD, cv2.GC_PR_FGD]) & visible
        # Keep the connected subject, not isolated color specks near it.
        count, components, stats, _ = cv2.connectedComponentsWithStats(selected.astype(np.uint8), 8)
        if count > 1:
            selected = components == (1 + np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        assert np.count_nonzero(selected) > 0, job["id"]
        rgba = np.full((*selected.shape, 4), 255, dtype=np.uint8)
        rgba[:, :, 3] = selected.astype(np.uint8) * 255
        ok, encoded = cv2.imencode('.png', rgba)
        assert ok
        encoded.tofile(job["result"])
        print(job["id"], int(selected.sum()), flush=True)


if __name__ == "__main__":
    main()
