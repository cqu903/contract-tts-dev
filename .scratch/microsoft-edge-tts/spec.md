# Microsoft / Edge TTS 正式引擎

Status: implemented

## Problem Statement

当前合同朗读服务只把 GPT-SoVITS 与百炼 CosyVoice 作为正式 Engine Provider，无法通过同一套 Template 与 Engine Profile 配置选择 Microsoft 语音能力。业务需要使用 `edge-tts` 为粤语、普通话和英语合同提供可配置的文字转语音，但现有引擎接口、音频响应与 Segment Cache 默认假设输出为 WAV，不能安全承载 Edge 原生 MP3；现有缓存身份也不能自动隔离 Driver、voice、rate、音频格式或 adapter 版本变化。

同时，当前 Edge 在线 TTS 没有项目级 API key、租户或地域边界。若把它直接固化为业务层的独立引擎，未来切换到正式 Azure Speech 时将迫使 Template、配置和调用链再次改造。服务需要一个稳定的 `microsoft` Engine Provider，以 Edge 作为当前可替换 Driver，并明确失败策略、合同数据外发边界与生产迁移路径。

## Solution

新增与 GPT-SoVITS、CosyVoice 同级的 `microsoft` Engine Provider，并允许全局或按 Reading Language 选择它。Provider 内部通过显式配置选择 Driver；本期实现 `edge` Driver，未来正式生产可增加或替换为 `azure` Driver，而 Template、Engine Profile 选择方式和上层合成调用契约保持不变。

粤语、普通话和英语分别支持服务端 `voice` 与基准 `rate` 配置，默认采用适合合同朗读的 `zh-HK-WanLungNeural`、`zh-CN-YunyangNeural` 与 `en-HK-SamNeural`，三种语言的默认基准语速均为 `+0%`。请求方不能逐请求修改引擎、音色或语速；现有前端播放倍速继续独立工作。

Edge Driver 保留上游原生 MP3，不转码。合成结果、HTTP 响应和 Segment Cache 改为格式感知；GPT-SoVITS 与 CosyVoice 继续输出 WAV。Cache Identity 加入稳定的合成指纹，自动隔离 Driver、voice、rate、音频格式和 adapter 版本变化。Edge 不可用时不自动切换其他引擎：已有缓存照常返回，未缓存 Segment 返回 `502`。

服务启动只做本地配置校验，不访问 Edge 网络服务。另提供独立的三语言诊断命令，用真实在线合成验证配置和试听结果。运维文档必须明确说明：使用 Edge Driver 会把归一化后的合同 Segment（可能包含 PII）发送到 Edge 在线服务；正式生产后可在同一 `microsoft` Provider 下改用带正式凭据、地域和服务协议的 Azure Driver。

## User Stories

