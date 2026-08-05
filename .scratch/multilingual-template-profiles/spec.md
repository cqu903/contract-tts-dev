# 多语言 Template 与独立 TTS Profile

Status: ready-for-agent

## Problem Statement

当前服务只接受 `template_id=xcash`，并把所有合同按一套粤语切分、归一化和全局 TTS 引擎配置处理。服务需要支持粤语、普通话和英语合同朗读，但现有全局引擎、共享切分/归一化规则和仅按文本与引擎生成的缓存身份无法保证不同语言的处理结果和音频相互隔离。

## Solution

引入可扩展的 Template Registry。公开提供 `xcash_yue`、`xcash_zh`、`xcash_en` 三个 Template，并保留 `xcash` 作为 `xcash_yue` 的输入别名。每个 Template 独立声明合同语言、朗读语言、切分规则、TTS 归一化规则和 Engine Profile；服务在每次请求时根据规范化后的 `template_id` 动态选择完整处理方案。

原始合同始终保持不变，只有送入 TTS 的文本按 Template 归一化。合同索引、分段、引擎配置和音频缓存均按 Template 隔离。第一阶段云端提供三种语言 profile，本地引擎只提供粤语 profile；未配置的 Template 在上传阶段返回明确的 `503`。

## User Stories

1. 作为调用方，我希望上传中文合同并选择 `xcash_yue`，从而获得粤语朗读合同。
2. 作为调用方，我希望上传中文合同并选择 `xcash_zh`，从而获得普通话朗读合同。
3. 作为调用方，我希望上传英文合同并选择 `xcash_en`，从而获得英语朗读合同。
4. 作为旧客户端，我希望继续发送 `template_id=xcash`，从而不必立即修改请求格式。
5. 作为调用方，我希望 `xcash` 与 `xcash_yue` 在规范化后代表同一个 Template，从而避免产生两套粤语身份。
6. 作为调用方，我希望同一份原文使用不同 Template 时得到不同的 `contract_id`，从而隔离不同语言的合同索引和 seek 结构。
7. 作为调用方，我希望由我声明 `template_id`，从而明确控制合同语言和朗读语言；服务不应擅自自动识别或切换 Template。
8. 作为调用方，我希望合同主体语言之外可以出现少量混合语言片段，从而支持英文公司名、地址和产品名等真实合同内容。
9. 作为粤语用户，我希望 `xcash_yue` 继续使用现有粤语专用切分和归一化规则，从而保持当前朗读质量。
10. 作为普通话用户，我希望 `xcash_zh` 拥有独立的普通话切分和归一化规则，从而不被粤语发音修正规则影响。
11. 作为英语用户，我希望 `xcash_en` 按英文句法和单词边界切分，从而不会在单词中间截断音频段。
12. 作为英语用户，我希望日期、金额、百分比和计量单位转换为自然英语读法，而合同编号、电话和账号可以逐位朗读。
13. 作为普通话用户，我希望普通话归一化只改变 TTS 输入，不把原始繁体合同整段转换为简体，从而保留法律文本和专有名词的原字形。
14. 作为调用方，我希望 API 返回和存储的原始合同始终不变，从而展示内容与上传内容完全一致。
15. 作为系统维护者，我希望每个 Template 在请求时动态绑定自己的 Engine Profile，从而无需重启服务或修改全局语言环境即可处理不同语言。
16. 作为系统维护者，我希望第一阶段云端提供粤语、普通话和英语 profile，而本地只提供粤语 profile，从而分阶段交付语言能力。
17. 作为调用方，我希望选择未配置的 Template 时在上传阶段收到明确的 `503`，从而不会拿到一个后续无法播放的合同。
18. 作为系统维护者，我希望不同 Template、Engine Profile 或 profile 版本永远不会共享不兼容的音频缓存，从而避免播放错误语言或旧配置音频。
19. 作为系统维护者，我希望旧缓存不参与新请求命中，从而避免无 Template 元数据的旧音频被错误复用。
20. 作为未来维护者，我希望新增语言时只需注册新的 Template 和 profile，而不修改 API 主流程，从而以较低成本扩展语言。

## Implementation Decisions

