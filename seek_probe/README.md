# 粤语合同朗读 + 可拖动进度条(穿刺)

可行性穿刺:GPT-SoVITS(粤语)+ 分段 / 内容寻址缓存 / 文本归一化 / seek 映射 + 网页播放器。

- **架构说明(as-built,代码为准):** `seek_probe/docs/architecture.md`
- **启动与参数(环境变量/常见运维/排障):** `seek_probe/docs/running.md`
- 设计 spec:`docs/superpowers/specs/2026-07-25-cantonese-tts-seek-probe-design.md`
- 引擎安装:`seek_probe/docs/engine-setup.md`

## 运行

### A. 本地 GPT-SoVITS 引擎(默认)

1. 引擎(独立终端;见 `docs/engine-setup.md` 安装步骤):
   ```
   cd /Users/roy/codes/GPT-SoVITS && uv run python api_v2.py   # 监听 :9880
   ```
2. 参考音频:`seek_probe/refs/cantonese_ref_trim.wav` + 转写 `cantonese_ref_trim.txt`(7s,gitignored)。
3. 后端 + 前端:
   ```
   uv run uvicorn seek_probe.backend.app:app --port 8000 --reload
   ```

### B. 云端 Bailian CosyVoice 引擎(无需本地引擎 / 参考音)

用 `SEEK_PROBE_ENGINE=bailian` 切换;音色 `BAILIAN_VOICE`(默认 `longjiaxin_v3` 原生粤语女,亦可 `longjiayi_v3` / `longanyue_v3` 粤语男)。需先设 `DASHSCOPE_API_KEY`。
   ```
   SEEK_PROBE_ENGINE=bailian uv run uvicorn seek_probe.backend.app:app --port 8000
   ```
> 引擎可热切:两个 client 的 `synth(text)->AsyncIterator[bytes]` 同构,归一化 / seek / 缓存全部共用。**注意缓存键不含引擎名**——本地↔云端切换前先 `rm -f seek_probe/cache/*.wav`,否则会命中旧引擎的音频。
> **TN 边界**:云端 cosyvoice 自动 TN 只覆盖日期 / 基础金额;逐位(电话 / 身份证 / 型号)、`HK$→港币`、罗马序号仍靠 `normalizer.py`——云端路径**不能省归一化层**。

### 打开

http://127.0.0.1:8000 —— 默认合同 `zacl0603`(真实 Zero Finance 贷款协议,659 段 ≈85 min);已注册 `sample` / `zacl0603` / `xcash`(X Cash 新贷合同,671 段 ≈85 min),用 `?contract=<id>` 切换。拖动进度条测试。

## 添加新合同 / 工具速查

**合同只接受 TXT 进件**(业务侧直接交付,如 xcash):`cp` 到 `contracts/<id>.txt` → `app.py` + `contract.py` 的 `_CONTRACT_FILES` 各注册一行 → `?contract=<id>` 打开。原样复制,不做任何加工;系统对合同文件只读不写。完整步骤见 **`docs/architecture.md` §8**。

通用工具:
- 切片落盘:启动加 `SEEK_PROBE_DUMP_SEGMENTS=1` → 每个注册合同的原始切片写到 `contracts/<id>.segments.txt`(逐段原文 + 预估时间,调分段参数时对照看)

## 测试
```
uv run pytest -q
```

## 结果(zacl0603 实测)
- 分段数 / 预估时长:652 段 / ~85 min
- 冷 seek 首字节延迟:短段 ~1–4s(M3 Max CPU,RTF≈0.4;靠预载 + 缓存掩盖)
- 跨段音色一致性:全部段共用同一参考音 → 一致
- 英文地址/公司名:`yue` + L2 清洗后读成词;金额/身份证/日期:粤语中文

## 已知后续(未做,见 spec §2/§10)
- `streaming_mode=true` 降冷 seek 延迟(段格式随版本变,未押注)。
- 真实时长回填精修进度条。
- 段内精确子 seek(目前吸附段边界)。
- 粤语母语者地道性 go/no-go(单独关卡)。
