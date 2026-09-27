// Read-only alpha/content verification. Never derive a mask or modify the source PNG.
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const sharp=require('sharp');

async function main() {
  assert(process.argv[2], 'Usage: node review-transparent.cjs path/to/image.png');
  const source=path.resolve(process.argv[2]),dest=path.join(path.dirname(source),'qa');
  const meta=await sharp(source).metadata();
  assert(meta.hasAlpha,'Generated image does not contain an alpha channel');
  const {data,info}=await sharp(source).ensureAlpha().raw().toBuffer({resolveWithObject:true});
  const {width,height}=info;
  let transparent=0,opaque=0,nearlyOpaque=0,partial=0,borderPixels=0;
  let left=width,top=height,right=-1,bottom=-1;
  for(let y=0;y<height;y++) for(let x=0;x<width;x++) {
    const a=data[(y*width+x)*4+3];
    if(a===0) {transparent++;continue;}
    if(a===255) opaque++;else partial++;
    if(a>=250) nearlyOpaque++;
    if(x===0||x===width-1||y===0||y===height-1) borderPixels++;
    left=Math.min(left,x);top=Math.min(top,y);right=Math.max(right,x);bottom=Math.max(bottom,y);
  }
  assert(transparent>width*height*.05,'No meaningful transparent background');
  // Generated alpha can peak at 253/254; report this rather than altering it.
  assert(nearlyOpaque>width*height*.05,'No meaningful nearly-opaque character content');
  fs.mkdirSync(dest,{recursive:true});
  for(const [name,background] of [['dark','#172433'],['light','#f0f0f0'],['blue','#126088']]) {
    await sharp(source).resize({width:1024,height:1536,fit:'inside',withoutEnlargement:true}).flatten({background}).png().toFile(path.join(dest,`preview-${name}.png`));
  }
  const checker=Buffer.alloc(width*height*3);
  for(let y=0;y<height;y++) for(let x=0;x<width;x++) {
    const value=(Math.floor(x/24)+Math.floor(y/24))%2?190:230,i=(y*width+x)*3;
    checker[i]=checker[i+1]=checker[i+2]=value;
  }
  await sharp(checker,{raw:{width,height,channels:3}}).composite([{input:source}]).png().toFile(path.join(dest,'checkerboard-preview.png'));
  for(const [name,box] of [
    ['head',[.25,0,.46,.25]],['waist',[.29,.30,.38,.25]],['tail',[.56,.42,.44,.34]],
  ]) {
    const region={left:Math.floor(width*box[0]),top:Math.floor(height*box[1]),width:Math.floor(width*box[2]),height:Math.floor(height*box[3])};
    await sharp(source).extract(region).flatten({background:'#126088'}).png().toFile(path.join(dest,`${name}-native.png`));
  }
  const report={file:path.basename(source),width,height,channels:info.channels,alpha:{transparent,opaque,nearlyOpaque,partial},borderPixels,contentBounds:{left,top,right,bottom},sourceAlpha:'preserved as generated; no matting, erosion, thresholding, or recoloring applied',limitations:['Generated interiors are mostly near-opaque (250..254), not exactly 255; no alpha normalization applied.','Alpha presence does not by itself verify every gap or preserve reference details; visual review required.','Flat illustration; not layered PSD or rig-ready Live2D model.']};
  fs.writeFileSync(path.join(dest,'report.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report,null,2));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
