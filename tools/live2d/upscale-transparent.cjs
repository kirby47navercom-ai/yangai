// Upscale color only; reuse the generated alpha, never infer a new background mask.
const path=require('node:path');
const fs=require('node:fs');
const assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const sharp=require('sharp');
const root=path.resolve(__dirname,'../..');
async function main() {
  const source=process.argv[2]?path.resolve(process.argv[2]):path.join(root,'assets/live2d/hana-v4/hana-clean-native.png');
  const output=path.join(path.dirname(source),'hana-clean-4x.png');
  assert.notEqual(source,output,'Source and output must be different');
  const temp=path.join(root,'.local-tools/live2d');
  const tool=path.join(root,'.local-tools/realesrgan-20220424');
  const meta=await sharp(source).metadata();
  assert(meta.hasAlpha,'Native source must already be transparent');
  assert.equal(meta.width,1024);assert.equal(meta.height,1536);
  fs.mkdirSync(temp,{recursive:true});
  await sharp(source).removeAlpha().png().toFile(path.join(temp,'clean-rgb.png'));
  execFileSync(path.join(tool,'realesrgan-ncnn-vulkan.exe'),['-i',path.join(temp,'clean-rgb.png'),'-o',path.join(temp,'clean-rgb-4x.png'),'-n','realesrgan-x4plus','-s','4','-t','256','-m',path.join(tool,'models'),'-f','png'],{windowsHide:true,stdio:'pipe'});
  const {data:rgb,info}=await sharp(path.join(temp,'clean-rgb-4x.png')).removeAlpha().raw().toBuffer({resolveWithObject:true});
  assert.equal(info.width,4096);assert.equal(info.height,6144);assert.equal(info.channels,3);
  const alpha=await sharp(source).extractChannel(3).resize(info.width,info.height).greyscale().raw().toBuffer();
  const rgba=Buffer.alloc(info.width*info.height*4);
  for(let i=0;i<alpha.length;i++){rgba[i*4]=rgb[i*3];rgba[i*4+1]=rgb[i*3+1];rgba[i*4+2]=rgb[i*3+2];rgba[i*4+3]=alpha[i];}
  await sharp(rgba,{raw:{width:info.width,height:info.height,channels:4}}).png().toFile(output);
  const savedAlpha=await sharp(output).extractChannel(3).raw().toBuffer();
  assert.deepEqual(savedAlpha,alpha,'Output alpha differs from resized native alpha');
  console.log('PASS: 4096x6144 RGBA; original generated alpha resized only, no segmentation');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
