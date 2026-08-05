# DashScope / 百炼地域与 API Endpoint 研究

更新时间：2026-08-04

本文只记录阿里云百炼官方文档中关于地域、API Key 和 CosyVoice SpeechSynthesizer 接入的信息。

## 结论

- `https://dashscope.aliyuncs.com` 是百炼华北 2（北京）地域的公共服务域名；域名中的 `aliyuncs.com` 本身并不表示“北京”，地域归属由百炼文档明确列出。
- 新加坡地域的旧公共服务域名是 `https://dashscope-intl.aliyuncs.com`。百炼文档说明该域名仍可用，但建议迁移到业务空间专属域名：`https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com`。
- CosyVoice/Qwen-Audio-TTS 的 WebSocket endpoint 使用：
  - 北京：`wss://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api-ws/v1/inference`
  - 新加坡：`wss://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/api-ws/v1/inference`
  - `{WorkspaceId}` 必须替换为真实的百炼业务空间 ID，协议必须是 `wss://`。
- API Key 应在目标地域的百炼控制台创建，并与该地域的 API Host 一起使用。官方非实时语音合成示例明确写出“新加坡和北京地域的 API Key 不同”；官方“获取 API Key”文档也把“华北 2（北京）、新加坡等地域”作为不同地域入口，并说明 API Host 会在创建弹窗中显示、随地域和协议变化。因此不要把新加坡 Key/Host 与北京 endpoint 混用。若鉴权失败，CosyVoice WebSocket 握手会返回 HTTP 401/403。

## 适用于当前项目的配置

当前项目的 `backend/engines/bailian_cosyvoice_client.py` 使用 HTTP `SpeechSynthesizer` endpoint（路径为 `/api/v1/services/audio/tts/SpeechSynthesizer`）。若项目使用的是新加坡地域，应将 HTTP base URL 从北京公共域名切换为百炼控制台为新加坡业务空间提供的 API Host；对于实时 WebSocket 接入，则使用上面列出的新加坡 `wss://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/api-ws/v1/inference`。

建议以 API Key 创建弹窗显示的 **API Host** 为准，不要自行拼接地域域名或只替换字符串。API Key 本身不要提交到 Git，应继续通过 `.env`/进程环境变量提供。

## 官方依据

1. [Qwen-Audio-TTS/CosyVoice WebSocket API 参考](https://help.aliyun.com/zh/model-studio/cosyvoice-websocket-api)
   - 列出了北京和新加坡 WebSocket URL。
   - 说明北京公共域名 `dashscope.aliyuncs.com` 和新加坡公共域名 `dashscope-intl.aliyuncs.com`，并建议迁移到业务空间专属域名。
   - 规定 `Authorization: Bearer <your_api_key>`，无效或缺失的 Key 在握手阶段返回 HTTP 401/403。
2. [非实时语音合成](https://help.aliyun.com/zh/model-studio/non-realtime-tts-user-guide)
   - `SpeechSynthesizer` HTTP 示例使用 `/api/v1/services/audio/tts/SpeechSynthesizer`，并明确说明新加坡和北京地域的 API Key 不同。
3. [如何获取 API Key](https://help.aliyun.com/zh/model-studio/get-api-key)
   - 要求在百炼控制台选择地域后进入 API Key 页面创建 Key。
   - 说明创建结果会同时显示 API Key 和 API Host（服务端点），调用时除 Key 外还需指定 API Host，且服务端点会随地域和协议变化。
4. [什么是阿里云百炼](https://help.aliyun.com/zh/model-studio/what-is-model-studio)
   - 官方示例说明不同地域的 `base_url` 不通用，并列出了新加坡业务空间域名格式 `https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1`（OpenAI 兼容协议示例）。
