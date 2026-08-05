# 01 — Template Registry 与 `xcash_yue` 兼容链路

**What to build:** 建立可扩展的 Template Registry，并让现有粤语合同通过 canonical `xcash_yue` 完成上传、分段、归一化、TTS 合成、缓存和播放；旧客户端发送 `xcash` 时继续工作，但进入新的 canonical 身份和缓存命名空间。

**Blocked by:** None — can start immediately

**Status:** done

- [x] 服务注册并接受 `xcash_yue`，同时把 `xcash` 规范化为 `xcash_yue`；未知 Template 返回 `400`
- [x] Template Profile 能独立提供合同语言、朗读语言、切分规则、normalizer 和 Engine Profile
- [x] `contract_id` 使用 canonical Template ID，同一原文在不同 Template 下不会共享合同身份
- [x] 音频缓存身份包含 Template、最终 TTS 文本、Engine Profile 和 profile cache version；旧缓存不会命中新请求
- [x] 上传阶段验证 profile 可用性；未配置 profile 返回 `503`，且不创建合同或启动预热
- [x] 现有粤语上传、分段、TTS、seek、缓存命中和 `xcash` 回归行为通过 API 与 fake engine 测试

## Comments

Implemented with a Template Registry, canonical `xcash_yue` aliasing, persisted Template metadata, profile-selected engine providers, versioned cache identities, and legacy-cache isolation. The complete multilingual suite passes 84 tests; `uv run python -m compileall -q backend` passes.
