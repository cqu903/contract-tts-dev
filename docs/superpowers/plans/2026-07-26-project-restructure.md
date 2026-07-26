# 项目结构重整 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把项目收缩为"只有 seek_probe 这一个有效产物"的干净结构——删除全部 Qwen3-TTS 遗留，修正 pyproject 命名与依赖。

**Architecture:** 纯清理，无新代码。删除 untracked 的 Qwen 文件/样本/日志，瘦身 `pyproject.toml` 依赖并重生成 `uv.lock`，重命名项目，重写根 README，增补 `.gitignore`。`seek_probe/` 包与所有 import 路径原样不动；现有 pytest 套件作为回归护栏。

**Tech Stack:** Python 3.12+ / uv / pytest / FastAPI（seek_probe 自身，不改）。

**参考 spec:** `docs/superpowers/specs/2026-07-26-project-restructure-design.md`

## Global Constraints

- **目录名不动**：仓库根目录保持 `audio-with-qwen3-tts`，只改 `pyproject.toml` 内的 `name`。
- **`seek_probe/` 包结构不动**：不 promote 到根、不改任何 import 路径或 `uvicorn seek_probe.backend.app:app` 入口。
- **删除不可恢复**：本计划删除的多为 untracked 文件，git 历史里没有；删除前无需再确认（spec 已授权）。
- **依赖删除有前置门**：删 `pyproject.toml` 依赖前必须 grep 确认 `seek_probe/` 零引用，否则保留该条。
- **`uv.lock` 必须重生成**：每次改 `pyproject.toml` 依赖后跑 `uv lock`。
- **提交策略**：local-only 仓库，按用户习惯直接提交 `main`；每个 commit message 末尾加 `Co-Authored-By: Claude <noreply@anthropic.com>`。
- **回归护栏**：每个任务结束前 `uv run pytest -q` 必须全绿才能提交。

---

### Task 1: 删除 Qwen3-TTS 遗留文件

**Files:**
- Delete (根目录代码/文档): `CONTEXT.md`, `README.md`, `probes.ipynb`, `build_notebook.py`, `precache.py`, `smoke.py`
- Delete (日志): `precache.log`, `smoke.log`, `execute.log`
- Delete (Qwen 样本, `samples/`): `A1_base_yue.wav`, `A2_vd_yue_neutral.wav`, `B_vd_yue_cantonese_instruct.wav`, `ctrl_en.wav`, `ctrl_pu.wav`, `longform_split.wav`, `longform_whole.wav`, `smoke_putonghua.wav`, `vd_contrast_boy.wav`, `vd_contrast_gentle_f.wav`, `vd_contrast_mature_m.wav`, `vd_contrast_young_f.wav`
- Delete (杂项): `.DS_Store`, `seek_probe/.DS_Store`

**Interfaces:**
- Consumes: 无。
- Produces: 一个不再含 Qwen 遗留的工作目录（后续任务在此基础上改配置）。

- [ ] **Step 1: 确认这些文件确实存在且都是 untracked（删除前 sanity check）**

Run:
```bash
ls -1 CONTEXT.md README.md probes.ipynb build_notebook.py precache.py smoke.py precache.log smoke.log execute.log .DS_Store seek_probe/.DS_Store samples/A1_base_yue.wav samples/A2_vd_yue_neutral.wav samples/B_vd_yue_cantonese_instruct.wav samples/ctrl_en.wav samples/ctrl_pu.wav samples/longform_split.wav samples/longform_whole.wav samples/smoke_putonghua.wav samples/vd_contrast_boy.wav samples/vd_contrast_gentle_f.wav samples/vd_contrast_mature_m.wav samples/vd_contrast_young_f.wav
```
Expected: 列出全部 23 个路径，无 "No such file" 报错。

- [ ] **Step 2: 删除全部 Qwen 遗留文件**

