// Reuse accepted 4K parts; add only the hidden whites of the eyes and speaking/effect overlays.
const fs=require('node:fs'),path=require('node:path'),sharp=require('sharp');
const {createCanvas}=require('@napi-rs/canvas');
const root=path.resolve(__dirname,'../..'),base=path.join(root,'assets/live2d/hana-v7-rig'),dest=path.join(root,'assets/live2d/hana-v8-live');
async function main(){
  fs.mkdirSync(path.join(dest,'parts'),{recursive:true});fs.mkdirSync(path.join(dest,'qa'),{recursive:true});
  const manifest=JSON.parse(fs.readFileSync(path.join(base,'parts.json'))),parts=manifest.parts.map(p=>({...p,file:'../hana-v7-rig/'+p.file}));
  for(const side of ['VL','VR']){
    const p=parts.find(p=>p.id===`Eye_${side}_Sclera`),{data,info}=await sharp(path.join(dest,p.file)).ensureAlpha().raw().toBuffer({resolveWithObject:true});
    for(const q of parts.filter(q=>q.id.startsWith(`Eye_${side}_`)&&/Iris|Pupil|Catchlight|Reflection/.test(q.id))){
      const {data:rgba,info:qi}=await sharp(path.join(dest,q.file)).ensureAlpha().raw().toBuffer({resolveWithObject:true});
      for(let y=0;y<qi.height;y++)for(let x=0;x<qi.width;x++){
        const ox=q.left+x-p.left,oy=q.top+y-p.top,i=(y*qi.width+x)*4;
        if(ox<0||oy<0||ox>=info.width||oy>=info.height||!rgba[i+3])continue;
        const j=(oy*info.width+ox)*4;
        if(data[j+3]<rgba[i+3]){data[j]=247;data[j+1]=248;data[j+2]=253;data[j+3]=rgba[i+3];}
      }
    }
    p.file=`parts/${p.id}.png`;await sharp(data,{raw:{width:info.width,height:info.height,channels:4}}).png().toFile(path.join(dest,p.file));
  }
  if(!process.argv[2])throw Error('Pass the generated transparent mouth PNG');
  const mouth=await sharp(process.argv[2]).trim({threshold:5}).resize(118,44,{fit:'fill'}).png().toBuffer();
  await sharp(mouth).toFile(path.join(dest,'parts/Mouth_Open.png'));
  parts.push({id:'Mouth_Open',group:'16_FaceDetails',file:'parts/Mouth_Open.png',left:1887,top:913,width:118,height:44,defaultOpacity:0,articulationBounds:[1887,913,118,44]});
  // A small clean tear overlay, not a replacement eye or a generic circular iris.
  for(const [side,x,y]of [['VL',1752,842],['VR',2047,773]]){
    const c=createCanvas(22,88),ctx=c.getContext('2d'),g=ctx.createLinearGradient(0,0,22,0);
    g.addColorStop(0,'rgba(80,152,208,.65)');g.addColorStop(.45,'rgba(220,246,255,.82)');g.addColorStop(1,'rgba(102,174,232,.55)');
    ctx.fillStyle=g;ctx.beginPath();ctx.moveTo(6,2);ctx.bezierCurveTo(4,25,10,41,3,61);ctx.bezierCurveTo(-3,91,24,91,18,62);ctx.bezierCurveTo(11,38,17,21,15,2);ctx.closePath();ctx.fill();
    ctx.strokeStyle='rgba(250,253,255,.9)';ctx.lineWidth=1.4;ctx.beginPath();ctx.moveTo(10,12);ctx.bezierCurveTo(8,34,13,51,7,72);ctx.stroke();
    const id=`Eye_${side}_Tear`,file=`parts/${id}.png`;fs.writeFileSync(path.join(dest,file),await c.encode('png'));
    parts.push({id,group:'16_FaceDetails',file,left:x,top:y,width:22,height:88,defaultOpacity:0,articulationBounds:[x,y,22,88]});
  }
  fs.writeFileSync(path.join(dest,'parts.json'),JSON.stringify({...manifest,parts,rigReady:false,source:'../hana-v7-rig/parts.json'},null,2)+'\n');
  console.log(`Prepared ${parts.length} parts; 189 reused PNGs, 2 eye white fills, speaking mouth and 2 tears`);
}
main().catch(e=>{console.error(e);process.exitCode=1;});
