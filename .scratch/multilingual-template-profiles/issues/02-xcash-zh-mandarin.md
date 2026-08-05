# 02 — `xcash_zh` 普通话合同端到端支持

**What to build:** 增加中文合同到普通话朗读的完整 Template 路径。调用方选择 `xcash_zh` 后，服务使用独立的普通话切分、归一化和 Engine Profile，完成合同上传、分段、TTS 合成、缓存和播放；与 `xcash_yue` 的合同身份及音频缓存严格隔离。

**Blocked by:** 01 — Template Registry 与 `xcash_yue` 兼容链路

**Status:** done

- [x] `xcash_zh` 被注册并接受中文合同；未注册或未配置时分别返回明确的 `400` 或 `503`
- [x] 普通话使用独立的切分 profile，可独立调整边界、长度和时长估算
- [x] 普通话使用独立的 normalizer，覆盖数字、金额、日期、编号等读法
- [x] 普通话 TTS 输入不做全量繁体转简体，原始合同文本保持不变
- [x] 同一原文以 `xcash_zh` 和 `xcash_yue` 上传时得到不同 `contract_id`、分段索引和缓存身份
- [x] 使用 fake engine 的端到端 API 测试证明普通话 profile 被动态选择且可完成音频生成

## Comments

Implemented `xcash_zh` with an independent Mandarin splitter, duration estimator,
number/date/percentage/identifier normalizer, and Engine Profile. Local GPT-SoVITS
reports this profile as unavailable (`503`); Bailian enables it when an API key is
configured. API tests cover profile selection, audio generation, identity/cache
isolation, and the unchanged stored source text. `uv run pytest -q` passes 84 tests.