- **Template canonicalization**：公开 Template 只有 `xcash_yue`、`xcash_zh`、`xcash_en`。`xcash` 是 `xcash_yue` 的输入别名；在计算合同身份、选择处理规则和生成缓存身份前完成规范化。
- **Template Registry**：使用代码内的可扩展 Registry 管理 Template。每个定义包含 canonical ID、别名、合同语言、朗读语言、独立切分 profile、独立 normalizer 和可用 Engine Profile。
- **Caller-declared language**：`template_id` 是调用方对合同语言和朗读方案的声明。服务不做整份合同自动语言识别，也不根据检测结果自动切换 Template。
- **Mixed-language input**：允许主语言之外的少量混合语言片段；主语言仍由 Template 固定，异语片段由该 Template 的 normalizer 和对应引擎处理。
- **Independent segmentation**：三个 Template 都拥有独立切分规则。粤语和普通话可以从现有中文规则开始，但配置必须可分别调优；英语使用英文句末标点、换行和单词边界，不能在单词中间截断。目标长度、软上限、硬上限和时长估算属于切分 profile。
- **Template-specific normalization**：原始合同不变，只有 TTS 输入文本归一化。`xcash_yue` 保留现有粤语数字、金额、日期、编号和粤语发音修正规则；`xcash_zh` 使用普通话读法规则且不做全量繁体转简体；`xcash_en` 保留英文词汇和专有名词，转换自然语言数字/日期/金额/百分比/单位，并对编号、电话和账号支持逐位读取。
- **Engine Profile selection**：服务按请求的 Template 动态选择 Engine Profile，不依赖全局语言环境、重启或修改环境变量切换语言。第一阶段云端提供 `bailian_yue`、`bailian_zh`、`bailian_en`，本地 GPT-SoVITS 只提供粤语 profile。每个 profile 的音色、模型、语言参数、参考音或服务端 voice、合成参数和缓存版本独立管理。
- **Upload validation**：上传时先验证 Template 和对应 Engine Profile 是否已注册且可用。未知 Template 返回 `400`；已知但未配置的 profile 返回 `503`；校验失败时不创建合同、不保存原文、不启动预热任务。
- **Contract identity**：`contract_id` 由 canonical Template ID 和原文共同决定。相同原文在不同 Template 下必须得到不同的合同身份和独立分段索引。
- **Cache identity**：音频缓存身份包含 canonical Template ID、最终送入 TTS 的归一化文本、Engine Profile ID 和 profile cache version。相同文本只有在同一 Template、同一 Engine Profile 和同一版本下才允许跨 Contract 复用。
- **Legacy cache policy**：继续兼容旧的 `template_id=xcash` 请求格式，但不读取或迁移旧版本 `contract_id` 和旧音频缓存。旧缓存自然过期；所有新请求使用新的缓存身份。
- **External behavior seam**：以 API 驱动的 Template Registry 流水线作为最高测试 seam，使用 fake/mock Engine 验证外部行为，不依赖真实 TTS 服务。

## Testing Decisions

- 测试只验证外部行为和稳定契约，不绑定具体内部函数拆分；需要覆盖 API 响应、合同身份、分段结果、TTS 输入和缓存命中行为。
- API 测试沿用现有 FastAPI `TestClient` 和 fake engine，验证三个 Template、`xcash` 别名、未知 Template 的 `400`、未配置 profile 的 `503`、原文保持不变以及各 Template 的动态 profile 选择。
- Contract 测试验证 canonical Template ID 参与 `contract_id`，相同原文在 `xcash_yue`、`xcash_zh`、`xcash_en` 下隔离。
- Segmentation 测试为三个 Template 分别提供中文粤语、中文普通话和英文样例，验证句末边界、换行边界、长段拆分、英文单词边界以及估算时长规则。
- Normalizer 测试分别验证粤语现有回归样例、普通话数字/金额/日期规则、繁体字不被全量转换、英语日期/金额/百分比/单位以及编号逐位规则，并覆盖混合语言片段。
- Cache 测试验证 Template、Engine Profile、profile version 或最终 TTS 文本变化时缓存键变化；相同 Template/Profile/版本下相同 TTS 文本仍可跨 Contract 复用；旧格式缓存不会命中新请求。
- Engine adapter 测试继续使用现有 HTTP transport mock，验证每个 profile 发送正确的语言、voice、参考音和合成参数。
- 回归测试应确保现有粤语 `xcash` 客户端行为仍然可用，但其新请求走 canonical `xcash_yue` 和新的缓存命名空间。

## Out of Scope

- 本次不实现自动语言识别、自动 Template 选择或根据文本内容纠正调用方的 `template_id`。
- 本次不开放除三个正式 Template 之外的任意语言 ID，也不开放调用方自定义 voice、engine 或 normalizer 参数。
- 本次不迁移旧 `contract_id`、旧音频缓存或无 Template 元数据的历史记录。
- 本次不要求本地 GPT-SoVITS 立即提供普通话和英语 profile；这些 profile 的本地资源准备另行处理。
- 本次不改变原始合同展示、存储或 API 返回的原文内容。
- 本次不承诺母语级音质验收、跨供应商音色一致性或完整语言学覆盖；这些属于各 Engine Profile 的后续质量验证。
- 本次不要求新增前端语言选择界面；前端改造可在 API 和 profile 稳定后单独规划。

## Further Notes

- 普通话和英语云端 profile 的具体 voice/model 标识属于部署配置，必须在接入对应 provider 时通过可用性和试听测试确认。
- `CONTEXT.md` 和 ADR-0008 已记录 Template、Reading Language、Engine Profile 和 Cache Identity 的领域约定；实现时如发现代码与这些约定冲突，应优先修正实现或明确提出 ADR 变更。
- 规格完成后可使用 `/to-tickets` 将实现拆分为按阻塞关系排序的 tickets，再使用 `/implement` 逐项实现并以 `/code-review` 收尾。
