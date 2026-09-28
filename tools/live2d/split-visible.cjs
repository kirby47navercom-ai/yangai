// Visible-pixel decomposition only. Occluded surfaces must be painted before deformation.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const sharp=require('sharp');
const {createCanvas,Path2D,StrokeCap,StrokeJoin,loadImage}=require('@napi-rs/canvas');
const psd=require('ag-psd');
psd.initializeCanvas(createCanvas,(width,height)=>({width,height,data:new Uint8ClampedArray(width*height*4)}));
const root=path.resolve(__dirname,'../..'),variant=process.argv[2]||'hana-v6-parts';
assert(/^hana-v6-[a-z-]+$/.test(variant),'Invalid output variant');
const dest=path.join(root,'assets/live2d',variant);
const W=4096,H=6144,S=4,hash=b=>crypto.createHash('sha256').update(b).digest('hex');
function raster(d){
  let p=new Path2D(d.d);if(d.stroke)p=p.stroke({width:d.stroke,cap:StrokeCap.Round,join:StrokeJoin.Round});
  const [x0,y0,x1,y1]=p.computeTightBounds();
  const margin=d.refine?Math.max(32,(d.refine.radius||12)+4):1;
  const left=Math.max(0,Math.floor(x0*S)-margin),top=Math.max(0,Math.floor(y0*S)-margin);
  const width=Math.min(W,Math.ceil(x1*S)+margin)-left,height=Math.min(H,Math.ceil(y1*S)+margin)-top;
  assert(width>0&&height>0,d.id);
  const c=createCanvas(width,height),ctx=c.getContext('2d');ctx.setTransform(S,0,0,S,-left,-top);ctx.fillStyle='#fff';ctx.fill(p);
  return {left,top,width,height,data:ctx.getImageData(0,0,width,height).data};
}
async function main(){
  const defs=require(path.join(dest,'cuts.cjs'));
  assert(new Set(defs.map(d=>d.id)).size===defs.length,'Duplicate layer ID');
  const sourceFile=path.join(root,'assets/live2d/hana-v6/hana-refined-4k.png'),sourceBytes=fs.readFileSync(sourceFile);
  assert.equal(hash(sourceBytes),'f91e25e12a870c202511d97912caa3ed196563a6e8052a314b0f965ab571e00a','Source changed: retrace masks');
  const {data:source,info}=await sharp(sourceBytes).ensureAlpha().raw().toBuffer({resolveWithObject:true});
  assert.equal(info.width,W);assert.equal(info.height,H);assert.equal(info.channels,4);
  const owners=new Uint16Array(W*H),domains=new Uint16Array(W*H),masks=defs.map(raster);
  const scratch=path.join(root,'.local-tools/live2d',variant+'-masks'),jobs=[];
  fs.mkdirSync(scratch,{recursive:true});
  for(const [n,d]of defs.entries())if(d.refine){
    const m=masks[n],mask=path.join(scratch,d.id+'-mask.png'),img=path.join(scratch,d.id+'-source.png'),result=path.join(scratch,d.id+'-refined.png');
    await sharp(Buffer.from(m.data),{raw:{width:m.width,height:m.height,channels:4}}).png().toFile(mask);
    await sharp(sourceBytes).extract({left:m.left,top:m.top,width:m.width,height:m.height}).png().toFile(img);
    jobs.push({id:d.id,mask,image:img,result,...d.refine});
  }
  if(jobs.length){
    const jobFile=path.join(scratch,'jobs.json');fs.writeFileSync(jobFile,JSON.stringify(jobs));
    const run=require('node:child_process').spawnSync('python',[path.join(__dirname,'refine-visible.py'),jobFile],{windowsHide:true,encoding:'utf8'});
    assert.equal(run.status,0,run.stderr||run.error?.message);console.log(run.stdout);
    for(const job of jobs)masks[defs.findIndex(d=>d.id===job.id)].data=await sharp(job.result).raw().toBuffer();
  }
  const ids=new Map(defs.map((d,i)=>[d.id,i+1]));
  for(const pass of ['base','detail'])defs.forEach((d,n)=>{
    if((d.base?'base':'detail')!==pass)return;
    const m=masks[n],allowed=d.within?d.within.map(id=>{assert(ids.has(id),id);return ids.get(id);}):null;
    const parents=d.of?d.of.map(id=>{assert(ids.has(id),id);return ids.get(id);}):null;
    for(let y=0;y<m.height;y++)for(let x=0;x<m.width;x++){
      const i=(y+m.top)*W+x+m.left;
      if(!source[i*4+3]||m.data[(y*m.width+x)*4+3]<128||(allowed&&!allowed.includes(domains[i]))||(parents&&!parents.includes(owners[i])))continue;
      owners[i]=n+1;if(d.base)domains[i]=n+1;
    }
  });
  let unassigned=0,foreground=0;for(let i=0;i<owners.length;i++)if(source[i*4+3]){foreground++;if(!owners[i])unassigned++;}
  assert.equal(unassigned,0,'Foreground missing from all masks');
  fs.mkdirSync(path.join(dest,'parts'),{recursive:true});fs.mkdirSync(path.join(dest,'qa'),{recursive:true});
  const composite=Buffer.alloc(source.length),layers=[],parts=[];
  for(let n=0;n<defs.length;n++){
    const d=defs[n],m=masks[n];let left=W,top=H,right=-1,bottom=-1,pixels=0,solidPixels=0;
    for(let y=0;y<m.height;y++)for(let x=0;x<m.width;x++){
      const px=x+m.left,py=y+m.top,i=py*W+px;if(owners[i]!==n+1)continue;
      left=Math.min(left,px);top=Math.min(top,py);right=Math.max(right,px);bottom=Math.max(bottom,py);pixels++;if(source[i*4+3]>=250)solidPixels++;
    }
    if(!pixels){parts.push({id:d.id,group:d.group,status:'empty-needs-review',pixels:0});continue;}
    const width=right-left+1,height=bottom-top+1,data=Buffer.alloc(width*height*4);
    for(let y=0;y<height;y++)for(let x=0;x<width;x++){
      const i=(y+top)*W+x+left,j=(y*width+x)*4;if(owners[i]!==n+1)continue;
      source.copy(data,j,i*4,i*4+4);data.copy(composite,i*4,j,j+4);
    }
    const file='parts/'+d.id+'.png';await sharp(data,{raw:{width,height,channels:4}}).png().toFile(path.join(dest,file));
    assert.deepEqual(await sharp(path.join(dest,file)).raw().toBuffer(),data,'PNG round-trip: '+d.id);
    layers.push({name:d.id,left,top,opacity:1,blendMode:'normal',imageData:{width,height,data:new Uint8ClampedArray(data)}});
    parts.push({id:d.id,group:d.group,file,left,top,width,height,pixels,solidPixels,status:d.review?'review-residue':'visible-draft-needs-boundary-review',hiddenSurface:'not-reconstructed',boundaryType:d.boundary||(d.refine?'manual-guide-with-local-segmentation':'manual-guide'),sha256:hash(fs.readFileSync(path.join(dest,file)))});
  }
  let mismatch=0;for(let i=0;i<owners.length;i++){
    if(composite[i*4+3]!==source[i*4+3])mismatch++;
    else if(source[i*4+3]&&[0,1,2].some(k=>composite[i*4+k]!==source[i*4+k]))mismatch++;
  }
  assert.equal(mismatch,0,'Visible RGBA reassembly differs');
  await sharp(composite,{raw:info}).png().toFile(path.join(dest,'assembled.png'));
  const children=[...new Set(defs.map(d=>d.group))].reverse().map(group=>({name:group,opened:false,children:layers.filter(l=>defs.find(d=>d.id===l.name).group===group).reverse()}));
  const binary=psd.writePsdBuffer({width:W,height:H,bitsPerChannel:8,colorMode:3,imageData:{width:W,height:H,data:new Uint8ClampedArray(composite)},children},{compress:true});
  fs.writeFileSync(path.join(dest,'hana-visible-parts.psd'),binary);
  const decoded=psd.readPsd(binary,{useImageData:true,skipCompositeImageData:true,skipThumbnail:true});
  const actual=decoded.children.flatMap(g=>g.children);assert.equal(actual.length,layers.length);
  for(const layer of actual){const expected=layers.find(l=>l.name===layer.name);assert.equal(layer.left,expected.left);assert.equal(layer.top,expected.top);assert.deepEqual(Buffer.from(layer.imageData.data),Buffer.from(expected.imageData.data));}
  const actualFiles=fs.readdirSync(path.join(dest,'parts')).filter(x=>x.endsWith('.png')).sort();
  assert.deepEqual(actualFiles,parts.filter(p=>p.file).map(p=>path.basename(p.file)).sort(),'Stale part PNGs; preserve/remove explicitly');
  const report={source:'../hana-v6/hana-refined-4k.png',sourceSHA256:hash(sourceBytes),canvas:[W,H],foregroundPixels:foreground,unassignedPixels:unassigned,reassemblyMismatchPixels:mismatch,actualLayers:layers.length,emptyMasks:parts.filter(p=>!p.file).map(p=>p.id),residuePixels:parts.filter(p=>p.status==='review-residue').reduce((s,p)=>s+p.pixels,0),psdRoundTrip:'PASS',psdBytes:binary.length,hiddenSurfacesReconstructed:0,semanticBoundaryReview:'INCOMPLETE',fineSeparationComplete:false,rigReady:false,cubismImportTested:false};
  fs.writeFileSync(path.join(dest,'parts.json'),JSON.stringify({canvas:[W,H],coordinates:'1024x1536 paths scaled 4x; PNG origins in native pixels',parts},null,2)+'\n');
  fs.writeFileSync(path.join(dest,'qa/report.json'),JSON.stringify(report,null,2)+'\n');
  // False-color ownership makes wrong cut assignments visible, not just the successful reconstruction.
  const map=Buffer.alloc(W*H*4);for(let i=0;i<owners.length;i++){const n=owners[i];if(!n)continue;map[i*4]=(n*73)%205+50;map[i*4+1]=(n*137)%205+50;map[i*4+2]=(n*193)%205+50;map[i*4+3]=source[i*4+3];}
  await sharp(map,{raw:info}).resize(1024,1536).flatten({background:'#26313c'}).png().toFile(path.join(dest,'qa/ownership.png'));
  for(const [name,bg]of [['light','#eee'],['dark','#273443']])await sharp(composite,{raw:info}).resize(1024,1536).flatten({background:bg}).png().toFile(path.join(dest,'qa/assembled-'+name+'.png'));
  const visible=parts.filter(p=>p.file);
  for(let page=0;page*20<visible.length;page++){
    const c=createCanvas(1440,1350),ctx=c.getContext('2d');ctx.fillStyle='#344453';ctx.fillRect(0,0,c.width,c.height);
    for(const [i,p]of visible.slice(page*20,page*20+20).entries()){
      const x=i%4*360,y=Math.floor(i/4)*270,buf=await sharp(path.join(dest,p.file)).resize({width:340,height:220,fit:'inside'}).png().toBuffer(),img=await loadImage(buf);
      ctx.drawImage(img,x+(360-img.width)/2,y+8+(220-img.height)/2);ctx.fillStyle='#fff';ctx.font='14px sans-serif';ctx.fillText(p.id,x+8,y+247);ctx.fillStyle='#b5c7d6';ctx.fillText(p.width+'x'+p.height+' @ '+p.left+','+p.top,x+8,y+265);
    }
    fs.writeFileSync(path.join(dest,'qa/contact-'+String(page+1).padStart(2,'0')+'.png'),await c.encode('png'));
  }
  console.log(JSON.stringify(report,null,2));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
