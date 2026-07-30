# 分段与归一化按合同模板特化（contract_id 含 template_id）

**修正 ADR-0001**：`contract_id` 不是 `sha256(原文)`，而是 `sha256(template_id | 原文)`。

服务是**高度特化、针对特定合同模板**的朗读：`split_contract` 的分段参数与 `normalize_for_tts` 的读法调整，都是为某一模板（当前 Xcash）手工调参的。不同模板需要不同的分段与归一化策略。

**张力**：同一份原文按不同模板会切出**不同分段**（段边界不同 → seek 不同）。若 `contract_id` 只绑原文，则「原文 X 按模板 A」与「原文 X 按模板 B」的段结构会冲突。故 `contract_id` 必须同时绑定原文与模板。

**v1 取舍**：只实现 Xcash 一个 Template profile（当前 segmenter / normalizer 无需改动，仍为单 profile）；但 `contract_id = sha256(template_id | 原文)` 从一开始就纳入 template_id，使将来新增模板时不必迁移已发出的 contract_id、不破坏 seek 语义。

**`template_id` 是上传必传参数**：服务无从得知模板（自动识别已否决），必须由调用方上传时声明。v1 只接受 `xcash`，未知 template_id → 400。注意 `template_id` 是调用方**声明文档类型**（属于「读什么」），不是指定读法——该模板具体怎么分段 / 归一化仍由服务按 template_id 查表决定；音色 / 引擎 / 语言照旧服务固定。

## 考虑并否决的方案

- **v1 就重构为多模板分发、调用方上传指定 template_id**：否决——若近期只接一个模板，这是为不存在的需求付实现成本；且要求调用方懂 template_id，违背「调用方只决定读什么」。
- **服务自动从原文识别模板**：否决（v1）——模板识别是新的特征匹配逻辑 + 误识别风险；v1 只有一个模板时识别无意义。留待多模板且调用方不便指定时再加。
