# Cantonese Contract TTS — 领域语言（Ubiquitous Language）

对外「粤语合同朗读」服务的核心术语表。只收录本项目特有的领域概念（不含通用编程概念与实现细节）。
术语在 `/grilling` 会话中敲定即落，随设计演进更新。

## Language

**Contract**
外部调用方经接口上传的一份合同 TXT。服务端以 `contract_id` 内容寻址，并临时持久化原文。
（服务只处理合同，不处理普通文档——见 ADR-0001。）
_Avoid_: document（普通文档，服务不处理）, file, input, payload, agreement

**Template**（合同模板）
一类结构相同的合同（当前仅 Xcash 模板）。分段（`split_contract`）与归一化（`normalize_for_tts`）策略**按 Template 特化**——不同模板有不同的段边界规则与读法调整，针对该模板的合同手工调参。新增合同版本 / 模板 = 新增一个 profile。
`template_id` 由调用方上传时声明（他们知道自己上传的是哪种合同）；具体 profile 实现由服务按 template_id 查表决定（v1 必传，仅接受 `xcash`，见 ADR-0005）。
_Avoid_: format, layout, version（模板 ≠ 版本号，是「结构与朗读策略的特化单元」）

**Segment**
Contract 经确定性切片（按其 Template 的 `split_contract` profile）得到的朗读单元。音频以段为单位合成与缓存；seek 以段为粒度吸附到段边界（非任意毫秒定位）。
_Avoid_: chunk, clause, sentence（段 ≠ 句子，是切片算法的产物）

**contract_id**
Contract 的标识，= `sha256(template_id | 原文)`。同时绑定原文与模板：同一原文按不同模板分段会得到不同 contract_id（段结构不同、seek 不同）。不绑定音色（音色服务固定）。
（旧探针里它是静态枚举字典的 key；对外服务重定义为内容寻址哈希。见 ADR-0001、ADR-0005。）
