# 多语言 Template 按 profile 隔离处理与缓存

服务从单一粤语 `xcash` 扩展为 `xcash_yue`、`xcash_zh`、`xcash_en` 三个 Template。我们决定由调用方声明 `template_id`（`xcash` 规范化为 `xcash_yue`），每个 Template 独立拥有合同语言、朗读语言、切分规则、归一化规则和 Engine Profile；服务按请求动态选择 profile，不做自动语言识别。第一阶段云端提供三种语言 profile，本地仅提供粤语 profile，未配置的 profile 在上传阶段返回 `503`。

音频缓存身份改为 `sha256(canonical_template_id | normalized_tts_text | engine_profile_id | engine_profile_cache_version)`，从而隔离相同原文在不同语言和音色下的音频。旧 `xcash` 请求格式继续兼容，但旧版本的 `contract_id` 和音频缓存不迁移、不参与命中；它们自然过期即可。此决策修正 ADR-0006 中仅按引擎区分缓存的旧范围。
