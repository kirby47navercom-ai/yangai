"""Complete object paintings precede detail masks; original artwork remains read-only."""
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / 'assets/live2d/hana-v8-live'
V7 = MODEL.parent / 'hana-v7-rig'
GUIDES = ROOT / '.local-tools/live2d/semantic-guides'
PAINT = MODEL / 'underpaint/semantic'

def read(path):
    return np.array(Image.open(path).convert('RGBA'))

def grow(mask, radius):
    return cv2.dilate(mask.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (radius*2+1,)*2)) > 0

def regional(p, rgba, box):
    canvas = Image.new('RGBA', (box[2]-box[0], box[3]-box[1]))
    canvas.paste(Image.fromarray(rgba), (p['left']-box[0], p['top']-box[1]))
    return np.array(canvas)

def clean(rgba, largest=False):
    core = (rgba[:, :, 3] > 190).astype(np.uint8)
    # Remove thin noise bridges before selecting a completed object; do not preserve floating grain as hair.
    if largest: core = cv2.morphologyEx(core, cv2.MORPH_OPEN, np.ones((5,5),np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(core, 8)
    assert count > 1, 'No opaque painting'
    keep = labels == (1+np.argmax(stats[1:, cv2.CC_STAT_AREA])) if largest else np.isin(labels, [i for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] >= 32])
    tile = rgba.copy(); tile[~grow(keep, 2), 3] = 0
    # Generated opaque materials carry alpha 252/253. Overlapping them shows a rectangular opacity step.
    # Keep fractional antialiasing at the contour, but make the solid material actually opaque.
    tile[tile[:,:,3]>190,3]=255
    return tile

def bounds(rgba):
    ys, xs = np.where(rgba[:, :, 3] > 190)
    assert len(xs)
    return int(xs.min()), int(ys.min()), int(xs.max())+1, int(ys.max())+1

def fit(rgba, box, largest=False):
    rgba = clean(rgba, largest); a,b,c,d = bounds(rgba)
    return clean(cv2.resize(rgba[b:d, a:c], (box[2]-box[0], box[3]-box[1]), interpolation=cv2.INTER_LANCZOS4), largest)

def main():
    guides = {p['id']: p for p in json.loads((GUIDES / 'guides.json').read_text())}
    current = json.loads((MODEL / 'parts.json').read_text(encoding='utf-8'))
    extra = {p['id']: p for p in current['parts'] if p['id'].endswith('_Sclera') or p['id'] in ('Mouth_Open','Eye_VL_Tear','Eye_VR_Tear')}
    baseline = json.loads((V7 / 'parts.json').read_text())['parts']
    parts = [{**p} for p in baseline if not p['id'].startswith('Forelock_Blue_Tip')]
    images = {p['id']: read(V7 / p['file']) for p in parts}
    for p in parts:
        if p['id'].endswith('_Sclera'):
            p.update(extra[p['id']]); images[p['id']] = read(MODEL / p['file'])
    for name in ('Mouth_Open','Eye_VL_Tear','Eye_VR_Tear'):
        parts.append({**extra[name]}); images[name] = read(MODEL / extra[name]['file'])
    by_id = {p['id']: p for p in parts}; removed = {}

    def save(name, rgba, box=None, reason='closed-object-contour-reviewed'):
        if name not in by_id:
            p={'id':name,'group':'01_BootRear','defaultOpacity':1}
            parts.append(p);by_id[name]=p
        p = by_id[name]
        if box is not None: p['left'],p['top'] = box[:2]
        ys,xs = np.where(rgba[:,:,3] > 0); assert len(xs), name
        a,b = max(0,int(xs.min())-4),max(0,int(ys.min())-4)
        c,d = min(rgba.shape[1],int(xs.max())+5),min(rgba.shape[0],int(ys.max())+5)
        tile = rgba[b:d,a:c].copy()
        tile[tile[:,:,3]==0,:3]=0  # Standalone PNG viewers must not reveal discarded RGB under zero alpha.
        p.update(left=p['left']+a,top=p['top']+b,width=c-a,height=d-b,file='parts/'+name+'.png',surfaceReview=reason,
                 pixels=int((tile[:,:,3]>0).sum()),solidPixels=int((tile[:,:,3]>190).sum()),status='semantic-surface-repair-draft')
        for key in ('sha256','hiddenFillPixels','jointOverlapPixels','aiUnderpaintPixels','visibleSkinRepainted'): p.pop(key,None)
        p['hiddenSurface']='painted-large-surface' if 'paint' in reason else 'existing-small-overlap-not-complete-anatomy'
        Image.fromarray(tile).save(MODEL / p['file']); images[name] = tile

    # Unknown fragments are not assigned to the nearest layer. Each object's own contour is authoritative.
    for p in parts:
        name=p['id']; tile=images[name].copy()
        if name in ('Face','Hair_CrownBack','Forelock_Red','Forelock_Blue') or name.startswith(('Tail_','Leg_')): continue
        if name in guides and not name.startswith('Eye_') and name not in ('Mouth','Nose'):
            g=guides[name]; box=(p['left'],p['top'],p['left']+p['width'],p['top']+p['height'])
            mask=grow(regional(g,read(GUIDES / (name+'.png')),box)[:,:,3] > 20,8)
            if name.startswith(('Hair_','Forelock_','Pony_')):
                r,gc,b=[tile[:,:,i].astype(int) for i in range(3)]
                skin=(r>130)&(gc>85)&(b>65)&(r-gc>9)&(gc-b>5)&(r-b<100)
                mask &= ~grow(skin,2)
                if 'White' in name or name.startswith('Hair_'):
                    mask &= (np.ptp(tile[:,:,:3].astype(int),axis=2)<80)&(np.max(tile[:,:,:3],axis=2)>85)
                elif '_Red_' in name: mask &= r-b>45
                elif '_Blue_' in name: mask &= b-r>45
            tile[~mask,3]=0
        if name.startswith(('Boot_','Hand_','Cuff_','Jacket_','Sleeve','Pony_','Hair_')): tile=clean(tile)
        removed[name]=int(((images[name][:,:,3]>0)&(tile[:,:,3]==0)).sum())
        save(name,tile)

    # A metal ring/chain is not an opaque disc of skirt fabric; its interior remains transparent.
    # Keep painted metal pixels (including warm shadows), not a replacement vector ring.
    for name in ['Hip_VL_Ring','Hip_VR_Ring','Hip_VL_Chain','Hip_VR_Chain','Cape_VL_Cord','Boot_VL_Flower','Boot_VR_Flower']:
        tile=images[name].copy(); r,g,b=[tile[:,:,i].astype(int) for i in range(3)]
        metal=(r>g+7)&(g>b+4)&(r>70)
        tile[~grow(metal,1),3]=0
        save(name,clean(tile),reason='original-painted-metal-only-no-fabric-disc')

    face_box=(1470,210,2350,1073)
    save('Face',fit(read(PAINT/'head-skin.png'),face_box),face_box,'complete-painted-head-no-hair-notches')
    neck_box=(1820,870,2165,1310)
    save('Neck',fit(read(PAINT/'neck-skin.png'),neck_box,largest=True),neck_box,'complete-painted-neck-under-jaw-and-collar')
    by_id['Neck']['group']='08_Torso'  # Neck behind collar; it must not paint skin over the front collar.
    collar=images['Collar'].copy()
    cloth=np.ptp(collar[:,:,:3].astype(int),axis=2)<35
    collar[~cloth,3]=0
    save('Collar',clean(collar,largest=True),reason='collar-cloth-only-no-old-neck-outline-or-red-cape')
    box=(1390,170,2390,1080); white=fit(read(PAINT/'white-front-hair.png'),box,largest=True)
    # ONE coherent white hair painting owns the complete shape; its detail layers use identical paint.
    # Different generated/old white paintings must not be overlaid: that creates doubled strand edges.
    save('Hair_CrownBack',white,box,'complete-painted-white-front-hair-only'); by_id['Hair_CrownBack']['group']='14_Crown'
    for name in [p['id'] for p in parts if p['id'].startswith(('Hair_VL_','Hair_VR_'))]:
        mask=regional(guides[name],read(GUIDES/(name+'.png')),box)[:,:,3]>128
        patch=white.copy(); patch[~mask,3]=0
        if (patch[:,:,3]>190).any(): save(name,patch,box,'same-paint-white-lock-no-skin-or-other-hair')
    for name,paint,is_red in [('Forelock_Red','forelock-red.png',True),('Forelock_Blue','forelock-blue.png',False)]:
        p=next(q for q in baseline if q['id']==name); original=read(V7/p['file'])
        material=(original[:,:,0].astype(int)-original[:,:,2]>65) if is_red else (original[:,:,2].astype(int)-original[:,:,0]>65)
        material &= original[:,:,3]>190
        marker=original.copy(); marker[~material,3]=0; a,b,c,d=bounds(clean(marker,largest=True))
        target=(p['left']+a,p['top']+b,p['left']+c,p['top']+d)
        painted=fit(read(PAINT/paint),target)
        # Skin-colored shadow triangles can pass a red threshold. Do not copy this contaminated old lock.
        save(name,painted,target,'complete-painted-hair-only')

    # Reconstruct BOTH ponytails from completed hair paint, not hair-shaped scraps of skin/cape/clips.
    back=read(PAINT/'back-hair.png')
    pony_contours={'VL':[(0,.13),(.27,.13),(.34,.18),(.30,.30),(.28,.43),(.32,.55),(.39,.64),(.40,1),(0,1)],
                   'VR':[(.69,.13),(1,.13),(1,1),(.62,1),(.62,.62),(.66,.54),(.75,.39),(.72,.24)]}
    for side,box in [('VL',(1120,180,1750,1535)),('VR',(2110,160,2830,1470))]:
        contour=np.array([(int(x*back.shape[1]),int(y*back.shape[0])) for x,y in pony_contours[side]],np.int32)
        mask=np.zeros(back.shape[:2],np.uint8); cv2.fillPoly(mask,[contour],1)
        paint=back.copy(); paint[mask==0,3]=0
        plane=fit(paint,box,largest=True)
        r,g,b=[plane[:,:,i].astype(int) for i in range(3)]
        skin=(r>130)&(g>85)&(b>65)&(r-g>9)&(g-b>5)&(r-b<100)
        plane[grow(skin,2),3]=0
        plane=clean(plane,largest=True)
        save('Pony_'+side,plane,box,'complete-painted-ponytail-hair-only')
        for name in [p['id'] for p in parts if p['id'].startswith('Pony_'+side+'_')]:
            mask=regional(guides[name],read(GUIDES/(name+'.png')),box)[:,:,3]>128
            mask &= (np.ptp(plane[:,:,:3].astype(int),axis=2)<80) if '_White_' in name else (r-b>45 if side=='VL' else b-r>45)
            patch=plane.copy(); patch[~mask,3]=0
            if (patch[:,:,3]>190).any(): save(name,patch,box,'same-paint-ponytail-lock')

    box=(1250,1020,2580,1530); cape=fit(read(PAINT/'cape-fabric.png'),box,largest=True)
    r,g,b=[cape[:,:,i].astype(int) for i in range(3)]
    for side in ('VL','VR'):
        # The black collar/yoke is another textile layer; no fastener or neck is baked into a cape half.
        mask=grow(r-b>25 if side=='VL' else b-r>25,2)
        patch=cape.copy(); patch[~mask,3]=0
        save('Cape_'+side,clean(patch,largest=True),box,'complete-painted-cape-fabric-only')

    box=(1080,1030,2720,3370); inner=fit(read(PAINT/'inner-outfit.png'),box)
    for name,region in [('Inner_Bodice',(1450,1050,2450,2040)),('Waist_Corset',(1600,1820,2260,2120)),('Skirt_Center',(1080,1980,2720,3370))]:
        save(name,regional({'left':box[0],'top':box[1]},inner,region),region,'continuous-painted-black-fabric-no-decoration-holes')
    # Side panels use the SAME complete garment, not old rectangles with flowers/loops baked in.
    for name in [p['id'] for p in parts if p['id'].startswith('Skirt_') and p['id']!='Skirt_Center' and 'Emblem' not in p['id']]:
        mask=grow(regional(guides[name],read(GUIDES/(name+'.png')),box)[:,:,3]>128,12)
        patch=inner.copy(); patch[~mask,3]=0
        save(name,clean(patch,largest=True),box,'same-painted-skirt-fabric-with-covered-panel-roots')
    coat_box=(560,1260,3210,3030); coat=fit(read(PAINT/'jacket-base.png'),coat_box)
    yy,xx=np.indices(coat.shape[:2]); gx,gy=xx+coat_box[0],yy+coat_box[1]
    # Match shoulder width to the source posture before cutting: the generated jacket was too narrow there.
    factor=1+.26*np.clip((2100-gy)/700,0,1)
    coat=cv2.remap(coat,(1940+(gx-1940)/factor-coat_box[0]).astype(np.float32),yy.astype(np.float32),cv2.INTER_LANCZOS4)
    # The old visible-pixel cutouts contain strap/pocket edges. Never bake them back into the cloth base.
    coat=clean(coat,largest=True)
    # Physical sleeve/torso seams on the COMPLETE new painting, with covered root overlaps.
    # These regions cover the garment as a whole; the old exclusive visible-pixel masks did not.
    for name in ['Jacket_VL','Jacket_VR','Sleeve_VL_Main','Sleeve_VR_Main','Sleeve_VL_Lower','Sleeve_VR_Lower']:
        left='_VL' in name
        if name.startswith('Jacket_'):
            mask=(gx>=1450)&(gx<1940)&(gy<2150) if left else (gx>=1940)&(gx<=2440)&(gy<2150)
        else:
            mask=(gx<1550) if left else (gx>2340)
            mask &= (gy<2330) if name.endswith('_Main') else (gy>2150)
        patch=coat.copy(); patch[~mask,3]=0
        if name.startswith('Sleeve_'):
            rgb=patch[:,:,:3].astype(int)
            cuff_material=(rgb[:,:,0]-rgb[:,:,2]>65) if left else (rgb[:,:,2]-rgb[:,:,0]>65)
            patch[cuff_material&(gy>2720),3]=0
        save(name,clean(patch),coat_box,'complete-painted-cloth-panel')
    for side in ('VL','VR'):
        for suffix in ('InsideHem',):
            name='Jacket_'+side+'_'+suffix
            mask=(gy>2030)&(gy<2150)&((gx<1940)&(gx>1450) if side=='VL' else (gx>1940)&(gx<2440))
            patch=coat.copy(); patch[~mask,3]=0
            save(name,patch,coat_box,'same-paint-inner-hem')
    cuffs=read(PAINT/'cuffs-base.png'); pockets=read(PAINT/'pockets-base.png'); armbands=read(PAINT/'armbands-base.png')
    for side in ('VL','VR'):
        half=slice(0,armbands.shape[1]//2) if side=='VL' else slice(armbands.shape[1]//2,None)
        p=next(q for q in baseline if q['id']=='ArmBand_'+side)
        box=(p['left'],p['top'],p['left']+p['width'],p['top']+p['height'])
        save(p['id'],fit(armbands[:,half],box,largest=True),box,'complete-painted-armband-black-cloth-only')
        half=slice(0,cuffs.shape[1]//2) if side=='VL' else slice(cuffs.shape[1]//2,None)
        p=next(q for q in baseline if q['id']=='Cuff_'+side)
        box=(p['left'],p['top'],p['left']+p['width'],p['top']+p['height'])
        save(p['id'],fit(cuffs[:,half],box,largest=True),box,'complete-painted-cuff-no-button-scars')
        half=slice(0,pockets.shape[1]//2) if side=='VL' else slice(pockets.shape[1]//2,None)
        for prefix in ('Jacket_'+side+'_','Sleeve'):
            body='Jacket_'+side+'_Pocket' if prefix.startswith('Jacket') else 'SleevePocket_'+side
            flap='Jacket_'+side+'_PocketFlap' if prefix.startswith('Jacket') else 'SleeveFlap_'+side
            a,b=by_id[body],by_id[flap]
            box=(min(a['left'],b['left']),min(a['top'],b['top']),max(a['left']+a['width'],b['left']+b['width']),max(a['top']+a['height'],b['top']+b['height']))
            plane=fit(pockets[:,half],box,largest=True)
            save(body,plane,box,'complete-painted-pocket-fabric-no-hardware')
            patch=plane.copy(); yy,xx=np.indices(patch.shape[:2]); patch[yy>patch.shape[0]*.37,3]=0
            save(flap,patch,box,'same-painted-pocket-flap-with-covered-root')
        # A hand contains skin/nails, not the cuff's colored rim. Keep the nail color at the finger tips.
        name='Hand_'+side; p=by_id[name]; tile=images[name].copy(); yy,xx=np.indices(tile.shape[:2])
        rgb=tile[:,:,:3].astype(int)
        foreign=((rgb[:,:,0]>130)&(rgb[:,:,1]<95)&(rgb[:,:,2]<90)) if side=='VL' else ((rgb[:,:,2]>130)&(rgb[:,:,0]<100))
        tile[foreign&(yy<tile.shape[0]*.16),3]=0
        save(name,clean(tile,largest=True),reason='hand-skin-and-nails-no-colored-cuff-rim')
    boots=read(PAINT/'boots-base.png')
    for side,box in [('VL',(1570,4950,2080,6105)),('VR',(2090,4950,2600,6105))]:
        half=slice(0,boots.shape[1]//2) if side=='VL' else slice(boots.shape[1]//2,None)
        plane=fit(boots[:,half],box,largest=True)
        yy,xx=np.indices(plane.shape[:2]);cx=plane.shape[1]/2
        # Back lining behind the calf, front rim/shaft in front of it. A filled ellipse cannot be worn.
        rear=plane.copy();rear[yy>115,3]=0
        save('Boot_'+side+'_Back',rear,box,'painted-boot-rear-rim-and-lining-behind-calf')
        opening=((xx-cx)/(plane.shape[1]*.425))**2+((yy-48)/39)**2<1
        plane[opening,3]=0
        save('Boot_'+side+'_Main',plane,box,'complete-painted-boot-front-with-open-calf-insertion')
        for suffix in ('Toe','Sole','UpperStrap','LowerStrap'):
            name='Boot_'+side+'_'+suffix
            mask=grow(regional(guides[name],read(GUIDES/(name+'.png')),box)[:,:,3]>128,6)
            patch=plane.copy(); patch[~mask,3]=0
            save(name,clean(patch,largest=True),box,'same-painted-boot-leather-with-covered-overlap')
    legs=read(PAINT/'legs-complete-v2.png')
    syy,sxx=np.indices(legs.shape[:2])
    # Split in the EMPTY gap, not at the canvas midpoint: the left calf crosses that midpoint.
    gap=np.interp(syy[:,0]/legs.shape[0]*1536,[0,160,380,580,690,990,1130,1260,1440,1536],
                  [520,515,520,524,535,555,570,570,575,575])/1024*legs.shape[1]
    for side,box in [('VL',(1340,3000,1950,5140)),('VR',(1950,3000,2520,5140))]:
        # A stocking is one continuous anatomical silhouette, not two paintings meeting at a crop line.
        leg=legs.copy();leg[sxx>gap[:,None] if side=='VL' else sxx<gap[:,None],3]=0
        full=fit(leg,box,largest=True)
        # Match original leg anatomy and knee height, while preserving ONE uninterrupted painting.
        yy,xx=np.indices(full.shape[:2]); gy=yy+box[1]
        sy=np.interp(gy[:,0],[3000,4108,5140],[0,(full.shape[0]-1)*.4,full.shape[0]-1])
        # The old visible-pixel masks contain skirt/tail occlusion steps. Never use them as anatomy.
        joints=[3000,4108,4450,4950,5140]
        centers=[1600,1720,1740,1790,1800] if side=='VL' else [2230,2170,2280,2350,2370]
        radii=[240,145,160,120,115] if side=='VL' else [250,135,180,110,105]
        center=np.interp(gy[:,0],joints,centers)-box[0];radius=np.interp(gy[:,0],joints,radii)
        lo=center-radius;hi=center+radius
        lo=cv2.GaussianBlur(lo.astype(np.float32).reshape(-1,1),(1,81),20).ravel()
        hi=cv2.GaussianBlur(hi.astype(np.float32).reshape(-1,1),(1,81),20).ravel()
        source=full[np.rint(sy).astype(int),:,3]>190
        valid=source.any(axis=1);rows=np.arange(len(source))
        sl=np.interp(rows,rows[valid],source[valid].argmax(axis=1))
        sh=np.interp(rows,rows[valid],full.shape[1]-1-source[valid,::-1].argmax(axis=1))
        sl=cv2.GaussianBlur(sl.astype(np.float32).reshape(-1,1),(1,31),7).ravel()
        sh=cv2.GaussianBlur(sh.astype(np.float32).reshape(-1,1),(1,31),7).ravel()
        sx=sl[:,None]+(xx-lo[:,None])*(sh-sl)[:,None]/np.maximum(hi-lo,1)[:,None]
        full=cv2.remap(full,sx.astype(np.float32),np.broadcast_to(sy[:,None],yy.shape).astype(np.float32),cv2.INTER_LANCZOS4)
        full[(xx<lo[:,None])|(xx>hi[:,None]),3]=0
        for suffix,y0,y1 in [('Upper',3000,4230),('Lower',4060,5140),('Opening',4950,5140)]:
            region=(box[0],y0,box[2],y1)
            save('Leg_'+side+'_'+suffix,regional({'left':box[0],'top':box[1]},full,region),region,'painted-continuous-stocking-overlap')
    box=(2350,2650,4040,4670); tail=fit(read(PAINT/'tail-complete-v2.png'),box)
    for name,region in [('Tail_Root',box),('Tail_LowerArc',(2350,3510,3560,4670)),('Tail_RisingArc',(3270,3410,4040,4670)),('Tail_TipWithTransition',(3210,2650,4040,3900))]:
        save(name,regional({'left':box[0],'top':box[1]},tail,region),region,'painted-complete-tail-overlap')

    order=['01_Tail','01_BootRear','02_Legs','03_Boots','04_Skirt','08_Torso','05_Sleeves','06_Hands','07_Cuffs','09_Jacket','12_Hair','10_Cape','11_Neck','18_ArmDetails','20_Hardware','21_SkirtDecor','17_Bow','13_Face','15_Eyes','15_Eye_VL','15_Eye_VR','16_FaceDetails','14_Crown','14_FrontHair','19_HairClips']
    assert set(p['group'] for p in parts).issubset(order)
    parts.sort(key=lambda p:order.index(p['group']))
    report={'workflow':'painted-material-surfaces-before-detail-separation','processedParts':len(parts),
            'trimmedPixelsByPart':{k:v for k,v in removed.items() if v},
            'paintedFamilies':['head-skin','neck-skin','white-crown','red-forelock','blue-forelock','ponytails','cape-fabric','inner-outfit','jacket-sleeves','stocking-legs','tail','boots','pockets','cuffs','armbands'],
            'allHiddenAnatomyFinished':False,'remaining':['complete individual hair locks rather than small visible slivers','remaining metal/strap/cord ornaments and their independent hidden contours','large-angle side/back portrait keyforms and final contour-tailored meshes']}
    # V7's residue/underfill counters are provenance of old cutouts, not measurements of this painting.
    for key in ('residueReassigned','hiddenFillPixels','jointOverlapPixels','unchangedOriginalParts','backgroundHaloPixelsRemoved',
                'skinUnderpaint','fabricUnderpaint','aiUnderpaintPixels','source','hiddenRepair'):
        current.pop(key,None)
    current['baselineParts']='../hana-v7-rig/parts.json'
    current.update(parts=parts,paintOrder=order,semanticRepair=report,hiddenRepair=None,rigReady=False)
    (MODEL/'parts.json').write_text(json.dumps(current,indent=2)+'\n',encoding='utf-8')
    (MODEL/'qa/hidden-repair.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='trimmedPixelsByPart'},indent=2))

if __name__=='__main__': main()