Run:
```bash
rm -f CONTEXT.md README.md probes.ipynb build_notebook.py precache.py smoke.py \
      precache.log smoke.log execute.log \
      .DS_Store seek_probe/.DS_Store \
      samples/A1_base_yue.wav samples/A2_vd_yue_neutral.wav samples/B_vd_yue_cantonese_instruct.wav \
      samples/ctrl_en.wav samples/ctrl_pu.wav \
      samples/longform_split.wav samples/longform_whole.wav \
      samples/smoke_putonghua.wav \
      samples/vd_contrast_boy.wav samples/vd_contrast_gentle_f.wav samples/vd_contrast_mature_m.wav samples/vd_contrast_young_f.wav
```
Expected: 无输出（成功）。

- [ ] **Step 3: 确认 `samples/` 只剩 GPT-SoVITS 产物**

Run: `ls samples/`
Expected: 仅 `gptsovits_yue_m0.wav`、`gptsovits_yue_numbers.wav`。

- [ ] **Step 4: 跑测试，确认 seek_probe 未受影响**

Run: `uv run pytest -q`
Expected: 全绿（与重构前同等数量的 passed）。若有失败，说明删除误伤——停下排查（seek_probe 不应依赖任何被删文件）。

- [ ] **Step 5: 查看 git status，确认只剩预期变化**

Run: `git status`
Expected: 工作目录里这些 untracked 文件直接消失（不出现在 status 里，因为它们从未被 tracked）；`samples/` 下被删的也是 untracked，同样不出现。tracked 文件无变化。

- [ ] **Step 6: 提交（记录这次清理）**

由于删除的全是 untracked 文件，`git add -A` 不会捕获它们。此任务的"提交"其实是空提交无意义——**改为**：用 `git status` 确认工作目录干净后，直接进入 Task 2，不单独 commit（清理效果体现在工作目录，下一次有 tracked 改动的 commit 会涵盖）。

Run: `git status --short`
Expected: 空输出（工作目录与 HEAD 一致，被删的 untracked 文件不再存在）。

> 说明：如果希望删除动作留下历史痕迹，可选地 `git commit --allow-empty -m "chore: remove Qwen3-TTS legacy files (probes.ipynb, CONTEXT.md, smoke/precache, 12 old samples)"`。默认不做空提交。

---

### Task 2: 瘦身 pyproject.toml 依赖

**Files:**
- Modify: `pyproject.toml`（`[project].dependencies` 删 5 条）
- Regenerate: `uv.lock`

**Interfaces:**
- Consumes: Task 1 的干净工作目录。
- Produces: 一个只含 seek_probe 实际所需依赖的 `pyproject.toml` + 一致的 `uv.lock`。

- [ ] **Step 1: 前置门——grep 确认 seek_probe 零引用待删依赖**

Run:
```bash
grep -rEn 'soundfile|matplotlib|mlx_audio|mlx-audio|jupyter|ipykernel|IPython' seek_probe/ conftest.py
```
Expected: **无任何输出**（零引用）。
- 若有输出：说明 seek_probe 仍用到其中某个依赖——**停下**，把命中的依赖从删除列表移除，只删确认未用的，并在 PR 描述里记一笔。spec §C 已授权此回退。

- [ ] **Step 2: 从 `pyproject.toml` 删除 5 条依赖**

把 `[project].dependencies` 从：
```toml
dependencies = [
    "cn2an>=0.5.24",
    "fastapi>=0.140.0",
    "httpx>=0.28.1",
    "ipykernel>=7.3.0",
    "jupyter>=1.1.1",
    "matplotlib>=3.11.1",
    "mlx-audio>=0.4.5",
    "soundfile>=0.14.0",
    "uvicorn[standard]>=0.51.0",
]
```
改为：
```toml
dependencies = [
    "cn2an>=0.5.24",
    "fastapi>=0.140.0",
    "httpx>=0.28.1",
    "uvicorn[standard]>=0.51.0",
]
```
（删 `ipykernel`、`jupyter`、`matplotlib`、`mlx-audio`、`soundfile` 共 5 条。）

- [ ] **Step 3: 重生成 lockfile**

