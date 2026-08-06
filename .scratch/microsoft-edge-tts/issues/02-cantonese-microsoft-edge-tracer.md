# 02 — 打通粤语 Microsoft/Edge TTS tracer bullet

**What to build:** 让部署人员能够为粤语合同显式选择正式的 `microsoft` Engine Provider 和当前 `edge` Driver，并从现有上传、切段、归一化、缓存和 Segment API 流程获得可播放的原生 MP3。该切片应证明未来可替换 Driver 的 Provider 边界、缓存隔离和上游故障语义全部成立。

**Blocked by:** 01 — 建立格式感知的 Audio Artifact 与 Segment Cache.

**Status:** resolved

- [x] 注册 canonical Engine Provider `microsoft`，使现有全局和粤语按语言的引擎选择配置能够选中它。
- [x] Microsoft Provider 通过统一 Driver 接口工作，并要求在选中 Microsoft 时显式配置 canonical Driver `edge`。
- [x] 未选择 Microsoft 的部署不初始化真实 Edge 网络会话，不发生 Edge 数据外发，现有默认引擎行为保持不变。
- [x] 加入并锁定 `edge-tts` 运行时依赖，Driver 使用其异步通信接口处理单个归一化 Segment。
- [x] 粤语默认 voice 为 `zh-HK-WanLungNeural`、默认 rate 为 `+0%`，并允许部署配置覆盖这两个值。
- [x] rate 规范化为带正负号的整数百分比形式；Driver 未配置、Driver 未知、voice 为空或 rate 语法非法时在本地配置阶段明确失败。
- [x] 启动和普通健康检查不查询在线 voice 列表、不发起试合成，也不依赖 Edge 网络可用性。
- [x] Edge Driver 按顺序收集所有音频 chunk，忽略非音频事件，并产出非空、格式为 MP3、media type 为 `audio/mpeg` 的 Audio Artifact。
- [x] 粤语 Segment API 在成功合成或命中缓存时返回原生 MP3 字节和 `audio/mpeg`，不执行 WAV 转码。
- [x] 粤语 Microsoft Engine Profile 的 synthesis fingerprint 至少包含 `edge` Driver、voice、canonical rate、MP3 格式和 adapter 版本。
- [x] 修改 Driver、voice、rate、格式或 adapter 版本会自动改变 Cache Identity，无需提升人工 cache version；相同完整配置仍可跨 Contract 复用相同 Segment。
- [x] 当前 fingerprint 完全匹配的缓存命中时直接返回缓存 Audio Artifact，不调用 Edge 网络服务。
- [x] 连接、超时、上游拒绝、无效 voice、协议错误、空音频和流中断统一映射为 Microsoft 合成错误，未缓存 Segment 返回 `502`。
- [x] Edge 合成失败时不调用 GPT-SoVITS、CosyVoice 或其他 Driver，也不写入空文件、错误格式或半成品缓存。
- [x] 首段后台预热失败不使合同上传失败；失败不会污染缓存，后续真实 GET 会重新尝试并在仍失败时返回 `502`。
- [x] 合同上传和 Segment API 不新增 provider、driver、voice 或 rate 请求字段，粤语的 Segment 列表、`est_dur_s` 和 `total_est_s` 不因 Edge rate 改变。
- [x] Edge adapter 自动化测试使用替代通信对象或事件源验证 voice/rate 传递、chunk 拼接、非音频事件、空流及异常映射，不访问真实 Microsoft 服务。
- [x] FastAPI `TestClient` 与 fake Driver 测试验证粤语端到端选择、MP3 Content-Type、fingerprint 缓存隔离、缓存优先、无回退、预热失败和 `502` 行为。

## Answer

实现了稳定的 `microsoft` Engine Provider 与显式 `edge` Driver，完成粤语默认 voice/rate、本地配置校验、原生 MP3、动态 Content-Type、完整合成指纹、缓存隔离及统一 `502` 失败语义。`edge-tts` 已锁定为 7.2.8；默认测试全部使用 fake Driver 或替代通信对象，不访问真实 Edge 服务。

验证：`uv run --frozen pytest -q`（199 passed），`uv run --frozen python -m compileall -q backend tests`，Standards/Spec 双轴复审均无发现。
