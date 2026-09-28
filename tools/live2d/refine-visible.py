"""Locally refine bounded cut masks; never modify or discard source RGBA pixels."""
import json
import sys
import hashlib
from pathlib import Path

import cv2
import numpy as np


def magnetic_contour(image, original, radius=16, spacing=64):
    """Snap the closed boundary, not the part's colors or interior highlights."""
    alpha = image[:, :, 3].astype(np.float32) / 255
    rgb = image[:, :, :3].astype(np.float32) * alpha[:, :, None]
    gx = cv2.Sobel(rgb, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(rgb, cv2.CV_32F, 0, 1, ksize=3)
    strength = np.max(np.sqrt(gx * gx + gy * gy), axis=2)
    inside = cv2.distanceTransform(original.astype(np.uint8), cv2.DIST_L2, 5)
    outside = cv2.distanceTransform((~original).astype(np.uint8), cv2.DIST_L2, 5)
    distance = np.maximum(inside, outside)
    band = distance <= radius + 2
    scale = max(30., float(np.percentile(strength[band], 90)))
    edge = np.minimum(strength / scale, 1)
    cost = .025 + .68 * (1 - edge) + .24 * np.minimum(distance / radius, 1)
    cost[~band] = .999
    contours, _ = cv2.findContours(original.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    output = np.zeros(original.shape, np.uint8)
    for contour in contours:
        contour = contour[:, 0, :]
        if len(contour) < 8:
            continue
        step = max(1, min(spacing, len(contour) // 8))
        anchors = []
        for i in range(0, len(contour), step):
            point = contour[i].astype(np.float32)
            tangent = contour[(i + 5) % len(contour)] - contour[(i - 5) % len(contour)]
            normal = np.array([-tangent[1], tangent[0]], np.float32)
            normal /= max(float(np.linalg.norm(normal)), 1.)
            candidates = np.rint(point + np.arange(-radius, radius + 1)[:, None] * normal).astype(np.int32)
            candidates[:, 0] = np.clip(candidates[:, 0], 0, original.shape[1] - 1)
            candidates[:, 1] = np.clip(candidates[:, 1], 0, original.shape[0] - 1)
            score = cost[candidates[:, 1], candidates[:, 0]]
            chosen = candidates[np.argmin(score)]
            anchor = tuple(map(int, chosen))
            if not anchors or anchors[-1] != anchor:
                anchors.append(anchor)
        if len(anchors) < 3:
            continue
        route = []
        for a, b in zip(anchors, anchors[1:] + anchors[:1]):
            # Each adjacent-anchor search needs only its local corridor, not the full image.
            x0=max(0,min(a[0],b[0])-radius*2);y0=max(0,min(a[1],b[1])-radius*2)
            x1=min(original.shape[1],max(a[0],b[0])+radius*2+1);y1=min(original.shape[0],max(a[1],b[1])+radius*2+1)
            local=cost[y0:y1,x0:x1].astype(np.float32)
            scissors=cv2.segmentation_IntelligentScissorsMB();scissors.setWeights(0,0,1)
            scissors.applyImageFeatures(np.zeros(local.shape,np.uint8),np.zeros((*local.shape,2),np.float32),local)
            scissors.buildMap((a[0]-x0,a[1]-y0))
            route.append(scissors.getContour((b[0]-x0,b[1]-y0)).reshape(-1,2)+[x0,y0])
        cv2.fillPoly(output, [np.concatenate(route)], 1)
    assert output.any(), 'Empty magnetic contour'
    return output.astype(bool)


def chromatic_contour(image, original, kind, radius=2, holes=False):
    """Bounded material selection; retain enclosed highlights instead of cutting holes."""
    b,g,r=cv2.split(image[:,:,:3].astype(np.float32))
    if kind=='red':
        wanted=(r>g*1.24)&(r>b*1.18)
    elif kind=='blue':
        wanted=(b>r*1.23)&(b>g*1.08)
    elif kind=='white':
        wanted=(r>100)&(b>=r*.985)&(b<r*1.36)
    elif kind=='gold':
        wanted=(r>100)&(g>70)&(r>g*1.01)&(g>b*1.15)&(r<g*1.7)
    elif kind=='brown':
        wanted=(r>g*1.15)&(g<195)&(b<g*1.05)
    elif kind=='skin':
        wanted=(r>145)&(r>g*1.025)&(g>b*1.015)&(g>r*.70)
    else:
        raise ValueError(kind)
    selected=(wanted&original&(image[:,:,3]>0)).astype(np.uint8)
    selected=cv2.morphologyEx(selected,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    n,labels,stats,_=cv2.connectedComponentsWithStats(selected,8)
    assert n>1,kind
    selected=(labels==(1+np.argmax(stats[1:,cv2.CC_STAT_AREA]))).astype(np.uint8)
    if not holes:
        contours,_=cv2.findContours(selected,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(selected,contours,-1,1,cv2.FILLED)
    if radius:
        selected=cv2.dilate(selected,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(radius*2+1,)*2))
    return selected.astype(bool)&(image[:,:,3]>0)


def main():
    jobs_path = Path(sys.argv[1])
    jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
    implementation=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    cv2.setNumThreads(2)
    for job in jobs:
        signature=hashlib.sha256((implementation+json.dumps(job,sort_keys=True)).encode()+Path(job['mask']).read_bytes()+Path(job['image']).read_bytes()).hexdigest()
        stamp=Path(job['result']+'.sha256')
        if Path(job['result']).exists() and stamp.exists() and stamp.read_text()==signature:
            continue
        cv2.setRNGSeed(0)
        original = cv2.imdecode(np.fromfile(job["mask"], dtype=np.uint8), cv2.IMREAD_UNCHANGED)[:, :, 3] > 127
        image = cv2.imdecode(np.fromfile(job["image"], dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        visible = image[:, :, 3] > 0
        if job.get("method") in ("edge","material"):
            if job['method']=='edge':
                selected = magnetic_contour(image, original, job.get("radius", 16), job.get("spacing", 64)) & visible
            else:
                selected=chromatic_contour(image,original,job['color'],job.get('radius',1),job.get('holes',False))
            rgba = np.full((*selected.shape, 4), 255, dtype=np.uint8)
            rgba[:, :, 3] = selected.astype(np.uint8) * 255
            ok, encoded = cv2.imencode('.png', rgba)
            assert ok
            encoded.tofile(job["result"])
            stamp.write_text(signature)
            print(job["id"], int(selected.sum()), flush=True)
            continue
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
        stamp.write_text(signature)
        print(job["id"], int(selected.sum()), flush=True)


if __name__ == "__main__":
    main()