1. 作为部署人员，我希望把 `microsoft` 配置为正式 Engine Provider，从而像选择 GPT-SoVITS 或 CosyVoice 一样选择 Microsoft 语音能力。
2. 作为部署人员，我希望不修改 Template 或对外 API 就能启用 Microsoft Provider，从而保持现有合同处理流水线稳定。
3. 作为部署人员，我希望分别为粤语、普通话和英语 Template 选择 Engine Provider，从而在同一服务实例内混合使用 Microsoft、GPT-SoVITS 与 CosyVoice。
4. 作为现有部署的维护者，我希望没有显式选择 `microsoft` 时仍沿用原来的引擎选择，从而避免升级后意外改变声音或产生数据外发。
5. 作为架构维护者，我希望 `microsoft` 是上层依赖的稳定 Provider 身份，从而将 Edge 与未来 Azure 的差异限制在 Provider 内部。
6. 作为架构维护者，我希望通过显式 Driver 配置启用 `edge`，从而清楚区分当前无凭据 Edge 在线服务和未来正式 Azure Speech 服务。
7. 作为未来迁移负责人，我希望 Azure Driver 遵循与 Edge Driver 相同的上层合成契约，从而只需小范围替换 Driver，而不重写 Template 和 API 流程。
8. 作为粤语合同用户，我希望 Microsoft Provider 默认使用 `zh-HK-WanLungNeural`，从而获得适合粤语合同朗读的男声基线。
9. 作为普通话合同用户，我希望 Microsoft Provider 默认使用 `zh-CN-YunyangNeural`，从而获得适合正式叙述的普通话男声基线。
10. 作为英语合同用户，我希望 Microsoft Provider 默认使用 `en-HK-SamNeural`，从而获得符合香港英语场景的男声基线。
11. 作为部署人员，我希望可以分别覆盖粤语、普通话和英语的 voice，从而在不改代码的情况下调整每种 Reading Language 的音色。
12. 作为部署人员，我希望可以分别覆盖三种语言的基准 rate，从而按合同朗读效果调整语速。
13. 作为默认配置的使用者，我希望三种语言的基准 rate 均为 `+0%`，从而先使用供应方的自然语速并保留明确基线。
14. 作为 API 调用方，我希望请求结构保持不变，从而无需在每次请求中传递 provider、driver、voice 或 rate。
15. 作为产品维护者，我希望不向请求方开放逐请求 voice 与 rate，从而保证 Engine Profile、审计与缓存身份可预测。
16. 作为播放器用户，我希望前端播放倍速继续可调，从而能够临时加速或减速，而不修改服务端的基准合成结果。
17. 作为播放器用户，我接受服务端基准 rate 与前端播放倍速叠加，从而保留部署基线和个人播放偏好两层控制。
18. 作为合同用户，我接受 Edge rate 不修正 `total_est_s`，从而保留现有进度条模型，即使总时长显示可能存在明显偏差。
19. 作为合同用户，我希望 Segment 顺序与进度条的相对定位继续工作，从而仍可按现有 Segment 边界 seek。
20. 作为浏览器客户端，我希望 Edge 合成的 Segment 以正确的 `audio/mpeg` 返回，从而能够直接播放原生 MP3。
21. 作为现有引擎用户，我希望 GPT-SoVITS 与 CosyVoice 的 Segment 继续以 `audio/wav` 返回，从而保持现有音频格式不变。
22. 作为平台维护者，我希望服务不把 Edge MP3 转码为 WAV，从而避免额外计算、音质损失与转码依赖。
23. 作为缓存使用者，我希望缓存条目携带音频格式和媒体类型，从而不会用 WAV 扩展名或 Content-Type 返回 MP3 数据。
24. 作为缓存使用者，我希望相同 Template、归一化文本与完整合成配置可以跨 Contract 复用 Segment 音频，从而保留内容寻址缓存收益。
25. 作为部署人员，我希望切换 Driver 后自动进入新的缓存命名空间，从而不会让 Azure 命中 Edge 生成的音频，反之亦然。
26. 作为部署人员，我希望修改 voice 后自动隔离旧缓存，从而无需人为提升缓存版本才能听到新音色。
27. 作为部署人员，我希望修改 rate 后自动隔离旧缓存，从而无需清空整个缓存即可使用新语速。
28. 作为维护者，我希望音频格式或 adapter 版本变化时自动隔离缓存，从而不会复用协议或编码不兼容的旧结果。
29. 作为运维人员，我希望在 Edge 暂时不可用时仍能返回已经缓存的 Segment，从而尽量维持已生成合同内容的播放能力。
30. 作为 API 调用方，我希望未缓存 Segment 的 Edge 合成失败明确返回 `502`，从而能区分上游语音服务失败与客户端输入问题。
31. 作为运维人员，我希望 Edge 失败时不自动回退到 GPT-SoVITS 或 CosyVoice，从而避免同一合同在没有明确提示的情况下混用音色或供应方。
32. 作为运维人员，我希望失败的预热不写入空文件或损坏缓存，从而让后续 Segment 请求能够重新尝试并收到明确结果。
33. 作为服务部署人员，我希望启动过程只校验本地配置而不访问 Edge，从而不让临时网络波动阻止进程启动。
34. 作为服务部署人员，我希望 voice 为空、rate 格式错误、Driver 不受支持或 Microsoft 配置不完整时尽早得到本地配置错误，从而避免把明显错误推迟到真实合同播放阶段。
35. 作为运维人员，我希望有独立的三语言诊断命令，从而能在部署后主动验证网络、voice、rate、MP3 输出和实际听感。
36. 作为运维人员，我希望诊断命令对每种语言生成可试听文件并汇总成功或失败，从而快速定位单一语言配置问题。
37. 作为安全与合规负责人，我希望运维文档明确记录 Edge Driver 的合同文本外发范围，从而在启用前评估可能包含 PII 的数据处理风险。
38. 作为安全与合规负责人，我希望只有显式选择 Microsoft Provider 与 Edge Driver 的部署才发生 Edge 数据外发，从而避免升级本身改变数据边界。
39. 作为未来生产负责人，我希望文档说明迁移到正式 Azure Driver 时应配置凭据、地域与服务协议，从而为正式 Microsoft 服务接入保留清晰路径。
40. 作为维护者，我希望真实 Edge 网络调用不进入默认自动化测试，从而保持 CI 快速、稳定且不会外发测试或合同文本。

## Implementation Decisions

