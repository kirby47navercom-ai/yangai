# 재작화 원본 및 프롬프트 세트

내장 이미지 생성 도구를 사용하였으며 CLI·개인 API 키를 사용하지 않았습니다. 선택한 결과를 이 프로젝트에 복사하고 알파 채널을 보존합니다. 원화는 `assets/live2d/hana-v6/hana-refined-4k.png`입니다. 아래는 재생성용 최종 요구사항을 정리한 프롬프트 세트이며, 이전 호출 전체를 단어 단위로 보존한 로그는 아닙니다.

## 공통 프롬프트

```text
Use case: precise-object-edit. Asset type: transparent material-surface artwork for Hana's 2D puppet. Use the accepted full-body Hana image as the costume, identity, color, proportion and drawing-style reference. Draw only the specified isolated complete object, including surfaces hidden behind the removed elements. Preserve the original material colors; colored fabric is not decoration. Never include pixels belonging to skin, hair, clothing or hardware other than the specified object. Do not imitate the boundary of a visible-pixel cutout. Paint continuous hidden surfaces, with clear natural contours and covered roots. Real transparent background, no shadow outside the silhouette, no text. Simple coherent hair bundles where applicable; smooth precise anime lineart; clean cel shading and restrained soft shading. No grain, moire, film grain, glitter, particles, unnecessary bloom or noisy texture. Do not redesign the costume.
```

## 대상별 추가 지시

| 저장명 | 공통 지시에 추가할 내용 |
| --- | --- |
| `head-skin.png` | Complete bald head skin with forehead, both ears, cheek and chin contours. No facial features, hair-shaped notches, hair or costume. Pale peach palette matching the face. |
| `neck-skin.png` | Full slim neck column, slightly tilted like the source, with upper skin continuing behind the chin and lower skin behind the standing collar. No jaw fragment, face, hair, collar or shoulders. Thin warm outline and restrained warm shading. |
| `forelock-red.png` | The entire original red central forelock only, from complete hidden root to tapered layered tips. No blue strand, white hair, skin triangles or ornaments. Preserve clean internal strand shading. |
| `forelock-blue.png` | The full original blue curved strand overlaying the red forelock, with complete root and layered tips. No red or white hair, skin or ornaments. |
| `white-front-hair.png` | A coherent full white crown and front-hair shape, including complete side/cheek locks. No face, skin, colored central forelock, hair clips, costume or disconnected fragments. |
| `back-hair.png` | Complete original hairstyle used as the reconstruction source for both full ponytails. White/red viewer-left and white/blue viewer-right; clear broad flowing bundles, no face, costume or hair accessories. Parts outside each ponytail are excluded during semantic separation. |
| `cape-fabric.png` | Full original shoulder cape cloth, red viewer-left and blue viewer-right, including fabric under clasps and straps. No gold hardware, cord, bow, brooch, skin or hair. A black yoke included by the selected result is not used as colored cape fabric. |
| `inner-outfit.png` | Continuous black high-neck bodice, fitted waist and complete skirt. Keep original red/blue/white textile panels and piping. Remove ornamental flowers, chains, loops, badges, gems and hanging ornaments. No jacket, limbs or skin. |
| `jacket-base.png` | Complete original short white jacket and both puffed sleeves, including covered shoulder/sleeve seams. Preserve colored textile piping and controlled lavender-gray cloth shading. No pocket hardware, straps, badges, tassels or metal ornaments. Colored cuff fabric is separated during preparation. |
| `pockets-base.png` | Both original white patch pockets with white flaps, side by side, preserving slanted lower corners and seam lines. Continuous cloth beneath removed gold cords, black hanging ribbons and pendants. No surrounding jacket or metal. Sleeve pocket cloth is fitted separately from this source. |
| `cuffs-base.png` | Two complete short curved cloth tubes, red viewer-left and cobalt blue viewer-right. Preserve perspective and dark inner lining. Remove gold buttons and repaint the covered fabric without circular scars or holes. No hands or white sleeves. |
| `armbands-base.png` | Two complete black upper-arm cloth bands, side by side, preserving soft folds and upper/lower hems. Remove all red/blue tabs, grommets, round buttons, buckles, straps, skin and white sleeves. No circular scars or gaps in the black cloth. |
| `legs-complete.png` | Both complete stocking-clad leg silhouettes, including upper thighs hidden beneath the skirt and lower ends behind boots. Match posture and smooth anatomical contours. No skirt, boots, tail or visible background fragments. |
| `boots-base.png` | Both entire original charcoal-black ankle boots, front standing view, including upper openings, wrinkled shafts, round toes and platform soles. Keep plain black fastening bands; remove jewels, gold, flowers and colored tassels/ribbons. Paint uninterrupted leather under every ornament. No legs or stockings. |
| `tail-complete.png` | A complete thick, soft curled white tail with a black end. Preserve the source curl, generous volume and softly grouped fur, using clean cel/soft shading instead of noisy individual hairs. No missing root, pinched notch, surrounding body or costume. |
| `tail-complete-v2.png` | 현재 사용하는 꼬리 원본입니다. 오른쪽 잘린 외곽을 다시 작성하고 캔버스 여백을 확보하였습니다. |
| `legs-complete-v2.png` | 현재 사용하는 연속된 다리 원본입니다. 다리 내부 명암을 이어 작성하며, 기존 가시 픽셀의 치마·꼬리 절단선을 형태로 재사용하지 않습니다. |

