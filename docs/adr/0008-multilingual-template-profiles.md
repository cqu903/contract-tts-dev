# 多语言 Template 按 profile 隔离处理与缓存

服务从单一粤语 `xcash` 扩展为 `xcash_yue`、`xcash_zh`、`xcash_en` 三个 Template。我们决定由调用方声明 `template_id`（`xcash` 规范化为 `xcash_yue`），每个 Template 独立拥有合同语言、朗读语言、切分规则、归一化规则和 Engine Profile；服务按请求动态选择 profile，不做自动语言识别。第一阶段云端提供三种语言 profile，本地仅提供粤语 profile，未配置的 profile 在上传阶段返回 `503`。

**后续扩展（2026-08-05）**：自托管 GPT-SoVITS 已提供 `zh/en/yue`，本地 adapter 也开放三个 Template profile。目标文本的 `text_lang` 与参考音的 `prompt_lang` 分离；普通话和英语在没有专属参考音时回退到粤语参考音进行跨语言合成，配置专属参考素材后使用对应参考语言。本段取代上文“本地仅提供粤语”的阶段性限制。

同日进一步把引擎选择从进程级下沉到 Engine Profile：`YUE/ZH/EN` 可分别选择 GPT-SoVITS 或 CosyVoice，未设置的语言回退到全局引擎。Engine Profile ID 包含规范化后的 adapter 名和语言，因此混合引擎配置天然隔离音频缓存，对外 Template interface 不增加 voice 或 engine 参数。

音频缓存身份改为 `sha256(canonical_template_id | normalized_tts_text | engine_profile_id | engine_profile_cache_version)`，从而隔离相同原文在不同语言和音色下的音频。旧 `xcash` 请求格式继续兼容，但旧版本的 `contract_id` 和音频缓存不迁移、不参与命中；它们自然过期即可。此决策修正 ADR-0006 中仅按引擎区分缓存的旧范围。