- **稳定 Provider 与可替换 Driver**：注册新的 canonical Engine Provider `microsoft`。Provider 内部依赖统一 Driver 接口；本期只实现 canonical Driver `edge`。未来 `azure` 作为同一 Provider 下的新 Driver，而不是新增与 `microsoft` 平级的 Provider。
- **显式启用**：现有全局和按 Reading Language 的引擎选择配置接受 `microsoft`。当任一 Engine Profile 选择 `microsoft` 时，必须显式配置 Microsoft Driver 为 `edge`；缺失或未知 Driver 属于本地配置错误。未选择 `microsoft` 时，不初始化真实 Edge 网络会话，也不改变现有默认引擎行为。
- **配置契约**：Microsoft Provider 提供三组按 Reading Language 隔离的 voice 与 rate 配置。默认 voice 分别为粤语 `zh-HK-WanLungNeural`、普通话 `zh-CN-YunyangNeural`、英语 `en-HK-SamNeural`；默认 rate 均为 `+0%`。rate 使用 Edge 接受的带正负号整数百分比形式，例如 `-10%`、`+0%`、`+15%`。
- **本地配置校验**：启动时校验 Driver 名称、voice 非空和 rate 语法，但不联网获取 voice 列表或执行试合成。配置中的 voice 是否真实可用由独立诊断命令或首次合成确认。
- **服务端固定 Engine Profile**：provider、driver、voice 与 rate 均由部署配置进入 Engine Profile；合同上传和 Segment 请求不新增这些参数。`volume` 与 `pitch` 不进入本期服务端配置，前端音量与播放倍速继续作为播放器行为。
- **统一合成结果**：引擎适配层不再只暴露无格式的字节流，而是向上层提供完整 Audio Artifact，至少包含音频字节或可收集的字节流、canonical 音频格式、HTTP media type 与缓存文件后缀。上层不得根据 Provider 名称猜测格式。
- **Edge Driver 行为**：Edge Driver 使用 `edge-tts` 的异步接口，以归一化后的单个 Segment、配置 voice 和 rate 发起在线合成，只收集音频事件并产出非空 MP3 Audio Artifact。与音频无关的边界或元数据事件不混入音频字节。
- **依赖管理**：加入 `edge-tts` 运行时依赖并锁定解析版本。升级可能影响输出的 adapter 或依赖时必须更新合成指纹版本，并运行三语言诊断。
- **原生音频格式**：Edge Driver 的 canonical 输出为 MP3，HTTP media type 为 `audio/mpeg`；不在服务端转码。现有 GPT-SoVITS 与 CosyVoice adapter 明确声明 WAV Audio Artifact，HTTP media type 保持 `audio/wav`。
- **动态 Segment 响应**：Segment API 继续整段合成完成后再返回，但 Content-Type 来自 Audio Artifact 或缓存元数据。上传、合同索引、Segment 编号和 preload API 结构保持不变。
- **格式感知缓存**：Segment Cache 以 Audio Artifact 为写入和读取单位，并持久化足以恢复正确格式、media type 与后缀的元数据。缓存文件后缀必须与实际格式一致；读取时若文件、manifest 与请求身份不一致，视为未命中或损坏条目，绝不带错误 Content-Type 返回。
- **Cache Identity**：缓存键继续包含 canonical Template ID、最终送入 TTS 的文本、Engine Profile ID 与人工 cache version，并新增确定性的 synthesis fingerprint。fingerprint 至少覆盖 canonical Driver、voice、canonical rate、音频格式和 adapter 版本；未来新增任何会改变音频结果或编码的配置时也必须进入 fingerprint。
- **自动隔离与人工版本并存**：Driver、voice、rate、格式或 adapter 版本变化依靠 fingerprint 自动隔离，不要求运维人员手动 bump cache version。人工 cache version 继续保留，用于未被结构化字段覆盖的紧急或业务性失效。
- **旧缓存策略**：引入新 Cache Identity 后不迁移旧命名空间，旧条目按现有滑动 TTL 自然淘汰。实现必须保证旧 WAV 文件不会被解释为 MP3；本次不要求跨新旧缓存键回退查询。
- **缓存优先的失败语义**：Segment 请求始终先查询与当前 synthesis fingerprint 完全匹配的缓存。命中时直接返回缓存 Audio Artifact，不访问 Edge；未命中时才调用 Driver。
- **无自动回退**：Edge Driver 失败后不调用 GPT-SoVITS、CosyVoice 或其他 Driver。连接、超时、上游拒绝、无效 voice、协议错误、空音频和流中断统一转换为稳定的 Microsoft 合成错误，并由 Segment API 返回 `502`。
- **缓存写入原子性**：只有完整、非空且格式已知的 Audio Artifact 才能提交到缓存。合成失败、取消或流中断不得留下可命中的半成品；同一缓存键继续使用单航班/锁机制避免并发重复合成。
- **预热行为**：上传后的首段预热继续是后台最佳努力任务。Edge 预热失败只记录可诊断信息，不使合同上传失败，也不写入失败缓存；随后真实 GET 在仍未命中时重新合成，并按统一规则返回 `502`。
- **时长与 seek**：Microsoft rate 不参与 Segment 预计时长或 `total_est_s` 修正。现有基于 Template 文本估算的时长、Segment 边界和前端进度条算法保持不变，接受显示时长与真实音频存在明显偏差。
- **诊断命令**：提供不随服务启动自动运行的三语言诊断入口。它从同一部署配置读取 Driver、voice 与 rate，分别使用固定的短测试句合成粤语、普通话和英语 MP3，验证每个结果非空且格式正确，保存可试听文件，逐项报告结果，并在任一语言失败时以非零状态退出。
- **诊断安全提示**：诊断运行前明确提示测试文本会发送到外部 Edge 在线服务。诊断只使用仓库内固定、无敏感信息的短句，不读取真实 Contract 或缓存内容。
- **运维文档**：引擎配置、三语言默认值、显式启用方法、重启生效要求、动态音频格式、诊断步骤、失败与无回退语义、缓存隔离方式和数据外发边界必须写入运维文档与示例配置。
- **数据外发边界**：选择 Edge Driver 表示允许将归一化后的合同 Segment 发送到 Edge 在线 TTS；内容可能包含姓名、地址、金额、账号等 PII。当前 Driver 不提供本项目专属 API key、租户或地域保证，不能把它描述成已经具备 Azure 企业服务边界。
- **未来 Azure 兼容点**：Azure Driver 必须复用 Microsoft Provider 的 Audio Artifact、错误和 synthesis fingerprint 契约；凭据、region、endpoint、部署模型以及任何影响输出的设置留在 Driver 内部，并在实现 Azure 时加入 fingerprint，不泄漏到 Template 或请求 API。

