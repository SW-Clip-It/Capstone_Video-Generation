# CLIP-IT Video Generation

문학 텍스트를 기반으로 생성된 장면별 영상 스크립트(JSONL)를 **ComfyUI의 LTX-2 모델**을 통해 영상으로 생성하는 파이프라인입니다.

각 챕터의 첫 장면은 Text-to-Video(T2V)로 생성하고, 이후 장면은 이전 영상의 마지막 프레임을 활용한 **Image-to-Video(I2V)** 방식으로 생성하여 장면 간 시각적 일관성을 유지합니다. 생성된 영상은 AWS S3에 업로드할 수 있습니다.

## 실행 방법

**환경:** Python 3.10+, ComfyUI, LTX-2, FFmpeg

```bash
pip install -r requirements.txt

python run.py \
  --comfy-url http://127.0.0.1:8888 \
  --input-jsonl /path/to/video_scripts_compact.jsonl \
  --comfy-input-dir /path/to/ComfyUI/input \
  --output-dir /path/to/ComfyUI/output \
  --strict-chain
```

S3 업로드 시 `--upload-s3 --s3-bucket YOUR_BUCKET` 옵션을 추가합니다. AWS CLI 인증 설정이 필요합니다.

**참고:** `workflows/` 폴더에 T2V 및 I2V 워크플로 JSON 파일이 필요합니다.
