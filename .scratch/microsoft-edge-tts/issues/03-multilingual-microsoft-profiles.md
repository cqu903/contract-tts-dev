# 03 — 扩展 Microsoft Engine Profile 到普通话和英语

**What to build:** 让同一服务实例中的粤语、普通话和英语 Template 都能独立选择 Microsoft/Edge 或现有 Engine Provider，并获得适合合同朗读的默认 voice 和可部署调整的基准 rate。部署人员可以混合配置三种语言，而调用方和播放器不需要改变请求或交互方式。

**Blocked by:** 02 — 打通粤语 Microsoft/Edge TTS tracer bullet.

**Status:** resolved

- [x] 全局 Engine Provider 配置选择 `microsoft` 时，粤语、普通话和英语 Engine Profile 都能回退使用 Microsoft；按 Reading Language 的配置仍可分别覆盖全局选择。
- [x] 单个服务实例可以同时运行 Microsoft、GPT-SoVITS 和 CosyVoice 的不同语言 Profile，请求按 Template 动态选择正确 Provider。
- [x] 普通话 Microsoft Profile 默认使用 `zh-CN-YunyangNeural` 和 `+0%`，并支持独立 voice/rate 覆盖。
- [x] 英语 Microsoft Profile 默认使用 `en-HK-SamNeural` 和 `+0%`，并支持独立 voice/rate 覆盖。
- [x] 粤语继续默认使用 `zh-HK-WanLungNeural` 和 `+0%`，三种语言的配置互不覆盖。
- [x] 每个 Microsoft Engine Profile 都包含自己的 Reading Language、voice、canonical rate、输出格式、Driver 和 synthesis fingerprint。
- [x] 只修改一种语言的 voice 或 rate 时，只有该语言进入新的缓存命名空间，其他语言的有效缓存仍可命中。
- [x] 三种语言的 Microsoft Segment 都返回原生 MP3 与 `audio/mpeg`；选择 GPT-SoVITS 或 CosyVoice 的 Profile 继续返回 WAV 与 `audio/wav`。
- [x] Microsoft Provider 不要求百炼 API key；只有实际选择 CosyVoice 的 Profile 才受其凭据可用性约束。
- [x] 三种语言的 voice 非空和 rate 语法均在本地校验，但启动过程不联网验证 voice 是否存在。
- [x] 合同上传和 Segment 请求继续只由 Template 决定 Reading Language 与 Engine Profile，不开放逐请求 provider、driver、voice、rate、volume 或 pitch。
- [x] 服务端基准 rate 与现有前端播放倍速可以叠加，播放器的音量、保调播放和倍速默认值保持不变。
- [x] 任一语言的 Microsoft rate 变化都不会改变该 Template 的 Segment 边界、`est_dur_s`、`total_est_s` 或现有 seek 数据契约。
- [x] 任一语言 Edge 失败时仅影响该请求：匹配缓存继续返回，未缓存请求返回 `502`，且不会自动切换到另一 Provider。
- [x] 应用 HTTP seam 覆盖全局 Microsoft、三种按语言覆盖和混合 Provider 矩阵，并验证每个 Template 选择正确 voice、rate、格式与缓存命名空间。
- [x] Provider 接口测试以相同上层调用方式替换 fake Edge Driver 和 fake Azure Driver，证明未来更换 Driver 不需要修改 Template 或 HTTP 契约。
- [x] 配置测试覆盖三语言默认值、独立覆盖、缺失或未知 Driver、空 voice、合法和非法 rate，以及未显式选择 Microsoft 时的原有默认行为。
- [x] 所有现有多语言 Template、normalizer、segmenter、GPT-SoVITS、CosyVoice 和前端播放回归测试继续通过。

## Answer

Microsoft/Edge Engine Profile 已扩展到粤语、普通话和英语，并支持全局回退、逐 Reading Language 覆盖及与 GPT-SoVITS/CosyVoice 混合部署。普通话默认 `zh-CN-YunyangNeural`，英语默认 `en-HK-SamNeural`，三语言 rate 默认 `+0%`；冻结的 `MicrosoftReadingLanguageConfig` 保证 voice/rate 配置独立成组。三语言 Provider 在启动时仅做本地校验并生成独立 synthesis fingerprint，不访问 Edge 网络。

验证：`uv run --frozen pytest -q`（218 passed），`node --test frontend/playback.test.mjs`（3 passed），`uv run --frozen python -m compileall -q backend tests`；Standards/Spec 双轴复审均无发现。
