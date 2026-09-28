// Register separately redrawn face/chest crops; preserve every pixel outside their bounds.
const path=require('node:path');
const fs=require('node:fs');
const assert=require('node:assert/strict');
const sharp=require('sharp');
const root=path.resolve(__dirname,'../..');
const dir=path.join(root,'assets/live2d/hana-v6');
// ponytail: fixed registration for this source pose; re-register for a different drawing.
const patches=[
  {file:'face-detail.png',x:360*4,y:82*4,size:256*4,crop:{left:0,top:0,width:256*4,height:242*4},fade:20,alpha:'detail'},
  {file:'chest-detail.png',x:455*4,y:349*4,size:176*4,crop:{left:59*4,top:37*4,width:60*4,height:121*4},fade:8,alpha:'base'},
];
async function main(){
  const source=path.join(root,'assets/live2d/hana-v5/hana-clean-4x.png');
  const {data:base,info}=await sharp(source).ensureAlpha().raw().toBuffer({resolveWithObject:true});
  assert.equal(info.width,4096);assert.equal(info.height,6144);assert.equal(info.channels,4);
  const out=Buffer.from(base);
  for(const p of patches){
    const {width,height}=p.crop;
    assert(p.x>=0&&p.y>=0&&p.x+width<=info.width&&p.y+height<=info.height);
    const file=path.join(dir,p.file),meta=await sharp(file).metadata();
    assert(meta.hasAlpha&&meta.width===meta.height&&meta.width>=p.size,'Detail crop must be square, RGBA and large enough');
    const detail=await sharp(file).resize(p.size,p.size).extract(p.crop).ensureAlpha().raw().toBuffer();
    for(let y=0;y<height;y++)for(let x=0;x<width;x++){
      const t=Math.min(1,Math.min(x,y,width-1-x,height-1-y)/p.fade);
      if(t<=0)continue;
      const w=t*t*(3-2*t),i=((p.y+y)*info.width+p.x+x)*4,j=(y*width+x)*4;
      // Retain the solid tie's source alpha; the face redraw carries its own hair-gap alpha.
      const a=(p.alpha==='base'?base[i+3]:detail[j+3])*w,b=out[i+3]*(1-w),alpha=a+b;
      for(let c=0;c<3;c++)out[i+c]=alpha?Math.round((detail[j+c]*a+out[i+c]*b)/alpha):0;
      out[i+3]=Math.round(alpha);
    }
  }
  let outsideChanges=0,changedPixels=0;
  for(let y=0;y<info.height;y++)for(let x=0;x<info.width;x++){
    const i=(y*info.width+x)*4;
    if(out[i]===base[i]&&out[i+1]===base[i+1]&&out[i+2]===base[i+2]&&out[i+3]===base[i+3])continue;
    changedPixels++;
    if(!patches.some(p=>x>=p.x&&x<p.x+p.crop.width&&y>=p.y&&y<p.y+p.crop.height))outsideChanges++;
  }
  assert.equal(outsideChanges,0,'Untargeted source pixels changed');
  assert(changedPixels>0,'No edits were applied');
  const cloth=patches.find(p=>p.alpha==='base');
  for(let y=cloth.y;y<cloth.y+cloth.crop.height;y++)for(let x=cloth.x;x<cloth.x+cloth.crop.width;x++)assert.equal(out[(y*info.width+x)*4+3],base[(y*info.width+x)*4+3],'Solid cloth alpha changed');
  const output=path.join(dir,'hana-refined-4k.png');
  await sharp(out,{raw:info}).png().toFile(output);
  assert.deepEqual(await sharp(output).raw().toBuffer(),out,'PNG round-trip changed RGBA pixels');
  const qa=path.join(dir,'qa');fs.mkdirSync(qa,{recursive:true});
  for(const [name,box] of [['face',{left:385*4,top:142*4,width:188*4,height:147*4}],['chest',{left:432*4,top:323*4,width:99*4,height:153*4}]]){
    for(const [version,file] of [['before',source],['after',output]])await sharp(file).extract(box).flatten({background:'#126088'}).png().toFile(path.join(qa,`${name}-${version}-100pct.png`));
  }
  for(const [name,background]of [['blue','#126088'],['light','#f0f0f0'],['dark','#172433']])await sharp(output).resize(1024,1536).flatten({background}).png().toFile(path.join(qa,`refined-${name}.png`));
  await sharp(output).extract({left:340*4,top:60*4,width:296*4,height:302*4}).flatten({background:'#126088'}).png().toFile(path.join(qa,'face-seams-100pct.png'));
  const report={base:'../hana-v5/hana-clean-4x.png',output:'hana-refined-4k.png',width:info.width,height:info.height,patches,changedPixels,outsideChanges,clothAlphaUnchanged:'PASS',rgbaRoundTrip:'PASS',note:'Localized high-resolution redraws; the rest is a 4x upscaled source. Not a layered PSD.'};
  fs.writeFileSync(path.join(qa,'detail-report.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report,null,2));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
