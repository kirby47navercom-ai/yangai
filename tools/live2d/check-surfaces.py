"""Run after rebuild-surfaces.py; verifies asset invariants, not artistic perfection."""
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / 'assets/live2d/hana-v8-live'
spec = json.loads((MODEL / 'parts.json').read_text(encoding='utf-8'))
parts = {p['id']: p for p in spec['parts']}
images = {}
for name, p in parts.items():
    assert p['file'] == 'parts/' + name + '.png', name + ': non-local asset'
    rgba = np.array(Image.open(MODEL / p['file']).convert('RGBA'))
    assert rgba.shape[:2] == (p['height'], p['width']), name
    assert np.all(rgba[rgba[:, :, 3] == 0, :3] == 0), name + ': discarded RGB residue'
    images[name] = rgba

def at(name, x, y):
    p = parts[name]
    return images[name][y-p['top'], x-p['left']]

assert at('Face', 1950, 450)[3] > 190, 'Forehead missing behind bangs'
assert at('Neck', 1950, 1050)[3] > 190, 'Neck missing under jaw'
assert spec['paintOrder'].index('01_BootRear') < spec['paintOrder'].index('02_Legs') < spec['paintOrder'].index('03_Boots')
for side, x in [('VL',1825),('VR',2345)]:
    assert at('Boot_'+side+'_Main',x,4998)[3]==0, 'Boot lining still masks calf insertion'
    assert at('Boot_'+side+'_Back',x,4998)[3]>190, 'Boot back lining missing'
    assert at('Leg_'+side+'_Opening',x,4998)[3]>190, 'Calf does not enter the boot opening'
tail=parts['Tail_Root']
assert tail['left']+tail['width']<4096-40, 'No canvas margin for tail movement'
paint=np.array(Image.open(MODEL/'underpaint/semantic/tail-complete-v2.png'))[:,:,3]
assert not np.any(np.r_[paint[0],paint[-1],paint[:,0],paint[:,-1]]), 'Tail repaint is clipped before separation'
thigh_steps={}
for name in ('Leg_VL_Upper','Leg_VR_Upper'):
    p=parts[name];a=images[name];w=a.shape[1]
    rows=np.array([a[y,int(w*.3):int(w*.7),:3].mean(axis=0) for y in range(3370-p['top'],3900-p['top'])])
    step=float(np.abs(np.diff(rows,axis=0)).max());thigh_steps[name]=step
    assert step<3, name+': horizontal shading/cut-mask discontinuity'
rgba=images['Collar']
assert np.all(np.ptp(rgba[:,:,:3].astype(int),axis=2)[rgba[:,:,3]>190]<35), 'Skin/cape residue in collar'
for name in ('Face', 'Forelock_Red', 'Forelock_Blue', 'Hair_CrownBack', 'Pony_VL', 'Pony_VR', 'Cape_VL', 'Cape_VR', 'Tail_Root',
             'Boot_VL_Main','Boot_VR_Main','Jacket_VL_Pocket','Jacket_VR_Pocket','Cuff_VL','Cuff_VR','ArmBand_VL','ArmBand_VR'):
    rgba = images[name]
    count, labels, stats, centers = cv2.connectedComponentsWithStats((rgba[:, :, 3] > 190).astype(np.uint8), 8)
    assert sum(area >= 32 for area in stats[1:, cv2.CC_STAT_AREA]) == 1, name + ': detached opaque scraps'
for name in ('Hair_CrownBack', 'Pony_VL', 'Pony_VR'):
    rgba = images[name]; r,g,b = [rgba[:,:,i].astype(int) for i in range(3)]
    skin = (r>130)&(g>85)&(b>65)&(r-g>9)&(g-b>5)&(r-b<100)&(rgba[:,:,3]>190)
    assert skin.sum() == 0, name + ': skin mixed into hair'
for name, red in [('Forelock_Red',True),('Forelock_Blue',False)]:
    rgba=images[name]; r,b=rgba[:,:,0].astype(int),rgba[:,:,2].astype(int)
    opaque=rgba[:,:,3]>190
    dominant=(r-b>45) if red else (b-r>45)
    assert dominant[opaque].mean() > .9, name + ': wrong hair material'
for name in ('Boot_VL_Main','Boot_VR_Main','ArmBand_VL','ArmBand_VR'):
    rgba=images[name]; opaque=rgba[:,:,3]>190
    rgb=rgba[:,:,:3].astype(int)
    # Lanczos may overshoot at a handful of edge pixels; an ornament occupies a material-sized area.
    assert np.count_nonzero(np.ptp(rgb,axis=2)[opaque]>=70) < 32, name + ': colored ornament baked into cloth/leather'
for name in ('Jacket_VL_Pocket','Jacket_VR_Pocket','SleevePocket_VL','SleevePocket_VR'):
    rgba=images[name]; r,g,b=[rgba[:,:,i].astype(int) for i in range(3)]
    gold=(r>g+15)&(g>b+15)&(rgba[:,:,3]>190)
    assert gold.sum()==0, name + ': metal baked into white pocket'

overlaps = 0
for a,b in [('Leg_VL_Upper','Leg_VL_Lower'),('Leg_VR_Upper','Leg_VR_Lower'),
            ('Sleeve_VL_Main','Sleeve_VL_Lower'),('Sleeve_VR_Main','Sleeve_VR_Lower'),
            ('Boot_VL_Main','Boot_VL_Toe'),('Boot_VR_Main','Boot_VR_Toe'),
            ('Jacket_VL_Pocket','Jacket_VL_PocketFlap'),('Jacket_VR_Pocket','Jacket_VR_PocketFlap'),
            ('Tail_Root','Tail_LowerArc'),('Tail_Root','Tail_RisingArc'),('Tail_Root','Tail_TipWithTransition')]:
    pa,pb = parts[a],parts[b]
    x,y = max(pa['left'],pb['left']),max(pa['top'],pb['top'])
    right = min(pa['left']+pa['width'],pb['left']+pb['width'])
    bottom = min(pa['top']+pa['height'],pb['top']+pb['height'])
    aa = images[a][y-pa['top']:bottom-pa['top'],x-pa['left']:right-pa['left']]
    bb = images[b][y-pb['top']:bottom-pb['top'],x-pb['left']:right-pb['left']]
    core = (aa[:,:,3]>240)&(bb[:,:,3]>240)
    assert core.sum() > 1000, a + ': no covered overlap'
    assert np.array_equal(aa[core,:3],bb[core,:3]), a + ': two unrelated paintings meet at joint'
    overlaps += 1

original = ROOT / 'assets/live2d/hana-v6/hana-refined-4k.png'
digest = hashlib.sha256(original.read_bytes()).hexdigest()
assert digest == 'f91e25e12a870c202511d97912caa3ed196563a6e8052a314b0f965ab571e00a'
report = {'assetChecks':'PASS','parts':len(parts),'matchingPaintOverlaps':overlaps,
          'thighMaxAdjacentRowColorStep':thigh_steps,
          'original4kSha256Unchanged':digest,'fullBodyArtFinished':False}
(MODEL/'qa/surfaces.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