## Testing Decisions

- 自动化测试只验证可观察行为和稳定接口，不断言私有函数拆分、具体第三方调用顺序或缓存内部实现细节。真实 Edge 网络调用不进入默认测试套件。
- **主要 HTTP seam**：沿用现有 FastAPI `TestClient` 与可注入 fake engine/driver，从最高层验证按语言选择 `microsoft`、现有默认引擎不变、三语言混合配置、动态 `audio/mpeg`/`audio/wav`、响应字节、缓存复用和错误状态。现有应用与多语言 Profile 测试是直接先例。
- HTTP seam 必须证明缓存命中时 Driver 不被调用；未缓存 Edge 失败返回 `502`；失败时不调用其他 Provider；失败或空输出不形成缓存；下一次请求仍可重试。
- HTTP seam 必须证明 Driver、voice、rate、格式或 adapter 版本任一变化都会改变 Cache Identity，而相同完整配置和相同归一化文本仍可跨 Contract 命中。
- HTTP seam 必须证明 Edge rate 变化不会改变合同索引的 Segment 列表、`est_dur_s` 或 `total_est_s`，并保持现有进度条数据契约。
- HTTP seam 必须覆盖后台首段预热失败：合同上传仍成功，缓存未被污染，后续未缓存 GET 返回清晰 `502`。
- **Microsoft Provider 接口 seam**：用 fake Edge Driver 验证 Provider 的三语言默认配置、本地校验、Audio Artifact 收集、非空检查、稳定错误转换和 fingerprint。以相同接口替换为 fake Azure Driver 时，上层调用方式与 HTTP 行为不得改变。
- Edge adapter 的自动化测试通过替代 `edge-tts` 通信对象或其事件源，验证 voice/rate 传递、多个 MP3 音频 chunk 按顺序收集、非音频事件忽略、空流与异常映射；不访问真实 Microsoft 服务。
- Segment Cache 测试验证 MP3 与 WAV 分别使用正确后缀和 media type、manifest 能恢复 Audio Artifact、损坏或不一致条目不命中、TTL 与命中刷新行为保持不变。现有 cache 测试是直接先例。
- 配置测试必须覆盖 `microsoft` canonical 名称、按语言选择、缺失 Driver、未知 Driver、空 voice、合法与非法 rate；不得通过启动联网来证明 voice 可用。
- 现有 GPT-SoVITS、CosyVoice、Template、normalizer、segmenter、cache TTL 与前端播放测试必须继续通过，以证明新 Provider 没有改变原有路径。
- **人工诊断 seam**：独立运行三语言诊断，确认每个语言产生非空 MP3 文件、控制台显示实际 voice/rate、退出状态准确，并由人工试听正式合同风格短句。该诊断属于部署验收，不作为默认 CI 门禁。