Run: `uv lock`
Expected: 成功退出，`uv.lock` 更新（移除上述 5 个包及其独占的传递依赖）。无报错。

- [ ] **Step 4: 同步环境，确认能装**

Run: `uv sync`
Expected: 成功；环境移除被删依赖。无 "import error" 类报错。

- [ ] **Step 5: 跑测试，确认 seek_probe 仍全绿**

Run: `uv run pytest -q`
Expected: 全绿。若有 import 失败，说明 Step 1 的 grep 漏了隐式依赖——回退该依赖到 `pyproject.toml`，重跑 Step 3–5。

- [ ] **Step 6: 提交**

Run:
```bash
git add pyproject.toml uv.lock
git commit -m "$(cat <<'EOF'
chore(deps): drop Qwen3-TTS-only dependencies

Remove ipykernel, jupyter, matplotlib, mlx-audio, soundfile — none used by
seek_probe (verified via grep). Regen uv.lock.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: 重命名项目 + 更新 description

**Files:**
- Modify: `pyproject.toml`（`name`、`description`；`[tool.uv] package = false` 保持）

**Interfaces:**
- Consumes: Task 2 的 `pyproject.toml`。
- Produces: 项目名 `cantonese-tts-probe`，描述反映 GPT-SoVITS 真实用途。

- [ ] **Step 1: 改 `pyproject.toml` 的 name 与 description**

把：
```toml
name = "audio-with-qwen3-tts"
version = "0.0.0"
description = "Local capability-boundary validation of mlx-audio + Qwen3-TTS (粤/普/英). A validation spike, not a service."
```
改为：
```toml
name = "cantonese-tts-probe"
version = "0.0.0"
description = "Cantonese contract-TTS seek/cache probe on GPT-SoVITS: segmentation + content-addressed cache + text normalization + seek mapping + web player."
```
（`version` 不动；`requires-python`、`[tool.uv]`、`[dependency-groups]` 不动。）

- [ ] **Step 2: 确认 pyproject 仍合法、环境仍可同步**

Run: `uv sync`
Expected: 成功（name 变更对虚拟环境无影响，但能验证 toml 未破坏）。

- [ ] **Step 3: 跑测试**

Run: `uv run pytest -q`
Expected: 全绿。

- [ ] **Step 4: 提交**

Run:
```bash
git add pyproject.toml
git commit -m "$(cat <<'EOF'
chore: rename project to cantonese-tts-probe

name + description now reflect the GPT-SoVITS Cantonese contract-TTS probe
(seek_probe). Directory name unchanged. Resolves the stale audio-with-qwen3-tts
naming left over from the original spike.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: 重写根 README + 增补 .gitignore

**Files:**
- Create (覆盖旧 Qwen README 的位置，已在 Task 1 删除): `README.md`
- Modify: `.gitignore`（末尾追加 2 条）

**Interfaces:**
- Consumes: Task 3 的新项目名 `cantonese-tts-probe`。
- Produces: 一份反映真实项目的根 README；`.gitignore` 覆盖 `.DS_Store` 与日志。

- [ ] **Step 1: 写新根 `README.md`**

内容（精确如下）：
```markdown
# cantonese-tts-probe

GPT-SoVITS 粤语合同朗读探针：分段 / 内容寻址缓存 / 文本归一化 /
seek 映射 / 网页播放器。（早期 Qwen3-TTS 能力边界 spike 已移除。）

详细文档与运行步骤见 **seek_probe/README.md**，
设计 spec 见 docs/superpowers/specs/。
```

- [ ] **Step 2: 给 `.gitignore` 追加 `.DS_Store` 与 `*.log`**

在 `.gitignore` 末尾追加：
```
# OS / logs
.DS_Store
*.log
```
（不动既有条目。）

- [ ] **Step 3: 确认 git status 干净且符合预期**

Run: `git status`
Expected: 仅 `README.md`（new file）、`.gitignore`（modified）两个 tracked 变化；无任何 stray untracked 文件（日志/`.DS_Store` 即便再生也被忽略）。

