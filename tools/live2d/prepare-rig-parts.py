"""Preserve native visible pixels; fill small occlusions and add internal joint overlaps."""
import json
from pathlib import Path
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "assets/live2d/hana-v6-precision"
DEST = ROOT / "assets/live2d/hana-v7-rig"


def read_image(path):
    image = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_UNCHANGED)
    assert image is not None, str(path)
    return image


def family(name):
    if name.startswith(("Hair_", "Forelock_", "Pony_", "HairClip_")):
        return "hair"
    if name.startswith("Tail_"):
        return "tail"
    if name.startswith(("Leg_", "Boot_")):
        return "leg_" + ("VL" if "_VL" in name else "VR")
    if name.startswith(("Sleeve", "ArmBand", "Shoulder", "Cuff", "Hand")):
        return "arm_" + ("VL" if "_VL" in name else "VR")
    if name.startswith(("Eye_", "Brow_")) or name in ("Face", "Neck", "Nose", "Mouth"):
        return "face"
    return "torso"


def beneath(base, detail):
    """Removable overlays need painted fabric underneath, not a punched-out parent."""
    side = 'VL' if '_VL' in base else 'VR'
    if base.startswith('Boot_') and base.endswith('_Main'):
        return detail.startswith('Boot_' + side + '_') and not detail.endswith(('_Tassel', '_Flower'))
    if base == 'Cuff_' + side:
        return detail.startswith(base + '_')
    if base == 'Waist_Corset':
        return detail.startswith(('Waist_',))
    if base == 'Inner_Bodice':
        return detail.startswith('Necktie')
    if base == 'Skirt_Center':
        return detail.startswith(('Skirt_Emblem_', 'Hip_', 'Pendant_'))
    if base == 'Jacket_' + side:
        return detail.startswith(base + '_') and 'InsideHem' not in detail or side == 'VR' and detail == 'Chest_Brooch'
    if base == 'Sleeve_' + side + '_Main':
        return detail.startswith(('ArmBand_' + side, 'Shoulder_' + side, 'SleevePocket_' + side, 'SleeveFlap_' + side)) or detail in ['Sleeve_' + side + '_' + suffix for suffix in ('Cord', 'Medallion')]
    if base == 'Sleeve_' + side + '_Lower':
        return detail.startswith('SleeveGem_' + side) or detail in ['Sleeve_' + side + '_' + suffix for suffix in ('Tassel', 'Ribbon', 'Coin')]
    if base == 'Cape_' + side:
        return detail.startswith(base + '_')
    if base == 'Face':
        return detail.startswith(('Eye_', 'Brow_')) or detail in ('Nose', 'Mouth')
    return False


