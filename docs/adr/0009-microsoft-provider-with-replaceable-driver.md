# Microsoft TTS 使用稳定 Provider 与可替换 Driver

服务新增与 GPT-SoVITS、CosyVoice 同级、可按语言配置的 `microsoft` Engine Provider；当前由第三方 `edge-tts` 驱动 Edge 在线 TTS，未来正式生产接入 Azure Speech 时只替换或增加 Provider 内部 Driver，不新增并列的 `azure` Provider，也不改变 Template 与上层合成接口。具体 Driver、音色、基准语速、音频格式和 adapter 版本共同进入合成指纹，因此 Edge 与 Azure 的缓存严格隔离，替换 Driver 不会读到旧实现生成的音频。

当前 Edge Driver 必须显式启用，项目默认引擎仍为 GPT-SoVITS。三个语言 Profile 默认使用 `zh-HK-WanLungNeural`、`zh-CN-YunyangNeural`、`en-HK-SamNeural`，仅开放服务端 `voice` 与 `rate`；前端播放倍速继续独立存在，基准语速不参与预计时长修正。Edge 的原生 MP3 不转码，缓存与响应改为格式感知，现有引擎继续使用 WAV。

Edge 是正式可选 Driver，但不自动降级到其他引擎：缓存命中继续返回，未缓存段调用失败时返回 `502`。服务启动只做本地配置校验，不联网探测，并提供三语言诊断脚本。选择 Edge 即接受归一化后的合同 Segment（可能含 PII）发送到无项目 API key、租户或地域边界的 Edge 在线服务；这一外发边界必须写入运维文档，未来 Azure Driver 再使用正式凭证、地域和服务协议。
