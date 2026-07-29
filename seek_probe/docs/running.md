# 启动与参数说明

> 面向运维/新接手同事:怎么把系统跑起来、每个参数是什么意思、出问题看哪里。
> 架构与数据流细节见 `architecture.md`;引擎安装见 `engine-setup.md`。

## 1. 系统组成

三个活动部件 + 一个磁盘缓存:

| 部件 | 进程 | 端口 | 必需性 |
|---|---|---|---|
| TTS 引擎 | 本地 GPT-SoVITS (`api_v2.py`) 或云端 Bailian CosyVoice(无本地进程) | 9880(本地) | 二选一 |
| 后端 | `uvicorn seek_probe.backend.app:app` | 8000 | 必需 |
| 浏览器 | 前端静态页由后端挂载提供 | 8000 | 必需 |
| 缓存 | `seek_probe/cache/*.wav`(内容寻址,gitignored) | — | 自动 |

## 2. 启动

### A. 本地 GPT-SoVITS 引擎(默认)

```bash
# 终端 1:引擎(安装见 engine-setup.md)
cd /Users/roy/codes/GPT-SoVITS && uv run python api_v2.py   # 监听 :9880

# 终端 2:后端 + 前端
uv run uvicorn seek_probe.backend.app:app --port 8000
```

需要参考音频 `seek_probe/refs/cantonese_ref_trim.wav` + 同名转写 txt(7 秒,gitignored)。

### B. 云端 Bailian CosyVoice 引擎(无需本地引擎/参考音)

```bash
export DASHSCOPE_API_KEY=sk-...
SEEK_PROBE_ENGINE=bailian uv run uvicorn seek_probe.backend.app:app --port 8000
```

### 打开浏览器

```
http://127.0.0.1:8000/?contract=xcash
```

## 3. 参数一览

### 环境变量(启动参数)

| 变量 | 默认值 | 说明 |
|---|---|---|
| `SEEK_PROBE_ENGINE` | `gptsovits` | 引擎选择:`gptsovits`(本地)/ `bailian`(云端 CosyVoice) |
| `DASHSCOPE_API_KEY` | 无 | `bailian` 引擎必需,阿里云百炼 API Key |
| `BAILIAN_VOICE` | `longjiaxin_v3` | 云端音色。`longjiaxin_v3` 粤语女 / `longjiayi_v3` / `longanyue_v3` 粤语男 |
| `SEEK_PROBE_DUMP_SEGMENTS` | 关 | `=1` 时启动即把每个注册合同的**原始切片**写到 `contracts/<id>.segments.txt`(逐段原文+预估时长,调分段参数用;每次启动覆盖重写) |

### 硬编码常量(`backend/app.py` 顶部,改需动代码)

| 常量 | 值 | 说明 |
|---|---|---|
| `ENGINE_URL` | `http://127.0.0.1:9880` | 本地引擎地址 |
| `REF_AUDIO` / `REF_PROMPT` | `refs/cantonese_ref_trim.{wav,txt}` | 本地引擎参考音,**必须 3–10 秒**(GPT-SoVITS 硬限制) |
| `VOICE_REF_ID` | `cantonese_ref_v1` | 缓存键组成部分;换参考音必须改它,否则命中旧音色缓存 |

### URL 参数(浏览器侧)

| 参数 | 默认 | 说明 |
|---|---|---|
| `?contract=` | `zacl0603` | 合同选择。已注册:`sample` / `zacl0603` / `xcash`。注册表在 `backend/app.py` 和 `backend/contract.py` 的 `_CONTRACT_FILES`(两处都要加) |

## 4. 它是怎么工作的(30 秒版)

合同以 **TXT** 交付(`contracts/<id>.txt`,原始文件,系统只读不写):

1. **切片**:浏览器请求合同 → 后端 `split_contract` 把全文确定性切成 ~20-50 字的段,附带每段预估时长 → 前端据此画出可拖动进度条(音频未生成也能拖)。
2. **定位**:拖动 → 前端按累积时长找到第 N 段 → 请求 `/api/segment/<contract>/<N>`。
3. **归一化**:后端只对该段跑 `normalize_for_tts`(数字/金额/日期 → 粤语读法,英文地址保留,多音字/问题 token 修正)。**逐段按需**,不批量。
4. **缓存**:`sha256(归一化文本 + VOICE_REF_ID)` 为键。命中 → 直接回发放置的 wav;未命中 → 调引擎合成 → 落缓存 → 回发。
5. **预载**:播放某段时后台预热后 3 段,顺序播放基本无等待。

显示给用户的永远是原始段文本;归一化只影响喂给引擎的文本。

## 5. 常见运维操作

| 要做什么 | 怎么做 |
|---|---|
| 接入新合同(TXT) | `cp` 到 `contracts/<id>.txt` → `app.py` + `contract.py` 的 `_CONTRACT_FILES` 各注册一行 → `?contract=<id>` 打开 |
| 切换引擎/音色 | 先 `rm -f seek_probe/cache/*.wav`(**缓存键不含引擎/音色**,不清会串音)再换参数重启 |
| 观察/调整切片 | 带 `SEEK_PROBE_DUMP_SEGMENTS=1` 启动,对比 `contracts/<id>.segments.txt`;参数在 `segmenter.py` 的 `TARGET/SOFT_MAX/HARD_MAX` |
| 看某段实际喂给引擎的文本 | `python -c "from seek_probe.backend.normalizer import normalize_for_tts; print(normalize_for_tts('<段文本>'))"` |
| 跑测试 | `uv run pytest -q` |

## 6. 排障

| 症状 | 原因与处理 |
|---|---|
| `/api/segment` 502 | 本地引擎没起,或代理劫走了 127.0.0.1(代码已 `trust_env=False`,若改了 httpx 调用注意保留) |
| 云端合成偶发 429 | cosyvoice-v3-flash 限流 3 QPM,预载并发会排队,稍等自动重试/重播即可 |
| 浏览器音频时长显示巨大 | cosyvoice 的 wav 头时长字段是占位值,浏览器按 EOF 播放,不影响功能 |
| 音色前后不一致 | 换过引擎/音色但没清缓存 → `rm -f seek_probe/cache/*.wav` |
| `uv run pytest` 报 `No module named 'cn2an'` | `.venv` 是从别的项目拷来的,脚本 shebang 陈旧 → `uv sync --reinstall` |
| 某字读错(如多音字) | 引擎前端缺陷,在 `normalizer.py` 加同音字/替换规则(现有 `還→環`、`注：→注，` 两个先例),勿改合同原文 |
