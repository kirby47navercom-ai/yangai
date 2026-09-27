# 하나 고해상도 원화 제작 기록

## 실행 방식과 결과

- 실행일: 2026-09-28
- 방식: 내장 이미지 생성·편집 도구. CLI/API 대체 경로는 사용하지 않았습니다.
- 입력: `approved.png`와 동일한 승인 원화.
- 비교 출력: 프로젝트의 `.local-tools/realesrgan-20220424/detail-candidate.png`. 최종 원화로 채택하지 않았으며 Git에서 제외합니다.
- 요청: 디자인을 유지한 고해상도 세부 보완, 2048 × 3072 또는 지원되는 최고 해상도.
- 실제 출력: 1024 × 1536, RGB PNG. 고해상도 목표 미달로 최종 마스터로 사용하지 않았습니다. 아래 로컬 업스케일 경로로 전환하였습니다.
- 투명 배경: 요청하지 않았습니다. 승인 원화의 배경 및 배치를 유지한 비교용 이미지입니다.
- 판정: 전신 구성과 적청색 머리·눈, 의상, 검은 끝의 흰 꼬리는 유지하였으나, 생성형 편집이므로 원본과 픽셀 단위로 동일하지 않습니다. 승인 원본은 별도로 보존하였습니다.

## 내장 이미지 도구에 실제 사용한 지시문

```text
Use case: identity-preserve
Asset type: high-resolution master candidate for a detailed Live2D character, not a redesign.
Input image 1 is BOTH the sole edit target and the approved authoritative design, style, pose, composition and facial identity.
Primary request: produce a genuinely higher-resolution, crisp restored edition of this exact illustration. Requested canvas 2048 x 3072 pixels (portrait 2:3), or the highest supported native resolution at the same aspect ratio. Improve fine detail for close inspection, rather than merely adding aggressive sharpening.
Preserve exactly: the full-body front pose and slight head inclination; half-lidded narrow red viewer-left eye and blue viewer-right eye, relaxed teasing smile, face shape, body proportions, hand poses; white/silver hair with red viewer-left and blue viewer-right locks, curled twin tails and black segmented HAIR ORNAMENTS, not ears/horns; every existing clothing panel, strap, bow, pocket, metal flower, tassel, dark tights and boots, including the existing asymmetries. Keep the same hand-drawn delicate linework, soft cool blue-gray shading, warm pink blush, and individual painted hair strands. Keep the same pale gray background and all margins and framing.
Tail: preserve ONE tail in exactly the same position, curve and proportions. White ermine-like furry body, with black ONLY at the terminal tip. Preserve the original black-to-white boundary and fine fur.
Enhance only resolution, clean faithful contour detail, eyelashes and iris edges, individual hair/fur strands, seams and already-present small metal decorations. Do not invent new embroidery or jewelry.
Avoid: changed face, rounder or larger eyes, chibi style, flat cel shading, photorealism, different costume, repositioned tail, new fingers, missing fingers, text, watermarks, multiple panels, separated parts, pose change, thick outlines, oversharpening halos, plastic smoothing.
One image only.
```

## 로컬 업스케일 처리

사용자가 로컬 AI 업스케일러 사용 및 필요 시 설치에 동의한 후 수행하였습니다. 이미지 생성 API의 CLI 대체 경로를 사용한 것이 아니라, [Real-ESRGAN 공식 프로젝트의 휴대용 Windows 배포판](https://github.com/xinntao/Real-ESRGAN/blob/master/README.md)을 로컬에서 실행한 것입니다. 추가 Python·CUDA 패키지를 설치하거나 기존 애플리케이션 환경을 변경하지 않았습니다.

- 배포본: `realesrgan-ncnn-vulkan-20220424-windows.zip`.
- 배포 위치: [공식 v0.2.5.0 릴리스](https://github.com/xinntao/Real-ESRGAN/releases/tag/v0.2.5.0).
- 선택 모델: `realesrgan-x4plus`.
- 비교 모델: `realesrgan-x4plus-anime`. 채색을 더 평탄하게 만드는 경향이 있어 이번 원화에서는 채택하지 않았습니다.
- 입력: `assets/live2d/hana-v1/approved.png`.
- 선택 결과: `assets/live2d/hana-v1/hana-4x.png`, 4096 × 6144, RGB PNG, 22,358,515바이트.
- 실행 설정: 4배, 타일 크기 256, PNG 저장. 별도 창을 표시하지 않는 숨김 프로세스로 실행하였습니다.

프로젝트 루트 기준 재현 명령은 다음과 같습니다. 실행 파일과 모델은 Git에 포함되지 않으므로 공식 배포본을 먼저 해당 로컬 도구 폴더에 준비해야 합니다. 기존 결과를 덮어쓰지 않도록 출력 이름은 재실행용으로 구분하였습니다.

```powershell
& .\.local-tools\realesrgan-20220424\realesrgan-ncnn-vulkan.exe `
  -i assets/live2d/hana-v1/approved.png `
  -o .local-tools/realesrgan-20220424/hana-4x-rerun.png `
  -n realesrgan-x4plus -s 4 -t 256 `
  -m .local-tools/realesrgan-20220424/models -f png
```

아래 SHA-256 값은 다운로드·처리한 로컬 파일의 추적용 값입니다. 배포자가 별도로 인증한 서명이나 체크섬이라는 의미는 아닙니다.

```text
realesrgan-ncnn-vulkan-20220424-windows.zip
abc02804e17982a3be33675e4d471e91ea374e65b70167abc09e31acb412802d

realesrgan-ncnn-vulkan.exe
07e49f7cbb4ede01ae4dd4c399d3a7e5846e3d2085c3128eff881e55cb7b1a0c

models/realesrgan-x4plus.bin
713ee713b0353afaa27976f0563a64a5043bd70b9bd8936c2e26e25ebcdbcddf
```

## 검수 결과와 한계

- 원본 보존: `approved.png`의 SHA-256 값이 승인 원화와 동일함을 확인하였습니다.
- 실제 크기: 업스케일 PNG 디코딩 및 4096 × 6144 규격 확인을 수행하였습니다.
- 확대 검사: 얼굴과 홍채, 손과 소매 장식, 흰 꼬리와 검은 끝 경계를 원본 픽셀 크기로 확인하였습니다. 검사 화면의 잘라내기·확대는 메모리에서만 수행하였으며 최종 파일을 수정하지 않았습니다.
- 전체 구성: 1024 × 1536으로 축소한 미리보기에서 승인 원화의 전신 배치, 색상 및 꼬리 형태를 비교하였습니다.
- 선택 이유: 일반 모델이 애니메이션용 모델보다 원본의 부드러운 음영과 선의 농도 차이를 더 유지하는 것으로 관찰되었습니다.
- 한계: 업스케일은 원본에 없던 정확한 정보를 복구하는 과정이 아닙니다. 일부 미세선과 질감은 모델의 추정이며, 무제한 확대에서도 선명하다는 의미는 아닙니다. 이후 얼굴 클로즈업과 파츠 변형 과정에서 필요한 부분은 별도 보완해야 합니다.