def main():
    parts = [p for p in json.loads((BASE / "parts.json").read_text())['parts'] if p.get('file')]
    source = read_image(ROOT / "assets/live2d/hana-v6/hana-refined-4k.png")
    # The accepted source still has a diffuse background halo; clean alpha only, not line/color pixels.
    original_alpha = source[:, :, 3].copy()
    edge_distance = cv2.distanceTransform((original_alpha < 240).astype(np.uint8), cv2.DIST_L2, 5)
    edge_keep = np.clip((6.0 - edge_distance) / 3.0, 0, 1)
    source[:, :, 3] = np.rint(original_alpha * edge_keep).astype(np.uint8)
    assert np.array_equal(source[:, :, 3][original_alpha >= 240], original_alpha[original_alpha >= 240])
    h, w = source.shape[:2]
    owners = np.zeros((h, w), np.uint16)
    for n, part in enumerate(parts, 1):
        img = read_image(BASE / part['file'])
        x, y = part['left'], part['top']
        patch = owners[y:y + img.shape[0], x:x + img.shape[1]]
        patch[img[:, :, 3] > 0] = n
    assert np.all(owners[source[:, :, 3] > 0]), "Missing source pixels"
    # Assign the old catch-all scraps to their nearest existing part, never discard them.
    residue = owners == 1
    distance, labels = cv2.distanceTransformWithLabels((owners <= 1).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    zero_labels = labels[owners > 1]
    lookup = np.zeros(int(labels.max()) + 1, np.uint16)
    lookup[zero_labels] = owners[owners > 1]
    assert np.all(lookup[zero_labels] == owners[owners > 1])
    owners[residue] = lookup[labels[residue]]
    del labels, lookup, zero_labels, distance
    groups = {name: i + 1 for i, name in enumerate(sorted({family(p['id']) for p in parts[1:]}))}
    part_family = np.zeros(len(parts) + 1, np.uint8)
    for n, part in enumerate(parts, 1):
        if n > 1:
            part_family[n] = groups[family(part['id'])]
    regions = part_family[owners]
    (DEST / "parts").mkdir(parents=True, exist_ok=True)
    (DEST / "qa").mkdir(exist_ok=True)
    output = []
    total_filled = total_overlap = 0
    for n, part in enumerate(parts, 1):
        if n == 1:
            continue
        underneath = [i for i, p in enumerate(parts, 1) if i != n and beneath(part['id'], p['id'])]
        coverage = np.isin(owners, [n, *underneath])
        ys, xs = np.where(coverage)
        if not len(xs):
            continue
        padding = 32
        x, y = max(0, int(xs.min()) - padding), max(0, int(ys.min()) - padding)
        right, bottom = min(w, int(xs.max()) + padding + 1), min(h, int(ys.max()) + padding + 1)
        own = owners[y:bottom, x:right] == n
        img = np.zeros((bottom - y, right - x, 4), np.uint8)
        src = source[y:bottom, x:right]
        img[own] = src[own]
        solid = (own & (src[:, :, 3] >= 240)).astype(np.uint8)
        outside = cv2.copyMakeBorder(solid, 1, 1, 1, 1, cv2.BORDER_CONSTANT)
        flood = outside.copy()
        cv2.floodFill(flood, None, (0, 0), 2)
        holes = (flood[1:-1, 1:-1] == 0)
        count, hole_labels, stats, _ = cv2.connectedComponentsWithStats(holes.astype(np.uint8), 8)
        # ponytail: local texture continuation only; large anatomical occlusions still require repainting.
        small = np.zeros_like(own)
        for i in range(1, count):
            if stats[i, cv2.CC_STAT_AREA] <= 18000:
                small |= hole_labels == i
        same_family = regions[y:bottom, x:right] == part_family[n]
        small |= np.isin(owners[y:bottom, x:right], underneath)
        small &= same_family & (src[:, :, 3] >= 240) & ~own
        # Extend only inside other already-visible same-family pieces, not outside the silhouette.
        joint = part['id'].startswith(('Tail_', 'Leg_', 'Sleeve_', 'Skirt_', 'Pony_', 'Hair_', 'Forelock_', 'Jacket_', 'Cape_', 'Boot_'))
        extend = cv2.dilate(solid, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (49, 49))) > 0 if joint else np.zeros_like(own)
        extend &= same_family & (src[:, :, 3] >= 240) & ~own
        extend &= ~small
        fill = small
        if fill.any():
            # Supply valid nearest texture outside this part before inpainting its new hidden band.
            hsv = cv2.cvtColor(src[:, :, :3], cv2.COLOR_BGR2HSV)
            material = own.copy()
            if part['id'].startswith(('Jacket_', 'Sleeve_')):
                material &= (hsv[:, :, 1] < 85) & (hsv[:, :, 2] > 155)
            elif part['id'].startswith(('Boot_', 'Skirt_')) or part['id'] in ('Waist_Corset', 'Inner_Bodice'):
                material &= (hsv[:, :, 1] < 100) & (hsv[:, :, 2] < 160)
            elif part['id'] == 'Cuff_VL':
                material &= (src[:, :, 2].astype(int) - src[:, :, 0] > 55)
            elif part['id'] == 'Cuff_VR':
                material &= (src[:, :, 0].astype(int) - src[:, :, 2] > 55)
            if not material.any():
                material = own
            _, nearest = cv2.distanceTransformWithLabels((~material).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
            palette = np.zeros((int(nearest.max()) + 1, 3), np.uint8)
            palette[nearest[material]] = src[:, :, :3][material]
            rgb = palette[nearest]
            rgb[material] = src[:, :, :3][material]
            painted = cv2.inpaint(rgb, fill.astype(np.uint8) * 255, 6, cv2.INPAINT_TELEA)
            img[fill, :3] = painted[fill]
            img[fill, 3] = src[fill, 3]
        # A joint band continues the adjacent existing texture exactly at the neutral pose.
        img[extend] = src[extend]
        assert np.array_equal(img[own], src[own]), part['id'] + ': changed visible pixels'
        file = 'parts/' + part['id'] + '.png'
        ok, encoded = cv2.imencode('.png', img)
        assert ok
        (DEST / file).write_bytes(encoded.tobytes())
        record = {**part, 'file': file, 'left': x, 'top': y, 'width': right - x, 'height': bottom - y,
                  'articulationBounds': [part['left'], part['top'], part['width'], part['height']],
                  'hiddenFillPixels': int(small.sum()), 'jointOverlapPixels': int(extend.sum()),
                  'status': 'native-pixels-with-local-overlap', 'hiddenSurface': 'small-occlusions-only'}
        record.pop('sha256', None)
        output.append(record)
        total_filled += int(small.sum())
        total_overlap += int(extend.sum())
        if len(output) % 24 == 0:
            print('Prepared', len(output), 'parts', flush=True)
    report = {'canvas': [w, h], 'parts': output, 'residueReassigned': int(residue.sum()),
              'hiddenFillPixels': total_filled, 'jointOverlapPixels': total_overlap,
              'sourceSolidPixelsPreserved': True, 'sourceRgbPreserved': True,
              'backgroundHaloPixelsRemoved': int(((original_alpha > 0) & (source[:, :, 3] == 0)).sum()),
              'largeHiddenAnatomyRepainted': False,
              'rigReady': False, 'cubismImportTested': False}
    (DEST / 'parts.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'parts'}, indent=2), flush=True)


if __name__ == '__main__':
    main()
