# 눈 보완 원화 생성 기록

## 생성 방식

내장 imagegen 도구를 사용하였습니다. 참조 이미지는 승인된 V6 원화에서 잘라낸 `../references/eyes-source-native.png`입니다. 얼굴 전체나 의상은 생성 대상이 아닙니다. 기존 그림의 눈 부분을 참조하여 눈꺼풀에 가려진 영역이 포함된 파츠를 새로 제작한 것이므로, 원화 픽셀을 그대로 복원한 결과와 구분해야 합니다.

첫 생성 결과를 `source/eye-underpaint-sheet.png`에 보존하였습니다. 투명 배경 요청에도 윤곽 밖 광채가 포함되어, 그대로 사용하지 않고 로컬 원형·타원형 마스크로 각 파츠의 내부만 추출하였습니다. 후속 광채 제거 편집도 동일한 문제가 남아 채택하지 않았습니다. 최종 마스터에는 첫 시트의 내부 색상과 새 윤곽 알파가 사용됩니다.

## 채택한 시트의 프롬프트

```text
Use case: precise-object-edit. Asset type: high-resolution Live2D eye reconstruction parts, a production asset sheet on genuine transparent alpha, no background. Input image 1 is the exact color/style reference of Hana's existing half-closed red viewer-left eye and blue viewer-right eye. Draw ONLY separated eye underpaint components, NOT a face, no eyelids, lashes, brows, hair, skin or labels. Layout: two columns, four rows with ample transparent spacing. ROW 1: left a FULL PERFECTLY ROUND red iris disk with fine dark burgundy outer rim, dark crimson upper third with a simple curved cel-shadow boundary and bright scarlet/coral lower area; right a FULL PERFECTLY ROUND royal-blue iris disk with fine dark navy rim, dark blue upper third with a simple curved cel-shadow boundary and bright royal blue lower area. Iris disks are complete filled circles, absolutely NO holes, NO pupils and NO specular reflections baked into these disks. Their entire circumference and occluded upper area must be painted so they can move behind eyelids. Each disk large, about 600px diameter on a 2048px-wide sheet if possible. Match the reference's SIMPLE cel+soft shading, NOT radial striations or realistic noisy eye textures. ROW 2: two separate dark nearly black narrow vertical elliptical pupils, one black-burgundy and one black-navy; simple filled ellipses without highlights. ROW 3: two wide filled white eye-white/sclera ovals with very subtle pale cool gray upper shading, NOT anatomical eyeballs, NO outlines; plain full flat oval underpaint. ROW 4: two isolated clean tiny solid white circular catchlights and one small pale blue soft lower-reflection oval positioned under the right column. All components are disconnected with generous clear space, crisp smooth antialiased edges, flat front-on orthographic view. No grain, no noise, no bloom, no glitter, no decorative particles, no texture, no checkerboard painted into image. Preserve red-left/blue-right identity. These are separate animation components, not a beauty portrait.
```

## 채택하지 않은 후속 편집

동일 파츠의 위치와 색을 유지하면서 광채·블룸·검은 배경을 제거하고 윤곽 밖을 투명하게 만드는 편집을 요청하였습니다. 결과에 여전히 광채가 남아 최종 추출 원화로 사용하지 않았습니다. 최종 PSD 및 PNG 생성은 `tools/live2d/prepare-eyes.cjs`에서 수행됩니다.

## 피부 보완 텍스처

눈 전체 이동용 피부 보완을 위해 원화의 피부색을 참고한 불투명 텍스처를 추가 생성하였습니다. 첫 눈 제거 시도는 불투명 피부 대신 빈 영역이 생겨 채택하지 않았습니다. 아래 프롬프트로 얻은 피부 텍스처를 `source/skin-underpaint-texture.png`에 보존하였습니다. 전체 얼굴을 대체하지 않고, 기존 눈 영역의 국소 마스크 안에만 사용하며 주변 원화의 피부색으로 저주파 색상을 보정합니다. 생성 시트 자체는 최종 피부 경계 마감 결과가 아닙니다.

```text
Create a completely OPAQUE rectangular facial-skin UNDERPAINT texture using the reference crop's soft peach skin tones. This is a flat paint texture for covering the two eyes before moving them in Live2D. Output only continuous pale peach skin color with subtle smooth blush shading matching the cheeks in this image, left side slightly warmer peach, right side soft cream-peach. Fill EVERY pixel with opaque skin paint; no transparent holes anywhere. No eyes, no eye sockets, no eyelids, no eyelashes, no eyebrows, no hair, no nose, no mouth, no face outline, no objects, no text. Simple clean anime cel/soft shading color field. There must be NO dark or black areas. No grain, texture, noise, sparkle, bloom, or visible brush marks. Wide horizontal rectangle, softly shaded skin paint only, so a local mask can reveal ONLY the tiny necessary under-eye regions in the unchanged original character.
```