## Out of Scope

- 本期不实现 Azure Speech Driver、Azure 凭据、region、私有网络、配额或正式服务协议接入。
- 本期不把 `azure` 暴露为与 `microsoft` 平级的 Engine Provider。
- 本期不新增逐请求的 provider、driver、voice、rate、volume 或 pitch 参数，也不新增相关前端配置界面。
- 本期不自动识别合同语言或根据文本内容切换 Engine Provider、Driver、voice 或 rate。
- 本期不在 Edge 失败时自动回退到 GPT-SoVITS、CosyVoice 或其他语音服务。
- 本期不把 MP3 转码成 WAV，也不要求所有 Engine Provider 统一输出同一种音频编码。
- 本期不根据 Microsoft rate 或实际生成音频修正 `est_dur_s`、`total_est_s` 或进度条模型。
- 本期不调整现有前端播放倍速、音量、保调播放或 Segment seek 交互。
- 本期不在服务启动或健康检查中访问 Edge，不把在线 voice 列表探测作为 readiness 条件。
- 本期不支持 Edge SSML、自定义 prosody、word boundary、字幕、时间戳或流式边生成边播放。
- 本期不迁移或重新编码旧 WAV 缓存，也不要求保留旧缓存键命中。
- 本期不承诺不同 Microsoft voice 的语言学完备性、法律术语读音完全正确或 Edge 与未来 Azure 音色一致；真实听感由诊断和后续验收处理。

## Further Notes

- 本规格落实 ADR-0009“Microsoft TTS 使用稳定 Provider 与可替换 Driver”，并使用领域模型中的 Template、Reading Language、Engine Profile、Driver、Audio Artifact 与 Cache Identity 术语。
- `edge-tts` 是调用 Microsoft Edge 在线 TTS 的第三方 Python 包，不等同于带正式项目凭据、租户、地域和 SLA 的 Azure Speech 接入。启用前必须接受并记录数据外发边界。
- 当前 Edge 输出按上游能力保留为 24 kHz、48 kbps、单声道 MP3；如果未来上游或 Driver 支持其他输出格式，格式必须继续由 Audio Artifact 和 synthesis fingerprint 显式表达。
- 引入 `edge-tts` 时应按项目常规完成依赖锁定与许可证清单更新；依赖升级属于显式发布动作，不应静默改变缓存身份或合成结果。
- 规格已具备实现状态。下一步可使用 `to-tickets` 按依赖顺序拆分为 Audio Artifact/缓存基础、Microsoft Provider 与 Edge Driver、应用接线、诊断与运维文档等实现票据。

## Subsequent Azure Production Extension (2026-08-17)

本规格的原始 “Out of Scope” 只约束首个 Edge 实现阶段。随后经明确需求确认，正式 Azure Speech 已作为同一个 `microsoft` Provider 下的 `azure` Driver 实现；它不是新的并列 Provider，Template、Reading Language、合同 API、Audio Artifact 和错误契约保持不变。

- Azure Driver 使用官方 `azure-cognitiveservices-speech` SDK，通过 `AZURE_SPEECH_KEY` 加 `AZURE_SPEECH_REGION`，或 Key 加 HTTPS `AZURE_SPEECH_ENDPOINT` 连接组织管理的 Speech 资源。
- 三语言继续复用 Microsoft voice/rate 配置；Driver 使用 SSML prosody 应用 rate，并请求 24 kHz、48 kbps、单声道 MP3。预计时长和前端进度条模型仍不调整。
- Azure 的 Driver、voice、rate、Region、Endpoint、输出格式、SDK 与 adapter 版本进入 synthesis fingerprint；Key 不进入 fingerprint、日志、缓存或错误详情。Edge 与 Azure 缓存自动隔离。
- 启动阶段仍只做本地配置校验，不进行联网 readiness 检测。通用三语言诊断命令根据当前 Driver 做真实合成；默认测试用 fake SDK 验证 Azure 边界，不访问云服务。
- 未缓存 Azure Segment 失败时返回脱敏后的 `502`，不自动切换 Edge、GPT-SoVITS 或 CosyVoice；已有匹配缓存照常返回。
- 运维文档分别记录 Edge 与 Azure 的合同文本外发、凭据、Region/Endpoint、配额、服务条款、依赖许可证及从 Edge 切换到 Azure 的验收步骤。
