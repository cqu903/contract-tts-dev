# Docker 部署（Azure Speech）

这套部署面向单实例 Azure Speech 生产运行：FastAPI、静态前端和 Microsoft Azure Driver 在一个容器内运行，宿主机默认使用 `8001`，容器内部固定使用 `8000`。Azure Speech 通过出站 HTTPS 调用，不需要在宿主机或容器开放额外入站端口。

## 1. 前置条件

- Docker Engine 或 Docker Desktop，包含 Docker Compose v2（使用 `docker compose` 命令）。
- 部署主机允许访问 Azure Speech 的出站 HTTPS（TCP 443）。
- Azure Speech Key 与 Region 来自同一个组织管理的 Speech 资源。
- 生产环境必须保持**一个容器副本、一个 Uvicorn worker**。当前锁、清理任务和本地存储都以单进程为边界；不要执行 `docker compose up --scale contract-tts=2`。

Dockerfile 使用 Debian 12/Python 3.12，并安装 Azure Speech SDK 所需的 CA certificates、OpenSSL 与 ALSA 运行库。Python 依赖由仓库的 `uv.lock` 锁定，构建时使用固定版本的 `uv` 执行 `uv sync --locked`。

## 2. 准备 `.env`

首次部署可复制 Azure 模板：

```powershell
Copy-Item deploy/azure.env.example .env
```

Linux/macOS：

```bash
cp deploy/azure.env.example .env
```

至少填写：

```dotenv
AZURE_SPEECH_KEY=实际资源Key
AZURE_SPEECH_REGION=southeastasia
AZURE_SPEECH_ENDPOINT=
```

正常区域模式保持 Endpoint 为空。只有 Azure 门户明确提供自定义或私有 HTTPS 资源 Endpoint 时才填写；不要把 `/cognitiveservices/v1` REST 路径填入该变量。

`.env` 被 Git 与 Docker build context 忽略，只由 Compose 在容器创建时注入。不要把真实 Key 写进 `Dockerfile`、`compose.yaml`、镜像构建参数、提交记录或工单。修改 `.env` 后，单纯 `restart` 不会重新创建容器，必须使用后文的 `--force-recreate`。

## 3. 构建与首次验收

在项目根目录执行：

```powershell
docker compose config --quiet
docker compose build --pull
docker compose run --rm contract-tts python scripts/diagnose_microsoft_tts.py
```

`config --quiet` 只验证 Compose 配置，不把展开后的 Key 打到控制台。三语言诊断会把仓库内固定、无敏感信息的短句发送到 Azure，并将 MP3 保存到诊断 volume；三项全部显示 `SUCCESS` 后再启动服务。

```powershell
docker compose up -d
docker compose ps
docker compose logs --tail=100 contract-tts
```

默认访问地址：

- 同机：`http://127.0.0.1:8001/`
- 局域网：`http://<部署主机IPv4>:8001/`

如需更换宿主机端口，在 `.env` 设置 `CONTRACT_TTS_PORT`，然后重新创建容器。容器内部端口始终是 `8000`。

## 4. 运行结构与持久化

Compose 创建三个 named volume：

| Volume | 容器路径 | 内容 | 敏感性 |
|---|---|---|---|
| `contract_tts_cache` | `/app/cache` | WAV/MP3 Audio Artifact 与 manifest | 可能还原合同朗读内容 |
| `contract_tts_uploaded` | `/app/uploaded` | 上传合同原文与 manifest | 包含真实合同及 PII，高敏感 |
| `contract_tts_diagnostics` | `/app/.scratch/microsoft-edge-tts/diagnostics` | 运维诊断 MP3 | 固定无敏感测试文本 |

容器使用非 root 用户、只读根文件系统、`no-new-privileges` 和空 Linux capabilities；只有上述 volumes 与 `/tmp` 可写。日志采用本地轮转，单文件最多 10 MB、保留 3 份。

`docker compose down` 会删除容器与网络，但保留 named volumes。**不要在没有确认和备份时运行 `docker compose down -v`**；`-v` 会永久删除上传原文、缓存与诊断文件。

## 5. 常用运维命令

停止和恢复：

```powershell
docker compose stop
docker compose start
```

查看健康状态与日志：

```powershell
docker compose ps
docker compose logs -f --tail=100 contract-tts
```

重新运行真实 Azure 三语言诊断：

```powershell
docker compose exec contract-tts python scripts/diagnose_microsoft_tts.py
```

把诊断 MP3 复制到宿主机：

```powershell
New-Item -ItemType Directory -Force diagnostics
docker compose cp contract-tts:/app/.scratch/microsoft-edge-tts/diagnostics/. ./diagnostics/
```

修改 Key、Region、voice、rate 或缓存版本后：

```powershell
docker compose up -d --force-recreate
docker compose exec contract-tts python scripts/diagnose_microsoft_tts.py
```

更新代码或依赖后：

```powershell
docker compose build --pull
docker compose up -d
docker compose ps
```

## 6. 备份

`uploaded` 是业务原文，`cache` 可降低 Azure 重复调用，应按组织的数据保留与加密策略备份。容器运行时可创建一个临时归档，再复制到宿主机：

```powershell
docker compose exec contract-tts tar -C /app -czf /tmp/contract-tts-data.tgz cache uploaded
docker compose cp contract-tts:/tmp/contract-tts-data.tgz ./contract-tts-data.tgz
```

备份文件含真实合同与可能的 PII，必须加密、控制访问并按保留策略清理。恢复会覆盖当前 manifest 和数据文件，应先停止服务并单独制定恢复窗口，不要在运行中直接覆盖 volume。

## 7. 生产网络边界

Compose 只提供应用容器，不自动提供 TLS、登录、租户隔离或调用方鉴权。当前 API 仍遵循 ADR-0002 的 v1 边界；不要把端口直接暴露到公网。正式对外部署应在容器前增加组织管理的 HTTPS reverse proxy/API gateway、访问控制、请求大小限制和审计，并由防火墙只开放必要来源。

Azure Key 进入容器环境，但不会复制进镜像、合成 fingerprint、缓存或应用错误详情。归一化后的未缓存合同 Segment 会发送到 `AZURE_SPEECH_REGION` 对应的 Azure Speech 资源；缓存命中不访问 Azure，Azure 失败不自动切换其他 Driver。

## 8. 本项目的验证限制

提交 Docker 文件时，本机没有安装 Docker CLI，因此无法在当前开发机执行 `docker compose config` 或真实镜像构建。文件已通过 YAML 解析、静态安全断言、完整 Python 测试和前端测试；首次部署主机仍必须执行第 3 节的 Compose 校验、镜像构建和容器内三语言诊断。
