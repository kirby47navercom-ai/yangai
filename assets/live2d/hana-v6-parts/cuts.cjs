// V6 source coordinates / 1024x1536. VL and VR mean viewer left and right.
// Visible-pixel draft: no invented hidden surfaces, no resampling of the original.
const p=[];
const box=(x,y,w,h)=>`M${x} ${y}h${w}v${h}h-${w}Z`;
const oval=(x,y,rx,ry)=>`M${x-rx} ${y}a${rx} ${ry} 0 1 0 ${rx*2} 0a${rx} ${ry} 0 1 0 -${rx*2} 0Z`;
const base=(group,id,d)=>p.push({group,id,d,base:true});
const cut=(group,id,within,d,stroke,boundary)=>p.push({group,id,d,within:Array.isArray(within)?within:[within],...(stroke?{stroke}:{}),...(boundary?{boundary}:{})});
const ellipse=(group,id,within,x,y,rx,ry)=>cut(group,id,within,oval(x,y,rx,ry));
base('00_Review','Review_EdgeResidue',box(0,0,1024,1536));p[0].review=true;
base('01_Tail','Tail_Root',box(580,640,444,520));
base('02_Legs','Leg_VL_Upper',box(310,790,179,485));
base('02_Legs','Leg_VR_Upper','M490 790H624Q610 861 589 929Q572 981 582 1012Q606 1065 618 1100Q627 1135 620 1199L620 1279H540L485 1100Z');
base('03_Boots','Boot_VL_Main','M399 1262Q403 1248 416 1247L461 1245Q477 1244 480 1255L508 1536H375V1350Z');
base('03_Boots','Boot_VR_Main','M555 1252Q588 1235 628 1251L654 1536H516L527 1320L524 1265Z');
base('05_Sleeves','Sleeve_VL_Main','M380 326L420 470L397 561L344 654L298 724L253 748L159 725L117 601L251 489L300 403Z');
base('05_Sleeves','Sleeve_VR_Main','M582 326L664 402L714 490L826 601L811 729L704 752L639 702L583 564L553 470Z');
base('06_Hands','Hand_VL','M178 716Q210 716 248 742L212 791L210 877H102V790Z');
base('06_Hands','Hand_VR','M735 721L769 727L795 766L841 831L839 868L781 881L746 842L738 799L712 747Z');
base('07_Cuffs','Cuff_VL','M194 687Q232 687 269 712L281 729L270 748Q263 753 245 739L214 726L181 719Z');
base('07_Cuffs','Cuff_VR','M707 711Q735 690 763 690L776 728Q755 726 722 746L708 754Q702 755 698 747L693 731Z');
base('04_Skirt','Skirt_Center','M410 505H549Q575 542 594 577L674 786L634 807L540 834L410 834L311 804L275 782L356 579Q386 535 410 505Z');
base('08_Torso','Inner_Bodice','M436 319H530L552 477H409Z');
base('08_Torso','Waist_Corset','M410 472Q476 461 552 473L556 517H412Z');
base('09_Jacket','Jacket_VL','M380 325Q425 320 475 336Q439 383 445 470Q396 477 357 500Q362 410 380 325Z');
base('09_Jacket','Jacket_VR','M493 337Q543 320 590 326L603 500Q562 477 514 470Q520 387 493 337Z');
base('09_Jacket','Jacket_VL_InsideHem','M358 500Q381 487 399 485L404 515Q369 515 358 506Z');
base('09_Jacket','Jacket_VR_InsideHem','M547 485Q581 491 602 500L600 506Q580 514 546 515Z');
base('12_Hair','Hair_CrownBack',box(255,0,480,275));
base('12_Hair','Pony_VL','M370 75L405 145L433 276L393 304L373 333L339 375L282 348L275 297L275 178Z');
base('12_Hair','Pony_VR','M570 68L637 64L733 181L722 320L697 371L642 381L588 291L577 231Z');
base('10_Cape','Cape_VL','M346 307Q363 277 399 274Q437 274 482 320L487 333Q456 331 421 329L390 326Q372 327 354 346Q349 340 346 329Z');
base('10_Cape','Cape_VR','M523 283Q560 271 582 277Q611 282 630 314L648 356Q616 328 593 327L558 330L486 334L481 323Z');
base('11_Neck','Collar','M454 270Q478 264 511 268Q535 268 537 277L529 293Q506 309 486 326Q472 309 461 301L454 289Z');
// Tail sections follow deformation joints, not an artificial saw-toothed fur boundary.
cut('01_Tail','Tail_LowerArc','Tail_Root','M580 887Q708 986 843 993L829 1160H580Z',0,'planned-joint');
cut('01_Tail','Tail_RisingArc','Tail_Root','M843 993Q928 1006 1024 935V1160H829Z',0,'planned-joint');
cut('01_Tail','Tail_TipWithTransition','Tail_Root','M780 640H1024V935Q936 1004 859 945L829 893Z',0,'planned-joint');
cut('02_Legs','Leg_VL_Lower','Leg_VL_Upper',box(310,1025,179,250),0,'planned-joint');
cut('02_Legs','Leg_VR_Lower','Leg_VR_Upper',box(485,1025,160,260),0,'planned-joint');
// Boot opening skin stays with its leg; rings, straps and ornaments remain separate.
cut('02_Legs','Leg_VL_Opening','Boot_VL_Main','M412 1241H473V1260Q452 1273 438 1274Q422 1269 415 1267Z');
cut('02_Legs','Leg_VR_Opening','Boot_VR_Main','M561 1241H621V1266Q589 1280 569 1274Z');
cut('03_Boots','Boot_VL_Sole','Boot_VL_Main','M399 1465Q446 1495 509 1460V1536H375Z');
cut('03_Boots','Boot_VR_Sole','Boot_VR_Main','M520 1463Q568 1498 649 1466V1536H516Z');
cut('03_Boots','Boot_VL_Toe','Boot_VL_Main','M414 1445Q417 1420 445 1421Q480 1422 496 1445L508 1460Q451 1492 409 1467Z');
cut('03_Boots','Boot_VR_Toe','Boot_VR_Main','M538 1437Q566 1417 598 1430L628 1450L647 1466Q582 1497 529 1466Z');
cut('03_Boots','Boot_VL_UpperStrap','Boot_VL_Main','M402 1273Q435 1294 481 1271L482 1298Q439 1310 407 1293Z');
cut('03_Boots','Boot_VL_LowerStrap','Boot_VL_Main','M406 1296Q440 1316 482 1299L483 1323Q441 1340 409 1317Z');
cut('03_Boots','Boot_VR_UpperStrap','Boot_VR_Main','M530 1275Q578 1297 627 1276L627 1301Q578 1317 531 1298Z');
cut('03_Boots','Boot_VR_LowerStrap','Boot_VR_Main','M531 1300Q578 1321 627 1303L627 1327Q580 1345 531 1322Z');
for(const [s,par,x,y]of [['VL','Boot_VL_Main',431,1290],['VR','Boot_VR_Main',606,1297]]){
  ellipse('20_Hardware',`Boot_${s}_UpperGem`,par,x,y,8,9);
  ellipse('20_Hardware',`Boot_${s}_LowerGem`,par,x+(s==='VL'?3:-1),y+22,8,9);
}
cut('20_Hardware','Boot_VL_Flower','Boot_VL_Main','M397 1281Q408 1272 414 1288Q429 1280 430 1296Q431 1310 417 1305Q417 1325 406 1318Q393 1321 398 1304Q384 1291 397 1281Z');
cut('20_Hardware','Boot_VR_Flower','Boot_VR_Main','M616 1288Q630 1272 634 1292Q645 1282 643 1298Q642 1304 635 1305Q648 1318 640 1325Q634 1327 628 1315Q628 1335 617 1321L613 1309Q602 1305 606 1297Z');
cut('20_Hardware','Boot_VL_Tassel','Boot_VL_Main','M401 1311L414 1315Q418 1342 419 1369Q400 1377 384 1366Z');
cut('20_Hardware','Boot_VR_Tassel','Boot_VR_Main','M624 1318L636 1322L652 1371Q640 1383 622 1378Z');
// Cloth panel boundaries retain the red/blue/white hems as fabric.
cut('04_Skirt','Skirt_VL_Outer','Skirt_Center','M410 512L421 522Q394 583 377 641L303 798L272 785Z');
cut('04_Skirt','Skirt_VR_Outer','Skirt_Center','M549 512L537 523Q568 583 584 641L649 800L678 786Z');
cut('04_Skirt','Skirt_VL_Panel','Skirt_Center','M429 525L434 528L416 666L376 825L310 810L353 657Z');
cut('04_Skirt','Skirt_VR_Panel','Skirt_Center','M524 525L518 528L538 666L582 826L644 810L601 657Z');
cut('04_Skirt','Skirt_VL_RedInset','Skirt_Center','M413 681L417 684L416 819L385 816Z');
cut('04_Skirt','Skirt_VR_BlueInset','Skirt_Center','M539 682L547 681L572 817L537 820Z');
cut('04_Skirt','Skirt_VL_FrontPiping','Skirt_Center','M410 698L420 697L385 823L375 822Z');
cut('04_Skirt','Skirt_VR_FrontPiping','Skirt_Center','M547 697L554 697L583 824L573 825Z');
for(const [i,x,y]of [[1,457,559],[2,507,559],[3,455,598],[4,509,598],[5,453,637],[6,510,637]]){
  cut('21_SkirtDecor',`Skirt_Emblem_${i}`,'Skirt_Center',`M${x-3} ${y-8}Q${x+1} ${y-13} ${x+4} ${y-7}Q${x+12} ${y-9} ${x+10} ${y-2}Q${x+15} ${y+3} ${x+8} ${y+6}Q${x+8} ${y+12} ${x+2} ${y+9}Q${x-2} ${y+14} ${x-6} ${y+7}Q${x-12} ${y+8} ${x-10} ${y+1}Q${x-14} ${y-4} ${x-7} ${y-6}Z`);
}
for(const [s,x]of [['VL',413],['VR',545]]){
  cut('21_SkirtDecor',`Pendant_${s}_Cord`,'Skirt_Center',`M${s==='VL'?429:526} 549L${x} 649`,2.2);
  cut('21_SkirtDecor',`Pendant_${s}_Flower`,'Skirt_Center',`M${x} 645Q${x+10} 650 ${x+6} 661Q${x+21} 650 ${x+25} 657Q${x+25} 667 ${x+10} 670Q${x+25} 678 ${x+15} 686Q${x+6} 684 ${x} 675Q${x-12} 689 ${x-20} 682Q${x-21} 674 ${x-8} 668Q${x-23} 662 ${x-20} 653Q${x-11} 651 ${x-5} 659Q${x-9} 650 ${x} 645Z`);
  cut('21_SkirtDecor',`Pendant_${s}_Drop`,'Skirt_Center',`M${x-1} 676Q${x-14} 693 ${x-7} 698Q${x+5} 706 ${x+7} 693Z`);
}
for(const [s,x]of [['VL',440],['VR',518]]){
  ellipse('20_Hardware',`Hip_${s}_Ring`,'Skirt_Center',x,533,13,15);
  cut('20_Hardware',`Hip_${s}_Chain`,'Skirt_Center',s==='VL'?'M435 545L424 562':'M526 545L536 562',5);
}
cut('21_SkirtDecor','Hip_VL_RedLoop','Skirt_Center','M402 575Q378 581 353 590Q345 594 352 609Q380 625 424 580L417 566Z');
cut('21_SkirtDecor','Hip_VR_RedLoop','Skirt_Center','M550 574Q580 582 607 594L612 607Q590 626 533 580L539 566Z');
ellipse('20_Hardware','Hip_VL_Clasp','Skirt_Center',428,565,8.5,9);ellipse('20_Hardware','Hip_VR_Clasp','Skirt_Center',539,566,8.5,9);
cut('08_Torso','Waist_UpperBelt','Waist_Corset','M451 477H509V498H451Z');
cut('08_Torso','Waist_LowerBelt','Waist_Corset','M451 499H509V521H451Z');
for(const [i,x,y]of [[1,452,488],[2,510,488],[3,452,511],[4,510,511]])ellipse('20_Hardware',`Waist_Button_${i}`,'Waist_Corset',x,y,8,9.5);
cut('08_Torso','Necktie','Inner_Bodice','M478 346L490 346L497 463Q483 465 468 463L468 441Z');
cut('08_Torso','Necktie_WhiteBand','Inner_Bodice',box(468,442.5,29,6));
cut('08_Torso','Necktie_BlueBand','Inner_Bodice',box(468,437,29,5.5)+box(468,448.5,29,8.5));
cut('08_Torso','Necktie_RedBand','Inner_Bodice',box(468,457,29,6));
cut('09_Jacket','Jacket_VL_Pocket','Jacket_VL','M375 401L423 389L424 453L374 470Z');
cut('09_Jacket','Jacket_VR_Pocket','Jacket_VR','M530 389L589 401L589 470L529 453Z');
cut('09_Jacket','Jacket_VL_PocketFlap','Jacket_VL','M375 390L432 377L429 397L376 410Z');
cut('09_Jacket','Jacket_VR_PocketFlap','Jacket_VR','M529 377L589 391L589 410L531 397Z');
cut('20_Hardware','Jacket_VL_Zip','Jacket_VL','M375 390Q399 380 431 378',4.5);
cut('20_Hardware','Jacket_VR_Zip','Jacket_VR','M532 378L589 391',4.5);
cut('20_Hardware','Jacket_VL_Cord','Jacket_VL','M396 418L392 483',5.5);
cut('20_Hardware','Jacket_VR_Cord','Jacket_VR','M570 418L568 483',5.5);
cut('20_Hardware','Jacket_VL_Badge','Jacket_VL','M395 400L405 410Q408 416 400 419Q395 427 388 421Q379 418 385 410Z');
cut('20_Hardware','Jacket_VR_Badge','Jacket_VR','M568 400L581 413Q581 420 574 421Q569 428 562 421Q554 418 559 410Z');
ellipse('20_Hardware','Chest_Brooch','Jacket_VR',550,357,12,10.5);
cut('05_Sleeves','Sleeve_VL_Lower','Sleeve_VL_Main','M264 531Q313 545 355 582L330 760H110V590Z',0,'planned-joint');
cut('05_Sleeves','Sleeve_VR_Lower','Sleeve_VR_Main','M692 531Q645 547 609 583L638 760H840V590Z',0,'planned-joint');
cut('18_ArmDetails','ArmBand_VL','Sleeve_VL_Main','M309 404Q333 417 370 405L366 441Q322 451 297 435L292 428Z');
cut('18_ArmDetails','ArmBand_VR','Sleeve_VR_Main','M592 405Q635 417 667 408L679 440Q647 461 595 443Z');
cut('18_ArmDetails','Shoulder_VL_RedStrap','Sleeve_VL_Main','M368 325L381 331L318 415L304 410Z');
cut('18_ArmDetails','Shoulder_VR_RedStrap','Sleeve_VR_Main','M595 327L608 325L658 411L643 415Z');
cut('20_Hardware','Shoulder_VL_Buckle','Sleeve_VL_Main','M328 382L345 388L339 402L320 396Z');
cut('20_Hardware','Shoulder_VR_Buckle','Sleeve_VR_Main','M628 389L645 382L651 398L634 404Z');
ellipse('20_Hardware','ArmBand_VL_Gem','Sleeve_VL_Main',313,427,8,11);ellipse('20_Hardware','ArmBand_VR_Gem','Sleeve_VR_Main',657,432,9,11);
cut('18_ArmDetails','SleevePocket_VL','Sleeve_VL_Main','M295 463L328 479L303 521L268 511Z');
cut('18_ArmDetails','SleevePocket_VR','Sleeve_VR_Main','M668 466L638 480L659 522L700 513Z');
cut('18_ArmDetails','SleeveFlap_VL','Sleeve_VL_Main','M294 444L324 454L312 479L278 477L270 468Z');
cut('18_ArmDetails','SleeveFlap_VR','Sleeve_VR_Main','M670 444L638 454L651 480L684 479L694 469Z');
cut('20_Hardware','Sleeve_VL_Cord','Sleeve_VL_Main','M290 474Q278 490 279 509Q291 501 300 495',4);
cut('20_Hardware','Sleeve_VR_Cord','Sleeve_VR_Main','M673 477Q686 491 687 511L667 497',4);
ellipse('20_Hardware','Sleeve_VL_Medallion','Sleeve_VL_Main',267,518,13.5,16);ellipse('20_Hardware','Sleeve_VR_Medallion','Sleeve_VR_Main',693,521,13.5,16);
cut('18_ArmDetails','Sleeve_VL_Tassel','Sleeve_VL_Main','M250 533L263 538L269 597Q252 602 238 595Z');
cut('18_ArmDetails','Sleeve_VR_Tassel','Sleeve_VR_Main','M695 537L706 537L720 596Q706 603 690 598Z');
cut('18_ArmDetails','Sleeve_VL_Ribbon','Sleeve_VL_Main','M250 537L261 539Q231 578 194 590Q164 610 176 632L188 651L180 658Q146 624 166 604Q179 587 202 581Z');
cut('18_ArmDetails','Sleeve_VR_Ribbon','Sleeve_VR_Main','M705 539L713 538Q741 573 775 590Q802 608 780 646L772 657L763 652Q790 623 773 609Q731 581 705 539Z');
ellipse('20_Hardware','Sleeve_VL_Coin','Sleeve_VL_Main',188,582,13.5,10.5);ellipse('20_Hardware','Sleeve_VR_Coin','Sleeve_VR_Main',769,586,13.5,10.5);
for(const [id,par,x,y,rx,ry]of [['VL_Blue','Sleeve_VL_Main',188,653,7,10],['VL_Red','Sleeve_VL_Main',186,673,10,11],['VL_Gold','Sleeve_VL_Main',203,665,7,9],['VR_Blue','Sleeve_VR_Main',767,660,8,11],['VR_Red','Sleeve_VR_Main',768,679,9,11],['VR_Gold','Sleeve_VR_Main',752,670,7,9]])ellipse('20_Hardware','SleeveGem_'+id,par,x,y,rx,ry);
for(const [s,par,x,y]of [['VL','Cuff_VL',197,699],['VR','Cuff_VR',759,703]]){
  ellipse('20_Hardware',`Cuff_${s}_UpperButton`,par,x,y,5,6.5);ellipse('20_Hardware',`Cuff_${s}_LowerButton`,par,x+(s==='VL'?-5:4),y+16,5,6.5);
}
// Hand/finger artwork remains intact in this pass: invented finger cuts failed visual QA.
// Front hair is traced as whole locks, including their existing painted highlights.
const hair=['Hair_CrownBack','Pony_VL','Pony_VR'];
cut('13_Face','Face','Hair_CrownBack','M423 133Q474 131 535 148L573 176L570 214Q562 233 539 249Q516 266 490 267Q450 257 424 238Q406 223 401 201Z');
cut('13_Face','Neck','Hair_CrownBack','M470 259Q480 264 490 267Q505 260 520 248L520 275H472Z');
cut('14_FrontHair','Hair_VL_Front',hair,'M459 62Q418 53 387 95Q358 136 371 189Q380 224 414 245Q425 252 444 253Q421 259 411 248Q422 260 445 263Q420 267 396 243Q371 223 364 190Q351 160 362 124Q380 79 415 62Z');
cut('14_FrontHair','Hair_VL_InnerLock',hair,'M459 67Q426 80 411 114Q393 159 405 190Q418 220 435 224Q419 229 403 217Q391 204 387 184Q380 147 399 108Q418 77 459 67Z');
cut('14_FrontHair','Hair_VL_CheekLock',hair,'M382 184Q389 214 410 226Q423 234 442 233Q430 242 410 232Q391 222 382 207Z');
cut('14_FrontHair','Hair_VR_Front',hair,'M463 64Q488 52 518 73Q563 101 582 152Q599 208 561 242L535 249Q568 230 572 195Q577 146 539 103Q505 67 463 64Z');
cut('14_FrontHair','Hair_VR_InnerLock',hair,'M464 68Q498 68 522 91Q551 118 540 170Q514 160 498 135Q481 100 464 68Z');
cut('14_FrontHair','Hair_VR_CheekUpper',hair,'M540 152Q550 187 531 205L523 211Q545 209 555 193L560 157Z');
cut('14_FrontHair','Hair_VR_CheekLower',hair,'M565 158Q583 210 547 226Q538 230 521 231Q548 217 555 194Z');
cut('14_FrontHair','Forelock_Red',hair,'M456 72Q461 65 469 71Q494 84 507 119Q520 158 491 192Q497 198 504 199Q480 203 465 196Q471 203 482 205Q448 201 430 174Q412 145 425 108Z');
cut('14_FrontHair','Forelock_Blue',hair,'M457 73Q441 102 447 123Q453 147 480 151Q461 156 443 145Q449 160 473 163Q459 171 444 163Q450 173 477 173Q440 184 421 158Q408 145 416 123Q425 89 457 73Z');
cut('14_FrontHair','Hair_Ahoge','Hair_CrownBack','M443 13Q473 0 480 29L474 30Q475 15 458 15Q435 21 436 37Q434 50 454 61Q429 58 420 41Q409 24 443 13Z');
// Ponytail curls use natural bends as planned articulation joints, not color-isolation masks.
cut('12_Hair','Pony_VL_LowerCurl','Pony_VL','M275 277Q311 280 329 293Q350 311 341 329Q338 350 362 333L373 333L340 379H275Z',0,'planned-joint');
cut('12_Hair','Pony_VR_LowerCurl','Pony_VR','M603 292Q633 297 652 321Q676 344 704 317L729 321L696 380H626Z',0,'planned-joint');
// Eyes: full visible iris pieces; pupil/highlight are not arbitrarily sliced out.
cut('15_Eyes','Eye_VL_White','Hair_CrownBack','M410 198Q435 188 457 199L457 205Q434 209 421 215L408 207Z');
cut('15_Eyes','Eye_VR_White','Hair_CrownBack','M496 185Q520 169 539 178L538 187Q518 192 503 193Z');
cut('15_Eyes','Eye_VL_Iris','Hair_CrownBack','M429 195Q440 192 451 195L451 206Q442 208 436 211Q430 207 429 195Z');
cut('15_Eyes','Eye_VR_Iris','Hair_CrownBack','M504 177Q516 172 526 175L526 187Q523 192 507 192Q503 186 504 177Z');
cut('15_Eyes','Eye_VL_UpperLash','Hair_CrownBack','M400 196L404 197L402 193L410 194L409 191L416 194Q435 188 449 192Q457 195 460 198Q432 193 410 207L406 208L401 202L397 201L404 200Z');
cut('15_Eyes','Eye_VR_UpperLash','Hair_CrownBack','M493 188Q506 173 525 173Q535 173 540 169L539 166L544 172L546 171L543 176L548 175L544 179Q519 174 497 189L492 192Z');
cut('15_Eyes','Eye_VL_LowerLine','Hair_CrownBack','M421 215Q438 208 457 205',0.8);
cut('15_Eyes','Eye_VR_LowerLine','Hair_CrownBack','M503 193Q518 191 538 187',0.8);
cut('15_Eyes','Brow_VL','Hair_CrownBack','M413 178Q422 174 432 172',2.5);
cut('15_Eyes','Brow_VR','Hair_CrownBack','M494 157Q507 153 514 154',1.8);
cut('16_FaceDetails','Mouth','Hair_CrownBack',box(468,225,36,17));
cut('16_FaceDetails','Nose','Hair_CrownBack','M474 210Q478 216 477 221L479 224L474 220Z');
// Hair clips are detached as whole ornaments first; their tiny hinges need a later pass.
cut('19_HairClips','HairClip_VL',hair,'M336 95Q349 59 390 39L402 59L400 68Q409 66 407 75L389 91L378 116Q365 109 370 92Q356 103 351 97L346 104Z');
cut('19_HairClips','HairClip_VR',hair,'M531 18Q577 26 604 70L591 78L584 70Q586 78 579 80L566 76L577 88Q575 94 568 97L547 76L521 62Q514 53 523 48L530 51L526 43Q514 35 525 28Z');
const chest=['Cape_VL','Cape_VR','Collar','Inner_Bodice','Jacket_VL','Jacket_VR'];
cut('10_Cape','Cape_VL_Cord',chest,'M438 305Q429 312 427 323L425 332L410 355',3.5);
ellipse('20_Hardware','Cape_VL_Pin',chest,438,306,4,5);
cut('20_Hardware','Cape_VR_Clasp',chest,'M537 288Q547 280 555 289L562 312L559 329L544 330L542 313Z');
cut('17_Bow','Bow_VL',chest,'M475 326Q459 315 448 321L449 347Q452 354 477 340Z');
cut('17_Bow','Bow_VR',chest,'M494 325Q510 317 523 321Q528 322 525 331L525 344Q525 355 516 350L493 340Z');
ellipse('17_Bow','Bow_Brooch',chest,485.5,334,12.2,12.2);
for(const d of p){
  if(['Forelock_Red','Forelock_Blue'].includes(d.id))d.refine={color:d.id.endsWith('Red')?'red':'blue',radius:14};
  if(['Face','Neck'].includes(d.id))d.refine={color:'skin',radius:10};
  if(d.group==='20_Hardware'&&/Button|Gem|Medallion|Coin|Brooch|Pin|Badge|Clasp/.test(d.id))d.refine={radius:8};
  if(d.id.startsWith('Cuff_')&&d.id.includes('Button'))d.refine={radius:8,color:'gold'};
  if(['Bow_Brooch','Bow_VL','Bow_VR','HairClip_VL','HairClip_VR'].includes(d.id))d.refine={radius:10};
  if(d.group==='14_FrontHair'&&d.id.startsWith('Hair_'))d.refine={color:'white',radius:8};
  if(d.id.endsWith('UpperLash')||d.id==='Mouth')d.refine={color:'ink',radius:4};
  if(d.id==='Mouth')d.refine={color:'mouth',radius:8};
  if(d.id.startsWith('Brow_'))d.refine={color:'bluegray',radius:8};
  if(d.id.endsWith('_Iris'))d.refine={color:d.id.includes('_VL_')?'red':'blue',radius:5};
}
module.exports=p;
