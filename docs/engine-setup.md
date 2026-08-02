# GPT-SoVITS 引擎安装(M0)

GPT-SoVITS 跑在**独立 venv**(Python 3.10),与本项目的 3.12 隔离。引擎监听 `127.0.0.1:9880`,后端通过 HTTP 调它的 `api_v2.py`。

## 1. 克隆(同级目录)

```bash
cd /path/to/parent
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

- 准备一段 **3–10 秒**干净粤语人声(GPT-SoVITS 硬性要求,否则报 `参考音频在3~10秒范围外`)放到:`refs/cantonese_ref_trim.wav`(mono,16k/24k/48k)。
- 把该音频的**粤语转写**写到:`refs/cantonese_ref_trim.txt`(整段文本,作 `prompt_text`)。`app.py` 读的就是这两个 trim 文件。
- 没有的话:自己录一段后裁到 3–10 秒,或用公开粤语短音频裁剪;只需一个固定粤语参考。

参考音决定音色、口音、韵律,但**不影响字的基本读音**(那由 `text_lang=yue` + 归一化负责);想让合成更地道港式,关键是参考音里的人本身就说地道港式粤语。

### 替换参考音(换音色 / 换口音)

1. 录约 1 分钟干净粤语素材,挑最地道的 5-8 秒裁出(mono):
   ```bash
   ffmpeg -ss <起点秒> -t <5-8> -i in.wav -ac 1 refs/cantonese_ref_trim.wav
   ```
   (Audacity 图形裁剪亦可;可裁 2-3 段分别试听择优)
2. 把**裁出片段**的逐字粤语转写覆盖到 `refs/cantonese_ref_trim.txt` —— 必须与音频逐字对齐,否则克隆质量下降。
3. **清缓存**(音色不入缓存键,ADR-0006;不清的话旧音最长存活 30 天):
   ```bash
   rm -rf cache/        # 或 bump CONTRACT_TTS_ENGINE(如 gptsovits-v2) 后重启服务
   ```
4. 重启服务、试听一段确认音色 / 口音。

## 5. 启动 API(独立终端,常驻)

```bash
cd /path/to/GPT-SoVITS
uv run python api_v2.py      # 默认 127.0.0.1:9880
```

## 6. 验证粤语(冒烟)

```bash
REF=refs/cantonese_ref_trim.wav
PROMPT=$(cat refs/cantonese_ref_trim.txt)
curl -s -X POST http://127.0.0.1:9880/tts \
  -H 'Content-Type: application/json' \
  -d "{\"text\":\"甲方應於三日內支付訂金。\",\"text_lang\":\"yue\",\"ref_audio_path\":\"$REF\",\"prompt_text\":\"$PROMPT\",\"prompt_lang\":\"yue\",\"media_type\":\"wav\",\"streaming_mode\":false}" \
  -o /tmp/yue_smoke.wav
ls -la /tmp/yue_smoke.wav   # KB+ = 拿到音频
```

听 `/tmp/yue_smoke.wav`:**M0 通过线 = 听起来是粤语**(不做母语级地道评判,那是后续单独关卡)。若像"普通话读粤字",记下来 —— 这是推迟的地道性风险,架构仍可继续(引擎解耦)。

## 7. 确认 /tts 参数名

打开 `GPT-SoVITS/api_v2.py`,核对 JSON 字段名(`text` / `text_lang` / `ref_audio_path` / `prompt_text` / `prompt_lang` / `media_type` / `streaming_mode`)与安装版本一致。若不同,记到本文档 —— `gptsovits_client.py` 须用实际字段名。

## 8. 实测踩坑(M0 已验证通过,2026-07-25 M3 Max)

1. **`hf download lj1995/GPT-SoVITS <folder>` 会 404** —— 该 CLI 把 folder 当单文件 resolve。改用 **ModelScope 镜像 `XXXXRT/GPT-SoVITS-Pretrained`**(国内快很多),按 `pretrained_models/<subfolder>/<file>` 的 resolve URL 逐文件拉。需要的子目录:`gsv-v2final-pretrained/`、`chinese-hubert-base/`、`chinese-roberta-wwm-ext-large/`、`fast_langdetect/`。
2. **缺 `pretrained_models/fast_langdetect`** → 报 `Cache directory not found: .../fast_langdetect`。补 `lid.176.bin` + `lid.176.ftz`(ModelScope 有)。
3. **`TorchCodec is required for load_with_torchcodec`** —— 根因是 **torchaudio 2.11 / torch 2.13 过新**(requirements 未 pin 上限,uv 装了最新)。修法:`uv pip install -p .venv torchcodec`(实测有效;降 transformers 到 4.46.3 无用,因为是 torchaudio 触发)。
4. **参考音频必须 3–10 秒** —— 否则 `参考音频在3~10秒范围外`。用 `refs/cantonese_ref_trim.wav`(7s)+ 对应转写 `cantonese_ref_trim.txt`。app.py 已指向 trim 版。
5. **本机 `http_proxy=localhost:7897`(clash)** —— curl 测试加 `--noproxy '*'`;后端 httpx 客户端必须 `trust_env=False`(已在 `gptsovits_client.py` 处理),否则 127.0.0.1 走代理 → 502。浏览器访问 localhost 通常自动 bypass。
6. **M0 结果**:书面中文 `甲方應於三日內支付訂金。` + `text_lang=yue` → 3.9s 粤语音频,生成耗时 1.57s,**RTF≈0.4**(M3 Max CPU,快于实时)。样本见 `samples/gptsovits_yue_m0.wav`。
7. **含拉丁字母的文本(如型号 `XR-7200`)→ 引擎 400 `Resource 'averaged_perceptron_tagger_eng' not found`**。GPT-SoVITS 英文前端需要 NLTK 数据。下载 ModelScope 的 `nltk_data.zip`,解压到 `~/nltk_data/`,**注意 zip 内有嵌套的 `nltk_data/` 目录,要把里面那层的内容拍平到 `~/nltk_data/`**(否则 NLTK 找不到 `taggers/averaged_perceptron_tagger_eng`)。
