# 03 — `xcash_en` 英语合同端到端支持

**What to build:** 增加英文合同到英语朗读的完整 Template 路径。调用方选择 `xcash_en` 后，服务使用英文句法/单词边界切分、英语专用 normalizer 和英语 Engine Profile，完成合同上传、分段、TTS 合成、缓存和播放；与其他 Template 的身份和缓存严格隔离。

**Blocked by:** 01 — Template Registry 与 `xcash_yue` 兼容链路

**Status:** done

- [x] `xcash_en` 被注册并接受英文合同；未注册或未配置时分别返回明确的 `400` 或 `503`
- [x] 英文切分使用句末标点、换行和单词边界，不能在单词中间截断
- [x] 英语 normalizer 保留英文词汇和专有名词，并处理日期、金额、百分比和计量单位的自然朗读
- [x] 合同编号、电话和账号等标识符支持逐位朗读
- [x] 混合语言片段不会导致整份合同被拒绝，主语言仍由 `xcash_en` 固定
- [x] 同一原文以不同 Template 上传时得到隔离的 `contract_id`、分段索引和缓存身份
- [x] 使用 fake engine 的端到端 API 测试证明英语 profile 被动态选择且可完成音频生成

## Comments

Implemented `xcash_en` with sentence/newline/whole-word segmentation, an English
normalizer for dates, currency, percentages, measurements, and identifiers, and a
separate Engine Profile. Mixed-language text is accepted as caller-declared English.
Local GPT-SoVITS returns `503`; Bailian enables the profile with its configured
English voice. API/fake-engine tests cover dynamic selection and isolation.
