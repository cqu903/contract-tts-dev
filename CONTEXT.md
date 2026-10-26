# Contract TTS — 领域语言（Ubiquitous Language）

对外「多语言合同朗读」服务的核心术语表。只收录本项目特有的领域概念（不含通用编程概念与实现细节）。
术语在 `/grilling` 会话中敲定即落，随设计演进更新。

## Language

**Contract**
外部调用方经接口上传的一份合同 TXT。服务端以 `contract_id` 内容寻址，并临时持久化原文。
同一原文使用不同 Template 时被视为不同 Contract，并拥有不同 `contract_id`；这是有意的语言隔离，而不是同一 Contract 下的多个音频版本。
（服务只处理合同，不处理普通文档——见 ADR-0001。）
_Avoid_: document（普通文档，服务不处理）, file, input, payload, agreement

**Template**（合同模板）
一套端到端、语言隔离的合同朗读处理方案。Template 同时确定 Contract Language、Reading Language、切分规则、发音与文本处理规则，以及 TTS 合成配置；不同 Template 的整套规则和缓存互不影响。
目标 Template ID 为 `xcash_yue`、`xcash_zh`、`xcash_en`。其中粤语和普通话 Template 可以接收相同中文原文，但它们仍产生不同 Contract 与 `contract_id`；英文 Template 接收英文合同。
`template_id` 由调用方上传时声明，服务按它选择完整处理方案。当前实现仍仅接受 `xcash`，尚未实现上述目标 Template。
为兼容现有请求格式，`xcash` 作为 `xcash_yue` 的输入别名保留；服务在生成 `contract_id`、选择规则和计算缓存身份之前，先将其规范化为 `xcash_yue`。`xcash` 不是第四套 Template，相同原文传入 `xcash` 或 `xcash_yue` 应得到相同的新 `contract_id`。
项目尚未投入使用，因此不迁移或兼容此前生成的 `contract_id`、无 Template 元数据的原文记录及旧格式音频缓存；它们可以直接失效。
_Avoid_: format, layout, language flag（Template 不是单纯版式，也不是只改变语言代码或音色的开关）

**Contract Language**（合同语言）
合同原文所使用的书面语言，属于 Template 的固有属性。例如中文合同与英文合同属于不同 Template；它不等同于实际朗读时使用的 Reading Language。

**Reading Language**（朗读语言）
音频实际使用的口语语言，例如粤语、普通话或英语。每个 Template 只对应一种 Reading Language；需要另一种朗读语言时使用另一个 Template。

**Engine Profile**（引擎配置）
一套会共同决定音频结果的完整 TTS 配置，包含稳定的 Engine Provider、具体 Driver、语言、模型、音色、合成参数、音频格式和独立缓存版本。Provider 是 Template 与运维配置依赖的稳定身份；同一 Provider 可以提供多个具有不同服务边界的 Driver，而不改变上层 Template 接口。
每个 Template 绑定一个 Engine Profile。某个 Engine Profile 内任何影响音频结果的配置发生变化时，只提升该 Engine Profile 的缓存版本，不影响其他 Engine Profile 的缓存。
单个服务实例必须同时注册并支持全部 Engine Profile；服务按每次请求所属的 Template 动态选择对应配置，不通过重启进程或修改全局环境变量来切换语言。

**Cache Identity**（缓存身份）
Segment 音频的内容寻址身份，由 Template ID、最终送入 TTS 的文本、Engine Profile 的合成指纹及其缓存版本共同决定。合成指纹覆盖会改变音频结果或格式的具体 Driver、音色、基准语速、音频格式和 adapter 版本；因此同一 `microsoft` Provider 从 Edge Driver 切换到 Azure Speech Driver 时不会误命中旧音频。不同 Template 与不同 Engine Profile 严格隔离；同一 Template 和 Engine Profile 下，最终 TTS 文本完全相同的 Segment 可以跨 Contract 复用缓存。
_Avoid_: text-only cache key（只按文本缓存会在语言、音色或配置变化时错误复用音频）

**Segment**
Contract 经其 Template 的独立切分规则确定性切片后得到的朗读单元。音频以段为单位合成与缓存；seek 以段为粒度吸附到段边界（非任意毫秒定位）。相同原文使用不同 Template 时可以得到完全不同的 Segment 清单。
_Avoid_: chunk, clause, sentence（段 ≠ 句子，是切片算法的产物）

**contract_id**
Contract 的标识，= `sha256(template_id | 原文)`。同时绑定原文与完整语言处理 Template：相同原文使用 `xcash_yue` 和 `xcash_zh` 时得到不同 contract_id，以此隔离各自的分段、处理与朗读请求。
（旧探针里它是静态枚举字典的 key；对外服务重定义为内容寻址哈希。见 ADR-0001、ADR-0005。）
