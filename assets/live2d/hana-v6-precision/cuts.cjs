// Precision pass keeps the original pixels and closes whole-part contours.
const old=require('../hana-v6-parts/cuts.cjs');
const defs=old.filter(d=>!d.id.startsWith('Eye_')&&d.group!=='14_FrontHair'&&!d.id.includes('LowerCurl')).map(d=>({...d}));
for(const d of defs){
  delete d.refine;
  if(!d.base&&!d.boundary)delete d.within;
  if(!d.review&&!d.boundary&&!d.stroke&&!['Tail_Root','Hair_CrownBack','Leg_VL_Upper','Leg_VR_Upper'].includes(d.id))d.refine={method:'edge',radius:12,spacing:72};
  if(d.id==='Mouth'||d.id.startsWith('Brow_'))d.refine=old.find(o=>o.id===d.id).refine;
  if(d.id.startsWith('Skirt_Emblem'))d.refine={method:'material',color:'gold',radius:1};
  if(d.id==='Cuff_VL')d.refine={method:'material',color:'red',radius:1};
  if(d.id==='Cuff_VR')d.refine={method:'material',color:'blue',radius:1};
  if(d.id==='Face'||d.id==='Neck')d.refine={method:'material',color:'skin',radius:2};
}
const add=(group,id,d,radius=4,of)=>defs.push({group,id,d,refine:{method:'edge',radius,spacing:24},...(of?{of}:{} )});
const oval=(x,y,rx,ry)=>`M${x-rx} ${y}a${rx} ${ry} 0 1 0 ${rx*2} 0a${rx} ${ry} 0 1 0 -${rx*2} 0Z`;
const material=(group,id,d,color,of)=>defs.push({group,id,d,refine:{method:'material',color,radius:1},...(of?{of}:{} )});
// Each hair piece retains its highlights and shadow interior; no white/color erasure.
material('12_Hair','Pony_VL_White_Outer','M375 94Q345 132 317 164Q288 189 269 178Q276 199 305 191Q337 176 367 124Z','white');
material('12_Hair','Pony_VL_White_Middle','M375 98Q345 133 327 168Q310 196 323 224Q342 250 373 243L382 235Q371 251 351 251Q320 250 309 226Q300 205 322 162Z','white');
material('12_Hair','Pony_VL_White_Lower','M313 181Q300 226 321 247Q347 273 375 259L382 253Q368 275 343 269Q311 265 307 238Q299 215 313 181Z','white');
material('12_Hair','Pony_VL_Red_OuterCurl','M329 182Q288 221 294 257Q295 279 326 278L337 271Q315 285 294 275Q267 258 287 224Z','red',['Pony_VL']);
material('12_Hair','Pony_VL_Red_MiddleCurl','M327 249Q359 281 349 313Q340 342 307 339Q280 334 282 307L290 297Q284 318 308 322Q334 328 337 306Q342 285 320 264Z','red',['Pony_VL']);
material('12_Hair','Pony_VL_Red_BottomCurl','M356 295Q369 318 349 341Q328 361 309 340Q309 364 338 374Q357 372 369 350L385 318Z','red',['Pony_VL']);
material('12_Hair','Pony_VR_White_Outer','M587 70Q634 85 669 124Q698 158 713 183L716 181Q714 202 689 190Q669 163 650 131Q620 93 587 70Z','white');
material('12_Hair','Pony_VR_White_Middle','M602 83Q652 118 670 155Q698 197 680 237Q671 261 642 277Q618 293 642 316L651 319Q622 327 609 296Q601 278 622 258Q666 230 659 199Q663 155 629 116Z','white');
material('12_Hair','Pony_VR_White_Curl','M642 179Q662 227 633 240Q613 250 598 241L590 235Q607 255 630 250Q655 244 655 214Z','white');
material('12_Hair','Pony_VR_Blue_OuterCurl','M680 186Q713 214 695 247Q683 264 661 255Q695 258 696 231Q698 211 680 202Z','blue',['Pony_VR']);
material('12_Hair','Pony_VR_Blue_MiddleCurl','M643 254Q623 281 642 299Q664 313 679 289Q681 316 657 326Q630 326 617 298Q606 273 643 254Z','blue',['Pony_VR']);
material('12_Hair','Pony_VR_Blue_BottomCurl','M622 290Q631 325 663 330Q685 333 700 305Q704 330 684 343Q664 357 643 335Q649 361 679 354L685 342Q687 369 657 369Q636 365 625 341L611 312Z','blue',['Pony_VR']);
material('14_FrontHair','Hair_VL_Outer','M454 63Q414 49 391 82Q350 123 357 177Q360 221 396 249Q414 267 455 269L450 256L424 236L444 229L425 211L414 194L430 129Z','white');
material('14_FrontHair','Hair_VL_InnerBang','M455 68Q418 78 402 112Q386 150 408 199Q415 190 421 153Q416 112 455 68Z','white',['Hair_VL_Outer']);
material('14_FrontHair','Hair_VL_CheekUpper','M379 184Q397 215 438 224Q423 230 406 218L387 205Z','white',['Hair_VL_Outer']);
material('14_FrontHair','Hair_VL_CheekMiddle','M386 207Q407 235 442 234Q433 245 413 234L396 221Z','white',['Hair_VL_Outer']);
material('14_FrontHair','Hair_VL_CheekLower','M397 230Q416 254 450 261Q428 270 410 248Z','white',['Hair_VL_Outer']);
material('14_FrontHair','Hair_VR_Outer','M462 61Q496 51 527 72Q574 93 591 150Q609 212 575 244L537 255Q555 238 560 214L548 171L520 131L478 82Z','white');
material('14_FrontHair','Hair_VR_InnerBang','M462 66Q501 62 532 104Q548 129 541 171Q514 160 497 125Q480 84 462 66Z','white',['Hair_VR_Outer']);
material('14_FrontHair','Hair_VR_CheekUpper','M539 118Q552 163 542 195Q536 206 524 211Q545 212 555 191Q568 156 539 118Z','white',['Hair_VR_Outer']);
material('14_FrontHair','Hair_VR_CheekMiddle','M554 135Q570 178 551 211Q540 223 523 226Q548 228 568 203Q578 173 554 135Z','white',['Hair_VR_Outer']);
material('14_FrontHair','Hair_VR_CheekLower','M572 155Q587 200 564 234L536 248Q559 249 579 224Q592 193 572 155Z','white',['Hair_VR_Outer']);
material('14_FrontHair','Forelock_Red','M457 66Q491 71 512 130Q523 169 499 189L516 200L480 211Q431 195 417 153Q415 114 457 66Z','red');
material('14_FrontHair','Forelock_Blue','M459 69Q441 102 447 124Q456 148 483 152Q461 158 445 147Q454 161 477 164Q459 173 445 165Q454 175 480 173Q441 187 419 159Q404 140 416 112Q430 83 459 69Z','blue');
add('14_FrontHair','Hair_Ahoge','M444 14Q473 5 476 28Q476 13 458 15Q437 22 437 40Q437 51 454 61Q428 58 420 39Q414 22 444 14Z',5);
// Forelock tips are articulated bundles cut at their painted overlaps.
add('14_FrontHair','Forelock_Blue_TipUpper','M440 134Q451 150 481 151Q457 158 440 143Z',3,['Forelock_Blue']);
add('14_FrontHair','Forelock_Blue_TipMiddle','M428 144Q442 164 476 163Q460 175 441 160Z',3,['Forelock_Blue']);
add('14_FrontHair','Forelock_Blue_TipLower','M424 154Q444 176 478 172Q446 185 428 165Z',3,['Forelock_Blue']);
add('15_Eye_VL','Eye_VL_Sclera','M419.6 203.5Q434 197.3 456 199.4L456.4 206.6Q443 210 432.6 213.6Q424.8 212 419.6 203.5Z',4);
add('15_Eye_VL','Eye_VL_Iris','M432.8 199.4Q444.5 197.8 455.2 199.5L456 206.6Q447 209 439.5 211Q433.3 207.2 432.8 199.4Z',4,['Eye_VL_Sclera']);
add('15_Eye_VL','Eye_VL_Iris_UpperShade','M432 198H457V202.9Q445 200.6 434 205Z',2,['Eye_VL_Iris']);
add('15_Eye_VL','Eye_VL_Pupil','M441.9 198.7Q444.6 197.7 445.5 201.2Q447 207 443.8 205Q441.9 203.7 441.9 198.7Z',3,['Eye_VL_Iris','Eye_VL_Iris_UpperShade']);
add('15_Eye_VL','Eye_VL_Catchlight',oval(443.2,200.65,.82,.82),2,['Eye_VL_Iris','Eye_VL_Iris_UpperShade','Eye_VL_Pupil']);
add('15_Eye_VL','Eye_VL_OuterCorner','M409.7 202.8L419.8 202.7Q422 209 428 212.1Q419.5 210.7 409.7 202.8Z',4);
add('15_Eye_VL','Eye_VL_UpperLashes','M409.2 202.4L414.7 200.7L410.3 198.4Q414.8 199.3 417.4 198.3L418.7 197.1L416.2 194.9Q422 196.6 430.6 194.1L427.1 191.3L432.3 193.8Q437.7 193.0 442.9 193.6L442.5 191.7L446.1 193.9Q452.7 194.3 456 197.2L460.8 200.5Q454.8 198.3 433.5 199.5Q425.6 201.3 419.3 204.1L414.4 204.8Z',3);
add('15_Eye_VL','Eye_VL_LowerLid','M431.8 213.8Q443.7 208.3 457.7 206.5L457.3 207.2Q443 209.9 431.1 214.8Z',2);
add('15_Eye_VL','Eye_VL_UpperLid','M420 194Q438 188 452.8 193.9Q439.5 187.4 420 193.3Z',2);

