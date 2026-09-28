const fs=require('node:fs'),path=require('node:path'),sharp=require('sharp');
const {createCanvas,loadImage}=require('@napi-rs/canvas');
const root=path.resolve(__dirname,'../..'),dest=path.join(root,'assets/live2d/hana-v6-precision/references');
async function main(){
  fs.mkdirSync(dest,{recursive:true});
  for(const [name,x,y,w,h,step,k]of [['eye-left',395,182,72,42,5,12],['eye-right',490,160,65,43,5,12],['white-hair',350,45,250,235,10,4],['left-ponytail',280,85,150,290,10,4],['right-ponytail',570,55,150,320,10,4],['cuff-left',175,680,110,90,5,8],['cuff-right',690,680,100,90,5,8]]){
    const img=await sharp(path.join(root,'assets/live2d/hana-v6/hana-refined-4k.png')).extract({left:x*4,top:y*4,width:w*4,height:h*4}).resize(w*k,h*k,{kernel:'nearest'}).flatten({background:'#293849'}).png().toBuffer();
    const c=createCanvas(w*k,h*k),ctx=c.getContext('2d');ctx.drawImage(await loadImage(img),0,0);ctx.font='15px sans-serif';
    for(let n=Math.ceil(x/step)*step;n<x+w;n+=step){const u=(n-x)*k;ctx.strokeStyle='#2ccdb666';ctx.beginPath();ctx.moveTo(u,0);ctx.lineTo(u,h*k);ctx.stroke();ctx.fillStyle='#122e29';ctx.fillRect(u,0,34,19);ctx.fillStyle='#fff';ctx.fillText(String(n),u+1,15);}
    for(let n=Math.ceil(y/step)*step;n<y+h;n+=step){const v=(n-y)*k;ctx.strokeStyle='#2ccdb666';ctx.beginPath();ctx.moveTo(0,v);ctx.lineTo(w*k,v);ctx.stroke();ctx.fillStyle='#122e29';ctx.fillRect(0,v,34,19);ctx.fillStyle='#fff';ctx.fillText(String(n),1,v+15);}
    fs.writeFileSync(path.join(dest,name+'.png'),await c.encode('png'));
  }
}
main().catch(e=>{console.error(e);process.exitCode=1;});