## 이번 수정의 최종 이미지 생성 프롬프트

기존 내장 이미지 생성 도구를 사용하였습니다. 아래 두 프롬프트는 선택한 새 원본의 실제 최종 호출 지시입니다. 꼬리의 첫 수정 결과는 여백이 부족하여 채택하지 않았습니다.

```text
Precise object edit of Image 1. The existing tail is too zoomed in: the RIGHT OUTER CURVE is clipped by the canvas. Render the SAME tail completely surrounded by spacious transparent margins. Use a SQUARE composition; zoom OUT significantly. The tail occupies only the CENTER 65 percent of the image width and height. A minimum 15 percent entirely transparent EMPTY margin on the left AND right AND top AND bottom is essential. Finish the right fur outline into a naturally rounded convex contour; no edge touches any canvas boundary. Keep exactly this white fluffy curved weasel tail with black/dark charcoal tip, broad clean cel-shaded fur masses and soft smooth shading. Root upper left and black tip upper right, same proportions. No added objects, no text, no backdrop, no grain, speckles, particles or bloom. Actual transparent PNG. Do NOT deliver a tightly cropped tail; the full object must float within ample blank alpha canvas.
```

```text
Use case: precise-object-edit. Image 1 is the edit target and anime shading/style reference. Repaint this same pair of stocking-clad legs as a clean Live2D anatomical base on actual transparent alpha. Keep the original slim thigh/knee/calf/ankle proportions, feet down and same posture. TWO entirely COMPLETE separate dark charcoal warm gray stocking legs, from smooth rounded hidden upper-thigh roots to complete ankles/feet. No skirt, boots, body or costume. Each leg is a continuous opaque surface: inside the leg shape alpha must be fully opaque; outside the crisp clean leg silhouette alpha must be zero. REMOVE ALL brown fog and translucent haze outside the legs. No detached skin, horizontal step, rectangular shading, joint seam, background cloud or rim halo. Anatomically continuous rounded knees, broad clean smooth cel and soft shading, not disconnected thigh/knee/calf pieces. Delicate clean outer line; highlights follow the full leg continuously without abrupt changes. Sufficient transparent gap between the two legs and generous transparent margins. No grain, speckles, particles, bloom or glitter, no text. Same two stocking legs and palette, do not redesign.
```

다리 생성 원본에는 실루엣 주변의 흐린 알파가 일부 남아 있습니다. 프롬프트만으로 깔끔한 마스크가 보장된다고 취급하지 않습니다. 실행 파츠에는 정리한 윤곽과 불투명 내부를 적용하고 별도로 재조합을 검사합니다.

## 생성 결과와 적용 범위의 구분

실제 배치와 분리는 `tools/live2d/rebuild-surfaces.py`에 정의합니다. 그린 전체 윤곽을 완전한 개체 또는 같은 재질의 연속된 면으로 사용합니다. 관절을 서로 다른 생성 그림의 경계에서 연결하지 않습니다. 남아 있던 피부·다른 재질의 파편과 투명 영역의 RGB 잔여물을 제거하고 PSD 재조합과 네이티브 재생을 확인합니다.

생성 결과에는 원화와 다른 주름·형태가 있으며 모든 미세 장식의 완전한 숨은 면까지 보장하지 않습니다. 파츠 수·해상도·자동 검사 통과를 미술적 완성의 증거로 취급하지 않습니다. 미완성 범위는 상위 README와 `qa/review.json`에 기록합니다.
