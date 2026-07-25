# GPT-SoVITS 引擎安装(M0)

GPT-SoVITS 跑在**独立 venv**(Python 3.10),与本项目的 3.12 隔离。引擎监听 `127.0.0.1:9880`,后端通过 HTTP 调它的 `api_v2.py`。

## 1. 克隆(同级目录)

```bash
cd /Users/roy/codes
git clone --depth 1 https://github.com/RVC-Boss/GPT-SoVITS.git
cd GPT-SoVITS
```

## 2. Python 3.10 venv + 依赖

```bash
uv venv --python 3.10 .venv
uv pip install -p .venv -r requirements.txt
```

> Apple Silicon 走 CPU 推理(官方把 Apple silicon 列为已测推理设备)。若某依赖报错,按仓库当前 macOS 说明处理,并把偏差记回本文档。

## 3. 预训练模型

按仓库 README 放置(版本可能演进,以下为已知结构):
- `GPT_SoVITS/pretrained_models/` — 含 `gsv-v2final-pretrained`(v2 起支持粤语 `yue`)。
- `GPT_SoVITS/text/G2PWModel/` — 中文 G2PW(v2 中文必需)。
- 下载链接见上游 README 的 "pretrained_models" 与 "G2PWModel" 段。

## 4. 粤语参考音频(voice-clone 锚)

- 放约 5s 干净粤语人声到:`seek_probe/refs/cantonese_ref.wav`(mono,16k/24k/48k)。
- 把该音频的**粤语转写**写到:`seek_probe/refs/cantonese_ref.txt`(整段文本,作 `prompt_text`)。
- 没有的话:自己录 ~5 秒,或用公开粤语短音频;穿刺只需一个固定粤语参考。

## 5. 启动 API(独立终端,常驻)

```bash
cd /Users/roy/codes/GPT-SoVITS
uv run python api_v2.py      # 默认 127.0.0.1:9880
```

## 6. 验证粤语(冒烟)

```bash
REF=/Users/roy/codes/audio-with-qwen3-tts/seek_probe/refs/cantonese_ref.wav
PROMPT=$(cat /Users/roy/codes/audio-with-qwen3-tts/seek_probe/refs/cantonese_ref.txt)
curl -s -X POST http://127.0.0.1:9880/tts \
  -H 'Content-Type: application/json' \
  -d "{\"text\":\"甲方應於三日內支付訂金。\",\"text_lang\":\"yue\",\"ref_audio_path\":\"$REF\",\"prompt_text\":\"$PROMPT\",\"prompt_lang\":\"yue\",\"media_type\":\"wav\",\"streaming_mode\":false}" \
  -o /tmp/yue_smoke.wav
ls -la /tmp/yue_smoke.wav   # KB+ = 拿到音频
```

听 `/tmp/yue_smoke.wav`:**M0 通过线 = 听起来是粤语**(不做母语级地道评判,那是后续单独关卡)。若像"普通话读粤字",记下来 —— 这是推迟的地道性风险,架构仍可继续(引擎解耦)。

## 7. 确认 /tts 参数名

打开 `GPT-SoVITS/api_v2.py`,核对 JSON 字段名(`text` / `text_lang` / `ref_audio_path` / `prompt_text` / `prompt_lang` / `media_type` / `streaming_mode`)与安装版本一致。若不同,记到本文档 —— `gptsovits_client.py` 须用实际字段名。