- [ ] **Step 4: 提交**

Run:
```bash
git add README.md .gitignore
git commit -m "$(cat <<'EOF'
docs: rewrite root README for GPT-SoVITS probe; ignore .DS_Store and *.log

README now describes cantonese-tts-probe and points to seek_probe/README.md.
.gitignore gains .DS_Store and *.log so stray OS/log files stop cluttering
git status.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: 端到端最终验证

**Files:** 无改动（纯验证）。

**Interfaces:**
- Consumes: Task 1–4 的全部成果。
- Produces: spec §"验证"四条全绿的证据。

- [ ] **Step 1: 从干净状态完整同步**

Run: `uv sync`
Expected: 成功，无报错。

- [ ] **Step 2: 全量测试**

Run: `uv run pytest -q`
Expected: 全绿（与重构前同数量 passed）。

- [ ] **Step 3: 包导入路径未受影响（关键：证明 dep 瘦身没删掉 module-level 隐式依赖）**

Run: `uv run python -c "import seek_probe.backend.app as m; print('import ok', m.app.__class__.__name__)"`
Expected: 打印 `import ok FastAPI`（或类似），无 ImportError/ModuleNotFoundError。
- 若失败：说明 Task 2 删多了依赖。回 Task 2 Step 1 重新 grep，补回缺失依赖，重 lock。

- [ ] **Step 4: （可选）真实起一次 uvicorn，确认启动期无错**

Run:
```bash
uv run uvicorn seek_probe.backend.app:app --port 8000 & SERVER_PID=$!
sleep 3
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/ || true
kill $SERVER_PID 2>/dev/null || true
wait $SERVER_PID 2>/dev/null || true
```
Expected: curl 打印一个 HTTP 状态码（200 或 404 均可，证明进程起来了、路由注册了），随后进程被杀。日志里无 traceback。
（GPT-SoVITS 引擎未起时，根路径可能 404 或返回错误——本步只验证 uvicorn 能拉起 app、无 import/启动期异常，不验证合成。）

- [ ] **Step 5: 最终 git status 干净**

Run: `git status --short && git log --oneline -5`
Expected: `git status --short` 空输出；`git log` 顶部依次是 Task 4 / Task 3 / Task 2 的 commit（Task 1 默认空提交则无，否则含空提交），其上是 `docs(restructure): add project-cleanup design spec`（0832c24）。

- [ ] **Step 6: 无需提交（本任务无改动）。**

若 Step 4 产生了任何 log 文件，`*.log` 已被忽略，不会污染 status。

---

## Self-Review

**Spec coverage** — 逐条对照 spec：
- §A 删除清单 → Task 1（全部 23 个文件一一列出）。✅
- §B 重命名（name/description，目录不动）→ Task 3。✅
- §C 依赖瘦身（5 条 + grep 前置门 + uv lock）→ Task 2。✅
- §D 新根 README → Task 4 Step 1。✅
- §E .gitignore 增补 → Task 4 Step 2。✅
- §清理后根布局 → Task 5 Step 5 验证（status 干净 + 仅预期文件）。✅
- §验证 4 条（uv sync / pytest / uvicorn / git status）→ Task 5 Step 1/2/3-4/5。✅
- §风险（删除不可恢复、依赖误删回退、lock 漂移）→ Global Constraints + Task 2 Step 1 回退分支 + Task 5 Step 3 回退分支。✅
- §非目标（不改目录名、不 promote、不动 refs、不动 2026-07-25 spec/plan）→ Global Constraints。✅

**Placeholder scan** — 无 TBD/TODO/「适当处理」；每个 code step 都给了精确 toml/text/shell。✅

**Type/name 一致性** — 项目名 `cantonese-tts-probe` 在 Task 3、Task 4、Task 5 Step 5 一致；依赖列表在 Task 2 Step 2 与 spec §C 一致；删除清单在 Task 1 与 spec §A 一致。✅

无问题，plan 可执行。
