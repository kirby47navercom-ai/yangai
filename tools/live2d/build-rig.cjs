// Portable source preparation; native model export uses UmamoHana.kt.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const sharp=require('sharp'),{createCanvas,loadImage}=require('@napi-rs/canvas'),psd=require('ag-psd');
psd.initializeCanvas(createCanvas,(w,h)=>({width:w,height:h,data:new Uint8ClampedArray(w*h*4)}));
const root=path.resolve(__dirname,'../..'),dest=path.join(root,'assets/live2d/hana-v7-rig');
const W=4096,H=6144,S=4,read=f=>JSON.parse(fs.readFileSync(f,'utf8'));
const bones=[];
function bone(id,parent,x,y,param,range=6){bones.push({id,parent,pivot:[x*S,y*S],parameter:param,range,inputRange:param==='ParamAngleZ'?30:param==='ParamBodyAngleZ'?10:1});return id;}
bone('Root',null,483,780,'ParamRootZ',2);
bone('Body','Root',483,505,'ParamBodyAngleZ',4);
bone('Head','Body',490,266,'ParamAngleZ',6);
for(const [s,sx,ex,wx,hx,legx,kx,ax]of [['VL',380,310,238,203,430,422,446],['VR',591,652,737,763,560,573,577]]){
  bone('Arm_'+s,'Body',sx,344,'ParamArm'+s,5);
  bone('Forearm_'+s,'Arm_'+s,ex,550,'ParamForearm'+s,6);
  bone('Wrist_'+s,'Forearm_'+s,wx,735,'ParamWrist'+s,5);
  bone('Hand_'+s,'Wrist_'+s,hx,780,'ParamHand'+s,3);
  bone('Thigh_'+s,'Root',legx,817,'ParamLeg'+s,2);
  bone('Shin_'+s,'Thigh_'+s,kx,1027,'ParamKnee'+s,2);
  bone('Foot_'+s,'Shin_'+s,ax,1258,'ParamAnkle'+s,3);
  bone('Pony_'+s,'Head',s==='VL'?375:589,108,'ParamHair'+s,4);
  bone('Skirt_'+s,'Body',s==='VL'?423:542,530,'ParamSkirt'+s,2);
  bone('Jacket_'+s,'Body',s==='VL'?413:560,335,'ParamJacket'+s,1.5);
  bone('Cape_'+s,'Body',s==='VL'?418:555,283,'ParamCape'+s,2);
}
bone('Tail_Base','Root',595,875,'ParamTailBase',2);
bone('Tail_Lower','Tail_Base',716,1040,'ParamTailLower',2);
bone('Tail_Rise','Tail_Lower',902,1080,'ParamTailRise',2);
bone('Tail_Tip','Tail_Rise',942,943,'ParamTailTip',3);
bone('Bow','Body',486,334,'ParamBow',2);
bone('Tie','Body',484,349,'ParamTie',2);
const detailBones=new Map();
function assigned(p){
  const id=p.id,s=id.includes('_VL')?'VL':'VR';
  if(id.startsWith('Tail_'))return ({Tail_Root:'Tail_Base',Tail_LowerArc:'Tail_Lower',Tail_RisingArc:'Tail_Rise',Tail_TipWithTransition:'Tail_Tip'})[id];
  if(id.startsWith('Leg_'))return /Lower|Opening/.test(id)?'Shin_'+s:'Thigh_'+s;
  if(id.startsWith('Boot_'))return 'Foot_'+s;
  if(id.startsWith('Hand_'))return 'Hand_'+s;
  if(id.startsWith('Cuff_'))return 'Wrist_'+s;
  if(/^(Sleeve|ArmBand|Shoulder)/.test(id))return /Lower|Ribbon|Coin|SleeveGem/.test(id)?'Forearm_'+s:'Arm_'+s;
  if(id.startsWith('Jacket_')||id==='Chest_Brooch')return 'Jacket_'+s;
  if(id.startsWith('Cape_'))return 'Cape_'+s;
  if(id.startsWith('Skirt_')&&!id.includes('Emblem')&&id!=='Skirt_Center')return 'Skirt_'+s;
  if(id.startsWith('Bow_'))return 'Bow';
  if(id.startsWith('Necktie'))return 'Tie';
  if(/^(Eye_|Brow_|HairClip_)/.test(id)||['Face','Neck','Nose','Mouth','Hair_CrownBack'].includes(id))return 'Head';
  if(id.startsWith('Pony_'))return 'Pony_'+s;
  if(/^(Hair_|Forelock_)/.test(id))return 'Head';
  return 'Body';
}
function makeSpec(parts){
  for(const p of parts){
    p.bone=assigned(p);assert(p.bone,p.id);
    if(/^(Pony_.*(Curl|Middle|Lower)|Hair_(?!Crown)|Forelock_|Pendant_.*Cord|Hip_.*RedLoop|Sleeve_.*Tassel|Boot_.*Tassel)/.test(p.id)){
      const id='Detail_'+p.id;
      // The top of each existing lock/accessory is the articulation origin, not its center.
      const [x,y,w,h]=p.articulationBounds||[p.left,p.top,p.width,p.height];
      bone(id,p.bone,(x+w*.5)/S,(y+16)/S,'ParamSway_'+p.id,/Hair|Forelock|Pony/.test(p.id)?3:2);
      detailBones.set(p.id,id);p.bone=id;
    }
  }
  const ids=new Set(bones.map(b=>b.id));assert.equal(ids.size,bones.length);
  for(const b of bones){if(b.parent)assert(ids.has(b.parent),b.parent);let seen=new Set(),q=b;while(q){assert(!seen.has(q.id),'Bone cycle');seen.add(q.id);q=bones.find(b=>b.id===q.parent);}}
  return {canvas:[W,H],coordinates:'PSD native pixels; rotation hierarchy used by UmamoHana.kt',bones,parts:parts.map(p=>({id:p.id,bone:p.bone,file:p.file,left:p.left,top:p.top,width:p.width,height:p.height})),nativeModelCreated:false};
}
async function prepare(){
  const manifest=read(path.join(dest,'parts.json')),parts=manifest.parts,spec=makeSpec(parts),layers=[];
  const c=createCanvas(W,H),ctx=c.getContext('2d');
  for(const p of parts){const file=path.join(dest,p.file),{data,info}=await sharp(file).ensureAlpha().raw().toBuffer({resolveWithObject:true});layers.push({name:p.id,left:p.left,top:p.top,opacity:1,blendMode:'normal',imageData:{width:info.width,height:info.height,data:new Uint8ClampedArray(data)}});ctx.drawImage(await loadImage(file),p.left,p.top);}
  const groups=[...new Set(parts.map(p=>p.group))];
  const children=[...groups.reverse().map(g=>({name:g,opened:false,children:layers.filter(l=>parts.find(p=>p.id===l.name).group===g).reverse()}))];
  // Native full circular eye masters are retained for the gaze pass, not shown as unclipped discs.
  const eyeBase=path.join(root,'assets/live2d/hana-v6-precision/eye-motion-v2');
  const eyeParts=read(path.join(eyeBase,'parts.json')).parts.filter(p=>p.left!==undefined&&p.kind!=='guide');
  const eyeLayers=[];
  for(const p of eyeParts){const {data,info}=await sharp(path.join(eyeBase,p.file)).raw().toBuffer({resolveWithObject:true});eyeLayers.push({name:'Master_'+p.id,left:p.left,top:p.top,opacity:0,hidden:true,imageData:{width:info.width,height:info.height,data:new Uint8ClampedArray(data)}});}
  children.unshift({name:'98_EyeMotionMasters',opened:false,children:eyeLayers.reverse()});
  const composite=ctx.getImageData(0,0,W,H);
  const binary=psd.writePsdBuffer({width:W,height:H,bitsPerChannel:8,colorMode:3,imageData:composite,children},{compress:true});
  fs.writeFileSync(path.join(dest,'hana-rig-source.psd'),binary);
  const decoded=psd.readPsd(binary,{useImageData:true,skipCompositeImageData:true,skipThumbnail:true});
  const all=decoded.children.flatMap(g=>g.children);assert.equal(all.length,layers.length+eyeLayers.length);
  assert.equal(new Set(all.map(a=>a.name)).size,all.length,'Duplicate PSD names');
  for(const l of layers){const actual=all.find(a=>a.name===l.name);assert(Buffer.from(actual.imageData.data).equals(Buffer.from(l.imageData.data)),l.name+': PSD pixels changed');assert.equal(actual.left,l.left);assert.equal(actual.top,l.top);}
  fs.writeFileSync(path.join(dest,'rig.json'),JSON.stringify(spec,null,2)+'\n');
  const preview=`<!doctype html><html lang="ko"><meta charset="utf-8"><title>하나 — 전신 관절 초안</title><style>body{margin:0;background:#202a36;color:#eee;font:16px sans-serif;display:flex}aside{width:240px;padding:16px;position:fixed;overflow:auto;height:96vh}main{margin-left:280px}canvas{height:96vh;max-width:calc(100vw - 290px);object-fit:contain}label{display:block;margin:16px 0}input{width:210px}p{font-size:13px;line-height:1.6;color:#bcc8d5}</style><aside><h2>하나 관절 초안</h2><p>분리 PNG에 회전 계층을 적용한 미리보기예요. 이 페이지는 PNG 관절 미리보기예요. 편집 가능한 모델은 umamo/hana.cmo3에 따로 저장돼요. 큰 각도에서 생기는 빈틈은 재작화가 필요해요.</p><button id="reset">초기화</button><label><input id="play" type="checkbox">자동 움직임</label><label><input id="skeleton" type="checkbox">관절 표시</label><div id="controls"></div></aside><main><canvas id="view" width="2048" height="3072"></canvas></main><script>
const rig=${JSON.stringify(spec)},canvas=document.getElementById('view'),ctx=canvas.getContext('2d'),values={},images=new Map(),byId=new Map(rig.bones.map(b=>[b.id,b]));
for(const [label,test]of [['머리',b=>b.id==='Head'],['몸',b=>b.id==='Body'],['팔',b=>/^Arm_|^Forearm_/.test(b.id)],['손목',b=>/^Wrist_|^Hand_/.test(b.id)],['다리',b=>/^Thigh_|^Shin_/.test(b.id)],['머리카락',b=>/^Pony_|^Detail_(Hair|Pony|Forelock)/.test(b.id)],['옷·장식',b=>/^Skirt_|^Jacket_|^Cape_|^Bow$|^Tie$|^Detail_(?!Hair|Pony|Forelock)/.test(b.id)],['꼬리',b=>/^Tail_/.test(b.id)]]){const l=document.createElement('label');l.textContent=label;const input=document.createElement('input');input.type='range';input.min=-1;input.max=1;input.step=.01;input.value=0;input.oninput=()=>{for(const b of rig.bones)if(test(b))values[b.id]=+input.value;draw()};l.append(input);document.getElementById('controls').append(l)}
function chain(id){const out=[];for(let b=byId.get(id);b;b=byId.get(b.parent))out.unshift(b);return out}
function transform(id){for(const b of chain(id)){ctx.translate(...b.pivot);ctx.rotate((values[b.id]||0)*b.range*Math.PI/180);ctx.translate(-b.pivot[0],-b.pivot[1])}}
function draw(){ctx.setTransform(.5,0,0,.5,0,0);ctx.clearRect(0,0,4096,6144);for(const p of rig.parts){ctx.save();transform(p.bone);ctx.drawImage(images.get(p.id),p.left,p.top);ctx.restore()}if(document.getElementById('skeleton').checked){ctx.strokeStyle='#80e4ab';ctx.lineWidth=8;for(const b of rig.bones){ctx.save();transform(b.id);ctx.beginPath();ctx.arc(...b.pivot,12,0,Math.PI*2);ctx.stroke();ctx.restore()}}}
document.getElementById('skeleton').onchange=draw;document.getElementById('reset').onclick=()=>{for(const b of rig.bones)values[b.id]=0;for(const input of document.querySelectorAll('input[type=range]'))input.value=0;document.getElementById('play').checked=false;draw()};
Promise.all(rig.parts.map(p=>new Promise((resolve,reject)=>{const img=new Image;img.onload=()=>{images.set(p.id,img);resolve()};img.onerror=reject;img.src=p.file}))).then(()=>{draw();const start=performance.now();function tick(){if(document.getElementById('play').checked){const t=(performance.now()-start)/1000;for(const b of rig.bones)values[b.id]=Math.sin(t*(b.id.includes('Detail')?1.8:1.0)+b.pivot[0]/700)*.3;draw()}requestAnimationFrame(tick)}tick()}).catch(()=>document.getElementById('controls').textContent='PNG를 불러오지 못했어요. preview.html과 parts 폴더를 함께 보관해 주세요.');
</script></html>`;
  fs.writeFileSync(path.join(dest,'preview.html'),preview);
  fs.writeFileSync(path.join(dest,'neutral.png'),await c.encode('png'));
  const qa=createCanvas(1536,1536),qc=qa.getContext('2d');qc.fillStyle='#26313c';qc.fillRect(0,0,1536,1536);qc.drawImage(c,256,0,1024,1536);
  qc.lineWidth=2;qc.strokeStyle='#72dfa3';
  for(const b of bones){const x=b.pivot[0]/4+256,y=b.pivot[1]/4;if(b.parent){const parent=bones.find(p=>p.id===b.parent);qc.beginPath();qc.moveTo(parent.pivot[0]/4+256,parent.pivot[1]/4);qc.lineTo(x,y);qc.stroke();}qc.beginPath();qc.arc(x,y,3,0,Math.PI*2);qc.stroke();}
  fs.writeFileSync(path.join(dest,'qa/skeleton.png'),await qa.encode('png'));
  for(let page=0;page*20<parts.length;page++){const contact=createCanvas(1440,1350),cx=contact.getContext('2d');cx.fillStyle='#344453';cx.fillRect(0,0,1440,1350);for(const [i,p]of parts.slice(page*20,page*20+20).entries()){const buf=await sharp(path.join(dest,p.file)).resize({width:340,height:220,fit:'inside'}).png().toBuffer(),img=await loadImage(buf),x=i%4*360,y=Math.floor(i/4)*270;cx.drawImage(img,x+(360-img.width)/2,y+10+(220-img.height)/2);cx.fillStyle='#fff';cx.font='14px sans-serif';cx.fillText(p.id,x+8,y+248);}fs.writeFileSync(path.join(dest,'qa/contact-'+String(page+1).padStart(2,'0')+'.png'),await contact.encode('png'));}
  console.log(JSON.stringify({parts:parts.length,bones:bones.length,eyeMotionMasters:eyeLayers.length,psdLayers:all.length,psdRoundTrip:'PASS',psdBytes:binary.length}));
}
prepare().catch(e=>{console.error(e);process.exitCode=1;});
