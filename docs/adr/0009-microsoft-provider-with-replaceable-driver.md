# Microsoft TTS 使用稳定 Provider 与可替换 Driver

服务使用与 GPT-SoVITS、CosyVoice 同级、可按语言配置的 `microsoft` Engine Provider，并在 Provider 内同时提供第三方 `edge-tts` 驱动的 Edge Driver 与官方 Azure Speech SDK Driver；正式生产通过部署配置选择 `azure`，不新增并列 Provider，也不改变 Template 与上层合成接口。具体 Driver、服务 Region/Endpoint、音色、基准语速、音频格式、SDK 和 adapter 版本共同进入合成指纹，因此 Edge 与 Azure 的缓存严格隔离，凭据本身不进入日志或缓存。

Microsoft Driver 必须显式选择为 `edge` 或 `azure`，项目默认引擎仍为 GPT-SoVITS。三个语言 Profile 默认使用 `zh-HK-WanLungNeural`、`zh-CN-YunyangNeural`、`en-HK-SamNeural`，仅开放服务端 `voice` 与 `rate`；前端播放倍速继续独立存在，基准语速不参与预计时长修正。两个 Microsoft Driver 都输出 MP3 且不转码，现有引擎继续使用 WAV。

Microsoft Driver 不自动降级到其他引擎：缓存命中继续返回，未缓存段调用失败时返回 `502`。服务启动只做本地配置校验，不联网探测，并提供通用三语言诊断脚本。选择 Edge 即接受归一化后的合同 Segment（可能含 PII）发送到无项目 API key、租户或地域边界的 Edge 在线服务；选择 Azure 则使用正式资源 Key 和 Region 或 HTTPS Endpoint，把 Segment 发送到对应 Azure Speech 资源，并遵循该资源的服务条款与数据边界。
