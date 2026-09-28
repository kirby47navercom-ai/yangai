const fs=require('node:fs');
const path=require('node:path');
const sharp=require('sharp');
const {createCanvas,loadImage}=require('@napi-rs/canvas');
const variant=process.argv[2]||'hana-v6-parts';
if(!/^hana-v6-[a-z-]+$/.test(variant))throw new Error('Invalid variant');
const root=path.resolve(__dirname,'../..'),dest=path.join(root,'assets/live2d',variant,'references');
async function main(){
  fs.mkdirSync(dest,{recursive:true});
  for(const [name,x,y,w,h,step]of [['head',270,0,450,375,25],['torso',275,270,400,290,25],['skirt',270,475,420,380,25],['left-arm',100,330,295,550,25],['right-arm',575,330,275,550,25],['legs-boots',310,795,350,741,50],['tail',580,650,444,510,25],['face-close',385,140,200,145,10],['hands-close',100,685,750,200,25],['head-top',330,5,285,150,10],['bow-close',425,310,130,65,10],['torso-close',350,310,265,220,10]]){
    const scale=step===10?4:2;
    const img=await sharp(path.join(root,'assets/live2d/hana-v6/hana-refined-4k.png')).extract({left:x*4,top:y*4,width:w*4,height:h*4}).resize(w*scale,h*scale).flatten({background:'#344453'}).png().toBuffer();
    const c=createCanvas(w*scale,h*scale),ctx=c.getContext('2d');ctx.drawImage(await loadImage(img),0,0);ctx.font='16px sans-serif';ctx.lineWidth=1;
    for(let n=Math.ceil(x/step)*step;n<x+w;n+=step){const px=(n-x)*scale;ctx.strokeStyle='#63d4ba66';ctx.beginPath();ctx.moveTo(px,0);ctx.lineTo(px,h*scale);ctx.stroke();ctx.fillStyle='#15322a';ctx.fillRect(px,0,34,20);ctx.fillStyle='#fff';ctx.fillText(String(n),px+2,16);}
    for(let n=Math.ceil(y/step)*step;n<y+h;n+=step){const py=(n-y)*scale;ctx.strokeStyle='#63d4ba66';ctx.beginPath();ctx.moveTo(0,py);ctx.lineTo(w*scale,py);ctx.stroke();ctx.fillStyle='#15322a';ctx.fillRect(0,py,42,20);ctx.fillStyle='#fff';ctx.fillText(String(n),2,py+16);}
    fs.writeFileSync(path.join(dest,name+'.png'),await c.encode('png'));
  }
}
main().catch(e=>{console.error(e);process.exitCode=1;});
