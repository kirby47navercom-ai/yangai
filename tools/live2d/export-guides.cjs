// Closed object contours, not exclusive visible-pixel ownership or nearest-neighbor residues.
const fs=require('node:fs'),path=require('node:path');
const {createCanvas,Path2D,StrokeCap,StrokeJoin}=require('@napi-rs/canvas');
const root=path.resolve(__dirname,'../..'),out=path.join(root,'.local-tools/live2d/semantic-guides');
fs.mkdirSync(out,{recursive:true});
const records=[];
for(const d of require(path.join(root,'assets/live2d/hana-v6-precision/cuts.cjs'))){
  if(d.review)continue;
  let p=new Path2D(d.d);if(d.stroke)p=p.stroke({width:d.stroke,cap:StrokeCap.Round,join:StrokeJoin.Round});
  const [a,b,c,e]=p.computeTightBounds(),x=Math.max(0,Math.floor(a*4)-4),y=Math.max(0,Math.floor(b*4)-4);
  const w=Math.min(4096,Math.ceil(c*4)+4)-x,h=Math.min(6144,Math.ceil(e*4)+4)-y;
  const canvas=createCanvas(w,h),ctx=canvas.getContext('2d');ctx.setTransform(4,0,0,4,-x,-y);ctx.fillStyle='#fff';ctx.fill(p);
  fs.writeFileSync(path.join(out,d.id+'.png'),canvas.toBuffer('image/png'));
  records.push({id:d.id,group:d.group,left:x,top:y,width:w,height:h,material:d.refine?.color||null});
}
fs.writeFileSync(path.join(out,'guides.json'),JSON.stringify(records,null,2)+'\n');
console.log('Closed semantic guides:',records.length);
