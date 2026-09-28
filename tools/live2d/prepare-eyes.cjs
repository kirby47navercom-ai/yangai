// Eye underpainting is deliberately separate from the lossless visible-pixel split.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const sharp=require('sharp'),{createCanvas,loadImage,Path2D}=require('@napi-rs/canvas'),psd=require('ag-psd');
psd.initializeCanvas(createCanvas,(width,height)=>({width,height,data:new Uint8ClampedArray(width*height*4)}));
const root=path.resolve(__dirname,'../..'),base=path.join(root,'assets/live2d/hana-v6-precision');
assert(!process.argv[2]||process.argv[2]==='v2','Use no argument for the original eyes, or v2 for painted irises');
const painted=process.argv[2]==='v2',legacy=path.join(base,'eye-motion'),dest=painted?path.join(base,'eye-motion-v2'):legacy;
const W=4096,H=6144,S=4,source=path.join(root,'assets/live2d/hana-v6/hana-refined-4k.png');
const manifest={canvas:[W,H],masterPixels:'native generated sheet pixels; never upscaled',parts:[],rigReady:false,cubismImportTested:false};
const original=JSON.parse(fs.readFileSync(path.join(base,'parts.json'))).parts;
const masters={},native={},layers=[];
const eyeSpec={VL:{cx:444,cy:199.5,r:12,white:[441,202,32,17],pupil:[444,200.9,2.35,4.1],light:[443.2,200.65,.9,.9]},VR:{cx:515.5,cy:183.6,r:12.2,white:[517,187,32,17],pupil:[515.1,185.7,2.1,4.2],light:[514.65,185.05,1,1]}};
const apertures={VL:'M419.8 203.2C429 199.7 443 197.7 456 199.1L457.3 200.2L456.6 206.1C449.4 207.2 440.2 210.7 432 213.2C425.8 211.5 422 207.8 419.8 203.2Z',VR:'M495.2 189.3C505 182.5 520 179.1 536.2 180.1C535.9 186.1 533.1 189.6 527.4 191.7C516.2 191.9 505.6 194 496.1 195.5Z'};
function solvePlane(a,b){
  // ponytail: local affine color match, not anatomical repainting; finish seams in a painting editor.
  const m=a.map((r,i)=>[...r,b[i]]);
  for(let col=0;col<3;col++){const pivot=[col,...Array.from({length:2-col},(_,i)=>i+col+1)].sort((x,y)=>Math.abs(m[y][col])-Math.abs(m[x][col]))[0];[m[col],m[pivot]]=[m[pivot],m[col]];assert(Math.abs(m[col][col])>1e-8,'Insufficient skin samples');const t=m[col][col];for(let j=col;j<4;j++)m[col][j]/=t;for(let i=0;i<3;i++)if(i!==col){const v=m[i][col];for(let j=col;j<4;j++)m[i][j]-=v*m[col][j];}}
  return m.map(r=>r[3]);
}
function ellipse(w,h){const c=createCanvas(w,h),ctx=c.getContext('2d');ctx.fillStyle='#fff';ctx.beginPath();ctx.ellipse(w/2,h/2,w/2-2,h/2-2,0,0,Math.PI*2);ctx.fill();return c;}
async function save(id,buf,box,kind){
  const file='parts/'+id+'.png';fs.writeFileSync(path.join(dest,file),buf);
  const img=await loadImage(buf),{data,info}=await sharp(buf).ensureAlpha().raw().toBuffer({resolveWithObject:true});
  native[id]={img,...box};
  layers.push({name:id,left:box.left,top:box.top,opacity:1,blendMode:'normal',hidden:kind==='guide'||kind==='underpaint',imageData:{width:info.width,height:info.height,data:new Uint8ClampedArray(data)}});
  manifest.parts.push({id,file,...box,kind});return native[id];
}
async function place(id,master,cx,cy,w,h,kind='moving'){
  const width=Math.round(w*S),height=Math.round(h*S),left=Math.round(cx*S-width/2),top=Math.round(cy*S-height/2);
  const buf=await sharp(master).resize(width,height,{fit:'fill'}).png().toBuffer();
  return save(id,buf,{left,top,width,height},kind);
}
async function main(){
  for(const sub of ['masters','parts','qa'])fs.mkdirSync(path.join(dest,sub),{recursive:true});
  const sheet=path.join(legacy,'source/eye-underpaint-sheet.png'),meta=await sharp(sheet).metadata();
  assert.equal(meta.width,1536);assert.equal(meta.height,1024);
  const sourceRaw=await sharp(source).ensureAlpha().raw().toBuffer();
  const hair=await Promise.all(original.filter(p=>p.file&&/^(Hair_|Forelock_)/.test(p.id)&&p.id!=='Hair_CrownBack').map(async p=>({...p,img:await loadImage(path.join(base,p.file))})));
  // Exact closed contours discard the unwanted generated glow, not the colored iris interior.
  const shapes=[['VL_Iris',464,205,174,174],['VR_Iris',1072,205,174,174],['VL_Pupil',462,507,34,88],['VR_Pupil',1072,507,34,88],['VL_Sclera',464,726,243,95],['VR_Sclera',1072,726,243,95],['VL_Catchlight',462,912,31,31],['VR_Catchlight',1073,894,26,26],['VR_LowerReflection',1074,963,61,22]];
  for(const [id,cx,cy,rx,ry]of shapes){
    if(painted&&id.endsWith('Iris'))continue;
    const width=rx*2+4,height=ry*2+4,left=cx-rx-2,top=cy-ry-2;
    const {data}=await sharp(sheet).extract({left,top,width,height}).ensureAlpha().raw().toBuffer({resolveWithObject:true});
    const mask=ellipse(width,height).getContext('2d').getImageData(0,0,width,height).data;
    for(let i=0;i<width*height;i++){data[i*4+3]=mask[i*4+3];if(!mask[i*4+3])data.fill(0,i*4,i*4+3);}
    const buf=await sharp(data,{raw:{width,height,channels:4}}).png().toBuffer();
    const file='masters/'+id+'.png';fs.writeFileSync(path.join(dest,file),buf);masters[id]=buf;
    let opaqueInside=0,leaks=0,softEdges=0;
    for(let y=0;y<height;y++)for(let x=0;x<width;x++){
      const exterior=((x+.5-width/2)/(rx+1))**2+((y+.5-height/2)/(ry+1))**2,a=data[(y*width+x)*4+3];
      const interior=((x+.5-width/2)/(rx-1.5))**2+((y+.5-height/2)/(ry-1.5))**2;
      if(interior<1&&a!==255)opaqueInside++;if(exterior>1&&a!==0)leaks++;if(a>0&&a<255)softEdges++;
    }
    assert.equal(opaqueInside,0,id+' interior holes');assert.equal(leaks,0,id+' outer glow');assert(softEdges>0,id+' no antialiasing');
    if(id.endsWith('Iris'))assert.equal(width,height,id+' must be circular');
    manifest.parts.push({id:'Master_'+id,file,width,height,kind:'native-high-resolution-master',interiorHoles:opaqueInside,outerLeaks:leaks});
  }
  if(painted){
    // Keep the generated contour and native resolution; do not trim off its limbal ring.
    const paintedSheet=path.join(dest,'source/iris-painted.png');
    const {data,info}=await sharp(paintedSheet).ensureAlpha().raw().toBuffer({resolveWithObject:true});
    assert.equal(info.width,1774);assert.equal(info.height,887);
    for(const [side,left,top]of [['VL',182,110],['VR',931,110]]){
      const size=664,buf=await sharp(paintedSheet).extract({left,top,width:size,height:size}).png().toBuffer();
      let interiorHoles=0,minAlpha=255,edgeAlpha=0;
      for(let y=0;y<size;y++)for(let x=0;x<size;x++){
        const a=data[((top+y)*info.width+left+x)*4+3];
        if(Math.hypot(x-size/2,y-size/2)<size*.45){minAlpha=Math.min(minAlpha,a);if(a<240)interiorHoles++;}
        if(x===0||y===0||x===size-1||y===size-1)edgeAlpha=Math.max(edgeAlpha,a);
      }
      assert.equal(interiorHoles,0,side+' painted iris interior gap');
      assert(edgeAlpha<20,side+' painted contour clipped by crop');
      const id=side+'_Iris',file='masters/'+id+'.png';masters[id]=buf;fs.writeFileSync(path.join(dest,file),buf);
      manifest.parts.push({id:'Master_'+id,file,width:size,height:size,kind:'native-painted-iris',interiorHoles,minInteriorAlpha:minAlpha,edgeAlpha,generatedAlphaPreserved:true});
    }
    // Match the reflection silhouette on both eyes; only its pigment follows iris color.
    const reflection=await sharp(masters.VR_LowerReflection).ensureAlpha().raw().toBuffer({resolveWithObject:true});
    const pink=Buffer.from(reflection.data);
    for(let i=0;i<pink.length;i+=4){const r=pink[i];pink[i]=pink[i+2];pink[i+1]=Math.round((pink[i+1]+r)/2);pink[i+2]=Math.round((pink[i+2]+r)/2);}
    masters.VL_LowerReflection=await sharp(pink,{raw:reflection.info}).png().toBuffer();
    const file='masters/VL_LowerReflection.png';fs.writeFileSync(path.join(dest,file),masters.VL_LowerReflection);
    manifest.parts.push({id:'Master_VL_LowerReflection',file,width:reflection.info.width,height:reflection.info.height,kind:'matching-reflection-silhouette',pairedWith:'Master_VR_LowerReflection'});
    for(let i=3;i<pink.length;i+=4)assert.equal(pink[i],reflection.data[i],'Paired reflection alpha mismatch');
  }
  for(const [side,e]of Object.entries(eyeSpec)){
    const prefix='Eye_'+side+'_',white=e.white;
    const eyes=original.filter(p=>p.id.startsWith(prefix)&&p.file),sx=Math.min(...eyes.map(p=>p.left))-20,sy=Math.min(...eyes.map(p=>p.top))-20,sw=Math.max(...eyes.map(p=>p.left+p.width))+20-sx,sh=Math.max(...eyes.map(p=>p.top+p.height))+20-sy;
    const eyeMask=createCanvas(sw,sh),ecm=eyeMask.getContext('2d');for(const p of eyes)ecm.drawImage(await loadImage(path.join(base,p.file)),p.left-sx,p.top-sy);
    const coverage=ecm.getImageData(0,0,sw,sh);for(let i=0;i<sw*sh;i++){coverage.data[i*4]=coverage.data[i*4+1]=coverage.data[i*4+2]=255;coverage.data[i*4+3]=coverage.data[i*4+3]?255:0;}ecm.putImageData(coverage,0,0);
    const skinMask=createCanvas(sw,sh),sc=skinMask.getContext('2d');for(const x of [-4,0,4])for(const y of [-4,0,4])sc.drawImage(eyeMask,x,y);
    const feather=await sharp(await skinMask.encode('png')).blur(1).raw().toBuffer();
    const skin=await sharp(path.join(legacy,'source/skin-underpaint-texture.png')).resize(sw,sh,{fit:'fill'}).ensureAlpha().raw().toBuffer();
    // Match the generated underpaint's low-frequency color to surrounding original skin.
    const a=Array.from({length:3},()=>[0,0,0]),b=Array.from({length:3},()=>[0,0,0]);let samples=0;
    for(let y=0;y<sh;y++)for(let x=0;x<sw;x++){
      const i=(y*sw+x)*4,j=((sy+y)*W+sx+x)*4,[r,g,blue]=sourceRaw.subarray(j,j+3);
      if(feather[i+3]>0||r<205||g<170||blue<140||r-g<5||g-blue<3)continue;
      const v=[1,x/sw,y/sh];samples++;for(let q=0;q<3;q++){for(let t=0;t<3;t++)a[q][t]+=v[q]*v[t];for(let k=0;k<3;k++)b[k][q]+=sourceRaw[j+k]*v[q];}
    }
    assert(samples>100,'Not enough surrounding skin');const planes=b.map(v=>solvePlane(a,v)),center=(Math.floor(sh/2)*sw+Math.floor(sw/2))*4,textureCenter=[...skin.subarray(center,center+3)];
    for(let y=0;y<sh;y++)for(let x=0;x<sw;x++){const i=(y*sw+x)*4;for(let k=0;k<3;k++)skin[i+k]=Math.max(0,Math.min(255,planes[k][0]+planes[k][1]*x/sw+planes[k][2]*y/sh+(skin[i+k]-textureCenter[k])*.15));skin[i+3]=feather[i+3];}
    await save(prefix+'Skin_Underpaint',await sharp(skin,{raw:{width:sw,height:sh,channels:4}}).png().toBuffer(),{left:sx,top:sy,width:sw,height:sh},'fixed-skin');
    await place(prefix+'Sclera_Full',masters[side+'_Sclera'],...white.slice(0,2),white[2]*2,white[3]*2,'underpaint');
    const aperture=new Path2D(apertures[side]),bounds=aperture.computeTightBounds();
    const left=Math.floor(bounds[0]*S)-2,top=Math.floor(bounds[1]*S)-2,width=Math.ceil(bounds[2]*S)+2-left,height=Math.ceil(bounds[3]*S)+2-top;
    const mask=createCanvas(width,height),mc=mask.getContext('2d');mc.setTransform(S,0,0,S,-left,-top);mc.fillStyle='#fff';mc.fill(aperture);
    const opening=createCanvas(width,height),oc=opening.getContext('2d'),full=native[prefix+'Sclera_Full'];oc.drawImage(full.img,full.left-left,full.top-top);oc.globalCompositeOperation='destination-in';oc.drawImage(mask,0,0);
    await save(prefix+'Sclera_Opening',await opening.encode('png'),{left,top,width,height},'clip-base');
    await save(prefix+'Aperture_Guide',await mask.encode('png'),{left,top,width,height},'guide');
    await place(prefix+'Iris_Full',masters[side+'_Iris'],e.cx,e.cy,e.r*2,e.r*2);
    await place(prefix+'Pupil_Full',masters[side+'_Pupil'],...e.pupil.slice(0,2),e.pupil[2]*2,e.pupil[3]*2);
    await place(prefix+'Catchlight_Full',masters[side+'_Catchlight'],...e.light.slice(0,2),e.light[2]*2,e.light[3]*2);
    if(painted)await place(prefix+'LowerReflection_Full',masters[side+'_LowerReflection'],e.cx,e.cy+e.r*.615,e.r*.377,e.r*.18);
    else if(side==='VR')await place(prefix+'LowerReflection_Full',masters.VR_LowerReflection,515.5,191.1,4.6,2.2);
    if(painted){
      // A separate cast-shadow mask stays with the eyelid, not with the iris.
      // ponytail: front-view shadow only; rotated/blinking eyelids require Cubism deformation.
      const shadow=createCanvas(width,height),shc=shadow.getContext('2d');
      shc.setTransform(S,0,0,S,-left,-top);
      shc.fillStyle=side==='VL'?'rgba(29,1,11,0.34)':'rgba(1,5,31,0.34)';
      shc.fill(new Path2D(side==='VL'?'M410 184H465V201C447 201 431 205 410 209Z':'M490 168H540V185C522 184 503 188 490 191Z'));
      shc.setTransform(1,0,0,1,0,0);shc.globalCompositeOperation='destination-in';shc.drawImage(mask,0,0);
      await save(prefix+'Lid_CastShadow',await shadow.encode('png'),{left,top,width,height},'fixed-to-lid-shadow');
      // Composite highlights above the shadow; preserve each as its own PSD layer.
      const lightNames=[prefix+'Catchlight_Full',prefix+'LowerReflection_Full'];
      for(const name of lightNames){const index=layers.findIndex(l=>l.name===name);if(index>=0)layers.push(...layers.splice(index,1));}
    }
    for(const suffix of ['UpperLashes','LowerLid','UpperLid','OuterCorner']){
      const o=original.find(p=>p.id===prefix+suffix);assert(o?.file,prefix+suffix);
      await save(o.id,fs.readFileSync(path.join(base,o.file)),{left:o.left,top:o.top,width:o.width,height:o.height},'source-eyelid');
    }
  }
  // Raw import PSD intentionally keeps full irises; Cubism clipping must be wired after import.
  const raw=createCanvas(W,H),rc=raw.getContext('2d');
  for(const l of layers)if(!l.hidden)rc.drawImage(native[l.name].img,l.left,l.top);
  const children=['VR','VL'].map(side=>({name:'Eye_'+side+'_Set',opened:true,children:layers.filter(l=>l.name.startsWith('Eye_'+side+'_')&&!l.name.endsWith('Skin_Underpaint')).reverse()}));
  children.push({name:'00_Fixed_Skin_Underpaint',opened:false,children:layers.filter(l=>l.name.endsWith('Skin_Underpaint'))});
  const binary=psd.writePsdBuffer({width:W,height:H,bitsPerChannel:8,colorMode:3,imageData:rc.getImageData(0,0,W,H),children},{compress:true});
  fs.writeFileSync(path.join(dest,'hana-eye-motion-parts.psd'),binary);
  const decoded=psd.readPsd(binary,{useImageData:true,skipCompositeImageData:true,skipThumbnail:true}).children.flatMap(g=>g.children);
  assert.equal(decoded.length,layers.length);for(const l of decoded){const expected=layers.find(e=>e.name===l.name);assert.equal(l.left,expected.left);assert.equal(l.top,expected.top);assert.deepEqual(Buffer.from(l.imageData.data),Buffer.from(expected.imageData.data));}
  const region={left:1580,top:624,width:660,height:268},src=await sharp(source).extract(region).png().toBuffer(),face=await loadImage(src);
  function render(dx=0,dy=0,pupilOnly=false,groupX=0,groupY=0,useUnderpaint=!!(groupX||groupY)){
    const c=createCanvas(region.width,region.height),ctx=c.getContext('2d');ctx.drawImage(face,0,0);let empty=0;
    if(useUnderpaint)for(const side of ['VL','VR']){const l=native['Eye_'+side+'_Skin_Underpaint'];ctx.drawImage(l.img,l.left-region.left,l.top-region.top);}
    for(const side of ['VL','VR']){
      const prefix='Eye_'+side+'_',baseEye=native[prefix+'Sclera_Opening'],clip=native[prefix+'Aperture_Guide'];
      const eye=createCanvas(region.width,region.height),ec=eye.getContext('2d');
      ec.drawImage(baseEye.img,baseEye.left-region.left+groupX,baseEye.top-region.top+groupY);
      for(const suffix of ['Iris_Full','Pupil_Full','Lid_CastShadow','LowerReflection_Full','Catchlight_Full']){
        const part=native[prefix+suffix];if(!part)continue;
        if(suffix==='Lid_CastShadow'){
          const shadow=createCanvas(region.width,region.height),sc=shadow.getContext('2d'),iris=native[prefix+'Iris_Full'];
          sc.drawImage(part.img,part.left-region.left+groupX,part.top-region.top+groupY);
          sc.globalCompositeOperation='destination-in';sc.drawImage(iris.img,iris.left-region.left+groupX+(pupilOnly?0:dx),iris.top-region.top+groupY+(pupilOnly?0:dy));
          ec.drawImage(shadow,0,0);continue;
        }
        const moves=suffix!=='Lid_CastShadow'&&(!pupilOnly||suffix==='Pupil_Full');ec.drawImage(part.img,part.left-region.left+groupX+(moves?dx:0),part.top-region.top+groupY+(moves?dy:0));
      }
      ec.globalCompositeOperation='destination-in';ec.drawImage(clip.img,clip.left-region.left+groupX,clip.top-region.top+groupY);
      {
        const mask=clip.img,data=ec.getImageData(clip.left-region.left+groupX,clip.top-region.top+groupY,clip.width,clip.height).data;
        const temp=createCanvas(clip.width,clip.height),tc=temp.getContext('2d');tc.drawImage(mask,0,0);const alpha=tc.getImageData(0,0,clip.width,clip.height).data;
        for(let i=0;i<clip.width*clip.height;i++)if(alpha[i*4+3]===255&&data[i*4+3]<250)empty++;
      }
      ctx.drawImage(eye,0,0);
      for(const suffix of useUnderpaint?['OuterCorner','UpperLashes','LowerLid','UpperLid']:['UpperLashes']){const l=native[prefix+suffix];ctx.drawImage(l.img,l.left-region.left+groupX,l.top-region.top+groupY);}
    }
    for(const p of hair)ctx.drawImage(p.img,p.left-region.left,p.top-region.top);
    assert.equal(empty,0,'Transparent gaps in moved eyes');return c;
  }
  const states=[['NEUTRAL',0,0],['LOOK LEFT',-16,0],['LOOK RIGHT',16,0],['LOOK UP',0,-10],['LOOK DOWN',0,10],['PUPIL ONLY',8,0,true],['WHOLE EYES LEFT / UP',0,0,false,-6,-4],['WHOLE EYES RIGHT / DOWN',0,0,false,6,4]];
  const qa=createCanvas(1320,1200),qc=qa.getContext('2d');qc.fillStyle='#293846';qc.fillRect(0,0,qa.width,qa.height);
  for(const [i,[label,x,y,pupilOnly,gx,gy]]of states.entries()){const frame=render(x,y,pupilOnly,gx,gy),left=i%2*660,top=Math.floor(i/2)*300;qc.drawImage(frame,left,top+30);qc.fillStyle='#fff';qc.font='16px sans-serif';qc.fillText(label+' / 100%',left+12,top+22);}
  fs.writeFileSync(path.join(dest,'qa/gaze-test.png'),await qa.encode('png'));
  fs.writeFileSync(path.join(dest,'qa/neutral-native.png'),await render().encode('png'));
  if(painted){
    const comparison=createCanvas(region.width,3*(region.height+32)),cc=comparison.getContext('2d');cc.fillStyle='#293846';cc.fillRect(0,0,comparison.width,comparison.height);
    const rows=[['SOURCE / original face',face],['V1 / previous flat underpaint',await loadImage(path.join(legacy,'qa/neutral-native.png'))],['V2 / painted iris + separate eyelid shadow',render()]];
    for(const [i,[label,img]]of rows.entries()){const y=i*(region.height+32);cc.fillStyle='#fff';cc.font='16px sans-serif';cc.fillText(label+' / 100%',10,y+23);cc.drawImage(img,0,y+32);}
    fs.writeFileSync(path.join(dest,'qa/face-comparison.png'),await comparison.encode('png'));
  }
  // Animated raster test demonstrates alpha coverage, NOT Cubism mesh/deformer validation.
  const frames=[];for(const [dx,dy]of [[0,0],[-16,0],[0,0],[16,0],[0,-10],[0,10],[0,0]])frames.push(await sharp(await render(dx,dy).encode('png')).raw().toBuffer());
  await sharp(Buffer.concat(frames),{raw:{width:region.width,height:region.height*frames.length,channels:4,pageHeight:region.height}}).webp({lossless:true,loop:0,delay:frames.map(()=>650)}).toFile(path.join(dest,'qa/gaze-test.webp'));
  const whole=[];for(const [x,y]of [[0,0],[-6,-4],[0,0],[6,4],[0,0]])whole.push(await sharp(await render(0,0,false,x,y,true).encode('png')).raw().toBuffer());
  await sharp(Buffer.concat(whole),{raw:{width:region.width,height:region.height*whole.length,channels:4,pageHeight:region.height}}).webp({lossless:true,loop:0,delay:whole.map(()=>650)}).toFile(path.join(dest,'qa/whole-eye-test.webp'));
  const masterEntries=painted?['Iris','Pupil','Sclera','Catchlight','LowerReflection'].flatMap(name=>['VL','VR'].map(side=>[side+'_'+name,masters[side+'_'+name]])):Object.entries(masters);
  const columns=painted?2:3,cellWidth=1200/columns,board=createCanvas(1200,Math.ceil(masterEntries.length/columns)*300+50),bc=board.getContext('2d');bc.fillStyle='#2e4050';bc.fillRect(0,0,board.width,board.height);
  for(const [i,[id,buf]]of masterEntries.entries()){const img=await loadImage(buf),x=i%columns*cellWidth,y=Math.floor(i/columns)*300;const ratio=Math.min(1,246/img.height,(cellWidth-40)/img.width);bc.drawImage(img,x+(cellWidth-img.width*ratio)/2,y+10+(246-img.height*ratio)/2,img.width*ratio,img.height*ratio);bc.fillStyle='#fff';bc.font='16px sans-serif';bc.fillText(id+' / '+img.width+'×'+img.height+' native',x+12,y+283);}
  fs.writeFileSync(path.join(dest,'qa/underpaint-parts.png'),await board.encode('png'));
  manifest.checks={roundIrises:true,masterInteriorHoles:0,masterOuterGlowPixels:painted?null:0,antialiasedContours:true,motionCases:states.length,transparentGapsInOpening:0,psdRoundTrip:'PASS',layerCount:layers.length,separateLidShadows:painted};
  manifest.motionLimitsTested={irisXNativePixels:[-16,16],irisYNativePixels:[-10,10],pupilIndependentNativePixels:8,wholeEyeNativePixels:[[-6,-4],[6,4]]};
  manifest.notTested=['Cubism import and clipping','mesh deformation','blinking','large whole-eye movement'];
  manifest.visualReview={irisMasters:painted?'painted iris candidate; see face-comparison.png':'smooth complete circles',eyeLidBoundary:'INCOMPLETE',skinBoundary:'INCOMPLETE',wholeCharacterSeparation:'INCOMPLETE'};
  if(painted){
    const paired=['VL','VR'].map(side=>native['Eye_'+side+'_LowerReflection_Full']);
    assert.equal(paired[0].width,paired[1].width);assert.equal(paired[0].height,paired[1].height);
    assert.equal(layers.length,26,'V2 must include both lower reflections and independent lid shadows');
    manifest.checks.pairedLowerReflections=true;
    manifest.cubismClipping=['Clip iris, pupil and reflections to Sclera_Opening','Clip Lid_CastShadow to the same-side iris; attach its movement to eyelids, not iris'];
    manifest.visualReview.wholeEyeMovement='FAIL: visible skin and hair seams; do not treat as a finished moving eye group';
    manifest.visualReview.irisStyle='More internal color structure than V1, but not a pixel-identical reconstruction of the reference';
  }
  fs.writeFileSync(path.join(dest,'parts.json'),JSON.stringify(manifest,null,2)+'\n');console.log(JSON.stringify(manifest.checks,null,2));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
