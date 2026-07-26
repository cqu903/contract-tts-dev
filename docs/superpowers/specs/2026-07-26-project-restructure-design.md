# 项目结构重整设计 — 2026-07-26

## 背景

本项目（目录 `audio-with-qwen3-tts`）最初是 **Qwen3-TTS 能力边界验证 spike**
（`probes.ipynb` + `CONTEXT.md` + 12 个样本）。探针结论：Qwen3-TTS 本地开源模型
无地道粤语路径 → 降级改用 **GPT-SoVITS**，所有后续工作发生在 `seek_probe/` 包里。

结果：根目录残留大量 Qwen 时代的无效代码、文档、日志、样本；`pyproject.toml`
仍挂着 Qwen 专属依赖；项目名 `audio-with-qwen3-tts` 已名不副实。

本 spec 的目标：**把项目收缩为"只有 seek_probe 这一个有效产物"的干净结构**，
移除全部 Qwen 遗留，修正命名与依赖。

## 确认的关键决策（来自 brainstorming）

1. **遗留处理**：直接删除（不可恢复，但结论已沉淀在 memory 与 seek_probe 设计文档）。
2. **项目命名**：改 `pyproject.toml` 的 `name`/`description`，**目录名不动**（重命名目录
   会打断当前 session cwd，且无必要）。
3. **包结构**：`seek_probe/` 保持嵌套，规范可导入 Python 包，不 promote 到根。

## 变更清单

### A. 删除（全部为 untracked / Qwen 遗留）

根目录代码与文档：
- `CONTEXT.md`（Qwen 领域词汇表）
- `README.md`（Qwen spike 说明；将被新 README 取代）
- `probes.ipynb`（Qwen 探针 notebook）
- `build_notebook.py`（构建 notebook 的脚本）
- `precache.py`、`smoke.py`（Qwen 预缓存 / 冒烟脚本）

日志：
- `precache.log`、`smoke.log`、`execute.log`

Qwen 样本（`samples/` 下 12 个，约 17MB）：
- `A1_base_yue.wav`、`A2_vd_yue_neutral.wav`、`B_vd_yue_cantonese_instruct.wav`
- `ctrl_en.wav`、`ctrl_pu.wav`
- `longform_split.wav`、`longform_whole.wav`
- `smoke_putonghua.wav`
- `vd_contrast_boy.wav`、`vd_contrast_gentle_f.wav`、`vd_contrast_mature_m.wav`、`vd_contrast_young_f.wav`

杂项：
- `.DS_Store`、`seek_probe/.DS_Store`

**保留** `samples/gptsovits_yue_m0.wav`、`samples/gptsovits_yue_numbers.wav`
（当前 GPT-SoVITS 产物）。`samples/` 目录留在根。

**不动**：整个 `seek_probe/` 包、`docs/superpowers/{specs,plans}/`、`conftest.py`、
`uv.lock`（重生成）、`.gitignore`（增补）。

### B. 重命名 pyproject（目录名不变）

- `name`: `audio-with-qwen3-tts` → `cantonese-tts-probe`
- `description`: →
  `Cantonese contract-TTS seek/cache probe on GPT-SoVITS: segmentation + content-addressed cache + text normalization + seek mapping + web player.`

### C. 依赖瘦身

`pyproject.toml` `[project].dependencies` 删除 5 个 Qwen 专属依赖
（已确认 `seek_probe/` 内无任何 import）：

- `ipykernel>=7.3.0`
- `jupyter>=1.1.1`
- `matplotlib>=3.11.1`
- `mlx-audio>=0.4.5`
- `soundfile>=0.14.0`

保留：`cn2an`、`fastapi`、`httpx`、`uvicorn[standard]`，dev 组 `pytest`。

**实现前先验证**：`grep -rEn 'soundfile|matplotlib|mlx|jupyter|ipykernel' seek_probe/`
确认确实零引用后再删；删后 `uv lock` 重生成 `uv.lock`。

### D. 新根 README.md

短文档，不复制 `seek_probe/README.md` 细节（避免两份路径维护）：

```markdown
# cantonese-tts-probe

GPT-SoVITS 粤语合同朗读探针：分段 / 内容寻址缓存 / 文本归一化 /
seek 映射 / 网页播放器。（早期 Qwen3-TTS 能力边界 spike 已移除。）

详细文档与运行步骤见 **seek_probe/README.md**，
设计 spec 见 docs/superpowers/specs/。
```

### E. .gitignore 增补

追加：
- `.DS_Store`
- `*.log`

（日志以后不再污染 `git status`。其余条目原样保留。）

## 清理后根布局

```
audio-with-qwen3-tts/            ← 目录名不动
├── .gitignore                   ← +.DS_Store, +*.log
├── conftest.py
├── pyproject.toml               ← 重命名 + 瘦身
├── uv.lock                      ← uv lock 重生成
├── README.md                    ← 新写
├── docs/superpowers/
│   ├── plans/2026-07-25-cantonese-contract-tts-seek-probe.md
│   ├── specs/2026-07-25-cantonese-tts-seek-probe-design.md
│   └── specs/2026-07-26-project-restructure-design.md   ← 本文件
├── samples/                     ← 仅 gptsovits_yue_m0.wav, gptsovits_yue_numbers.wav
└── seek_probe/                  ← 包结构原样不动
```

## 验证（实现后必跑，全部通过才算完成）

1. `uv sync` — 瘦身后依赖可装，无残留引用报错。
2. `uv run pytest -q` — 现有测试全绿（删根文件未打断 seek_probe）。
3. `uv run uvicorn seek_probe.backend.app:app --port 8000` 能起来再 Ctrl-C
   — 导入路径未受影响（包仍可导入）。
4. `git status` — 仅剩预期改动（删除的 untracked 文件不出现，改动文件 = pyproject/
   uv.lock/README/.gitignore + 新 spec）。

## 风险

- **删除不可恢复**：A 节所列多为 untracked，删了 git 里也没有。已由用户确认结论已沉淀、
  原始探针不需要。
- **依赖误删**：C 节删前 grep 验证；若发现 seek_probe 隐式依赖（如 `soundfile` 写 WAV），
  则保留该条、其余照删。
- **`uv.lock` 漂移**：删依赖后必须 `uv lock` 重生成，否则 lock 与 pyproject 不一致。
- 其余改动（pyproject name/description、README、.gitignore）均在 git 内，可回滚。

## 非目标（本次不做）

- 不重命名仓库根目录。
- 不 promote `seek_probe/` 到根、不改任何 import 路径。
- 不动 `seek_probe/refs/` 下 untracked 的大体积参考音频（`cantonese_ref.wav` 等，
  已被 `.gitignore` 的 `seek_probe/refs/*.wav` 覆盖）—— 这是既有的运行时输入，
  与"移除 Qwen 遗留"无关。
- 不动 `docs/superpowers/{specs,plans}/2026-07-25-*`（那是 seek_probe 自身的设计文档）。
