# 04 — 交付三语言诊断与生产运维说明

**What to build:** 让运维人员能够在不影响服务启动和默认 CI 的前提下，主动验证当前 Microsoft/Edge 三语言配置、网络连通性、MP3 输出和实际听感；同时获得足以做启用、故障处理、数据合规评估以及未来 Azure 迁移的完整运维说明。

**Blocked by:** 03 — 扩展 Microsoft Engine Profile 到普通话和英语.

**Status:** ready-for-agent

- [ ] 提供独立的三语言诊断入口，不被服务启动、健康检查或默认自动化测试隐式执行。
- [ ] 诊断复用服务实际使用的 Microsoft Driver、三语言 voice 和 rate 配置，不维护第二套不一致的默认值。
- [ ] 诊断分别使用固定、简短且不含敏感信息的粤语、普通话和英语合同风格测试句调用真实 Edge 在线服务。
- [ ] 诊断在联网前明确提示测试文本将发送到外部 Edge 在线服务，不读取真实 Contract、缓存或用户数据。
- [ ] 每种语言的诊断输出显示实际 Driver、voice 和 rate，验证结果为非空 MP3，并保存为可独立试听且文件名可辨识的音频。
- [ ] 单一语言失败不阻止其余语言执行；结束时逐语言汇总成功与错误，并在任一语言失败时返回非零退出状态。
- [ ] 诊断的自动化测试使用 fake Driver 验证三语言调用、输出文件、部分失败汇总和退出状态，不访问真实 Microsoft 服务。
- [ ] 文档说明如何全局或按 Reading Language 显式选择 `microsoft`，以及如何显式选择当前 `edge` Driver。
- [ ] 示例配置列出三语言默认 voice/rate、覆盖方式和修改部署配置后需要重启服务才能生效的规则。
- [ ] 文档明确 Edge 输出为 MP3/`audio/mpeg`、现有引擎输出为 WAV/`audio/wav`，客户端和缓存会按实际格式处理且不执行转码。
- [ ] 文档说明 synthesis fingerprint 如何自动隔离 Driver、voice、rate、格式与 adapter 版本，并说明人工 cache version 仍可用于额外失效。
- [ ] 文档明确无启动联网检测、缓存命中时不访问 Edge、未缓存 Edge 失败返回 `502`，以及系统不会自动回退到其他 Provider。
- [ ] 运维故障排查步骤覆盖本地配置错误、网络/超时、无效 voice、上游拒绝、空输出、诊断文件试听和缓存命中差异。
- [ ] 安全与运维文档明确记录：归一化后的合同 Segment 可能包含姓名、地址、金额、账号等 PII，并会在选择 Edge Driver 时发送到外部 Edge 在线服务。
- [ ] 文档不得把 Edge Driver 描述成具备项目专属 API key、租户、地域或 Azure 企业 SLA 的正式 Azure Speech 接入。
- [ ] 未来生产迁移说明把 Azure Speech 实现为同一 `microsoft` Provider 下的 `azure` Driver，并指出凭据、region、endpoint、服务协议及新增 fingerprint 字段属于后续范围。
- [ ] 依赖和运维说明记录 `edge-tts` 的版本锁定与许可证清单要求，升级影响输出的版本时要求更新 fingerprint 并重新运行三语言诊断。
- [ ] 在具备网络的部署验收环境中，可以按文档运行诊断并试听三份音频；该人工诊断不成为默认 CI 门禁。
