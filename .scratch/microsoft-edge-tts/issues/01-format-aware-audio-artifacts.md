# 01 — 建立格式感知的 Audio Artifact 与 Segment Cache

**What to build:** 让合同朗读服务能够端到端携带音频格式信息，而不是把所有合成结果假设为 WAV。现有 GPT-SoVITS 与 CosyVoice 用户应继续获得相同的 WAV 播放体验；同时，应用、缓存和浏览器响应已经能够安全承载后续 Microsoft/Edge 的 MP3，为新增 Driver 建立稳定且可测试的接口。

**Blocked by:** None — can start immediately.

**Status:** resolved

- [x] 定义稳定的 Audio Artifact 契约，至少表达完整音频字节、canonical 音频格式、HTTP media type 和缓存文件后缀；上层不再根据 Provider 名称猜测格式。
- [x] GPT-SoVITS 与 CosyVoice 通过新契约明确产出 WAV，现有正常合成、预热和 Segment 获取行为保持不变。
- [x] Segment API 根据新生成或缓存恢复的 Audio Artifact 返回 Content-Type，现有引擎仍返回 `audio/wav`。
- [x] Segment Cache 能按实际格式选择文件后缀，并持久化恢复 Audio Artifact 所需的格式和 media type 元数据。
- [x] 缓存读取发现文件、manifest、后缀或格式不一致时不会返回错误编码的数据，而是把条目视为未命中或损坏。
- [x] 缓存只提交完整、非空且格式已知的 Audio Artifact；失败、取消或中断不会留下可命中的半成品。
- [x] 相同缓存键的并发请求继续只执行一次合成，其余请求复用完整结果。
- [x] Cache Identity 接受确定性的 synthesis fingerprint 维度，为后续 Driver、voice、rate、格式和 adapter 版本隔离提供稳定入口。
- [x] 现有人工 cache version 继续有效，并能与 synthesis fingerprint 共同组成缓存身份。
- [x] 新缓存身份不回退查询或迁移旧命名空间；旧 WAV 条目按现有滑动 TTL 自然淘汰，且绝不会被解释成 MP3。
- [x] 缓存命中仍刷新滑动访问时间，过期清理能够删除不同音频后缀的条目及相应 manifest 记录。
- [x] 浏览器播放流程能够使用响应提供的 Blob 类型播放 WAV 或 MP3，不新增格式硬编码或改变现有播放倍速行为。
- [x] 自动化测试从应用 HTTP seam 验证 WAV 响应和缓存复用，并从 Segment Cache seam 验证格式元数据、不同后缀、损坏条目、原子写入、并发去重和 TTL。
- [x] 所有现有 GPT-SoVITS、CosyVoice、Template、缓存和前端播放测试继续通过。

## Answer

已交付格式感知的 Audio Artifact、WAV/MP3 canonical metadata、动态 Segment Content-Type、格式感知且原子提交的 Segment Cache，以及 Engine Profile synthesis fingerprint 入口。GPT-SoVITS 与 CosyVoice 明确保持 WAV；浏览器继续直接使用响应 Blob，播放倍速不变。

验证结果：Python 全量测试 172 项通过，Node 播放测试 3 项通过，Python 编译检查通过。具体 Microsoft Driver、voice、rate、格式和 adapter 版本的 fingerprint 组装由后续 Microsoft/Edge tracer ticket 接入本票据提供的稳定字段。