add('15_Eye_VR','Eye_VR_Sclera','M493.3 190.5Q513.1 179.2 536.8 180L535.5 185Q532.7 190.1 527.3 192.5Q510.3 194.4 495.4 196.1Z',4);
add('15_Eye_VR','Eye_VR_Iris','M503.8 184Q513 179.9 525.8 179.8Q527.9 185.3 524.4 192.4L506.2 194.5Q503.5 190.8 503.8 184Z',4,['Eye_VR_Sclera']);
add('15_Eye_VR','Eye_VR_Iris_UpperShade','M503 179H528V186.1Q515 185.1 504 189Z',2,['Eye_VR_Iris']);
add('15_Eye_VR','Eye_VR_Pupil','M513.1 182.5Q515.2 181.3 516.3 184.9Q517.5 190.1 515.3 189.3Q513.2 188 513.1 182.5Z',3,['Eye_VR_Iris','Eye_VR_Iris_UpperShade']);
add('15_Eye_VR','Eye_VR_Catchlight',oval(514.65,185.05,.93,1.03),2,['Eye_VR_Iris','Eye_VR_Iris_UpperShade','Eye_VR_Pupil']);
add('15_Eye_VR','Eye_VR_LowerReflection',oval(515.5,191.75,2.35,1.8),3,['Eye_VR_Iris']);
add('15_Eye_VR','Eye_VR_OuterCorner','M536.5 180L541.8 178.5Q540.2 186.2 528.3 192.1Q534.5 188.8 536.5 180Z',4);
add('15_Eye_VR','Eye_VR_UpperLashes','M492.2 192Q496.8 184.4 505.5 180.1L514.2 176.5L514.6 174.2L515.3 177.2Q521.8 176.4 525 173.5L525.5 170.9L525.1 175.1Q534.5 174.6 540.8 171L540.4 173.6L539.2 175.1Q542.7 176.7 545.8 175.3L542.5 179.1Q516.4 178.1 497.7 187.5Z',3);
add('15_Eye_VR','Eye_VR_LowerLid','M502.9 194.8Q514 191.9 528.9 192.5L530.1 192.8Q513 193.4 501.4 195.7Z',2);
add('15_Eye_VR','Eye_VR_UpperLid','M493.1 184.5Q506.4 174.6 523.1 173.4Q509 173.2 493.1 184Z',2);
for(const d of defs)if(d.id.endsWith('_UpperLashes'))d.refine={color:'ink',radius:8};
module.exports=defs;
