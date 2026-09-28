const fs=require('node:fs'),path=require('node:path'),sharp=require('sharp');
const {createCanvas,loadImage}=require('@napi-rs/canvas');
const root=path.resolve(__dirname,'../..'),dest=path.join(root,'assets/live2d/hana-v6-precision');
async function main(){
  const prefix=process.argv[2]||'Eye_',defs=require(path.join(dest,'cuts.cjs')).filter(d=>d.id.startsWith(prefix));
  const c=createCanvas(1400,Math.ceil(defs.length/4)*290),ctx=c.getContext('2d');ctx.fillStyle='#283747';ctx.fillRect(0,0,c.width,c.height);
  for(const [i,d]of defs.entries()){
    const file=path.join(dest,'parts',d.id+'.png');if(!fs.existsSync(file))continue;
    const meta=await sharp(file).metadata();
    const buf=await sharp(file).resize({width:320,height:230,fit:'inside',withoutEnlargement:true}).png().toBuffer(),img=await loadImage(buf),x=i%4*350,y=Math.floor(i/4)*290;
    ctx.drawImage(img,x+(350-img.width)/2,y+6+(230-img.height)/2);ctx.font='16px sans-serif';ctx.fillStyle='#fff';ctx.fillText(d.id,x+6,y+263);
    ctx.font='12px sans-serif';ctx.fillStyle='#b8c9d8';ctx.fillText(meta.width+' x '+meta.height+' px / '+Math.round(img.width/meta.width*100)+'% (no enlargement)',x+6,y+283);
  }
  fs.mkdirSync(path.join(dest,'qa'),{recursive:true});fs.writeFileSync(path.join(dest,'qa',prefix.replace(/[^a-z0-9]/gi,'')+'-details.png'),await c.encode('png'));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
