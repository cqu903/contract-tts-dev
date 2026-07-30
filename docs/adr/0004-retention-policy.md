# 留存策略：原文 3 月 creation TTL，音频 30 天滑动窗口（命中续期）

对外服务的两类持久数据分别按不同策略淘汰：

- **原文（contract_id → 原文 / 段文本，存于 `ContractStore`）**：创建后 **3 个月** TTL，按 *creation time* 清理。保留较久以方便核查。
- **音频缓存（`sha256(归一化文本 + 音色 + 引擎)` → wav，存于 `SegmentCache`）**：**30 天滑动窗口**——淘汰依据是「最近 30 天无命中」（*last-access time*），而非生成时间。每次缓存命中刷新访问时间，热点音频（反复被 seek 的常见合同段）因此常驻，冷音频 30 天无人听才删。

**理由**：音频是算力 / 字符费的大头，按命中续期能让高频复用的样板段长期命中、把成本压到最低；原文是 PII 载体，按固定 TTL 限时留存便于核查又不过度堆积。

**落地**：`cache.py` 的 `manifest.json` 扩展为 `{created_at, last_access_at, duration}`，`get` 命中时刷新 `last_access_at`；`ContractStore` 记原文 `created_at`；服务启动时各跑一次 `evict_expired`（音频 30d / 原文 90d）。
