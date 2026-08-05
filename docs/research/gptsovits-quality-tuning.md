# GPT-SoVITS 合同朗读音质优化研究

更新时间：2026-08-05

范围：只使用 GPT-SoVITS 官方仓库、官方 Wiki 和官方模型配置；代码事实固定到官方仓库提交 `d523079fc05d9a8028d6085bffe4a2757c32abb6`。下面把官方事实和本项目的工程建议分开表述。

## 结论摘要（按预期收益排序）

1. **先重做三种语言各自的参考音频并做盲听筛选。** 每段必须在 3～10 秒内；建议从同一说话人的干净、无混响、无削波、单人自然陈述中各挑 2～3 段，普通话、粤语、英语分别使用同语种参考。3～10 秒是推理代码的硬限制；“干净、同语种、多候选 A/B”是基于模型忠实跟随参考音频的工程建议，不是官方硬校验。[官方 `TTS.py` 的时长校验](https://github.com/RVC-Boss/GPT-SoVITS/blob/d523079fc05d9a8028d6085bffe4a2757c32abb6/GPT_SoVITS/TTS_infer_pack/TTS.py#L808-L826)；[官方 README 的 5 秒 zero-shot 说明](https://github.com/RVC-Boss/GPT-SoVITS/blob/d523079fc05d9a8028d6085bffe4a2757c32abb6/README.md#L28-L37)。
2. **确认远程服务实际加载的版本和成对权重。** 官方当前 `api_v2.py` 的默认配置文件仍把 `custom` 指向 v2，并不等于拉取最新代码就自动使用新模型。优先试听 `v2ProPlus`；若问题主要是金属音或发闷，再重点试听原生 48 kHz、修复 v3 上采样电音问题的 v4。不要混用不同版本的 GPT/SoVITS 权重。[官方默认配置及各版本权重组合](https://github.com/RVC-Boss/GPT-SoVITS/blob/d523079fc05d9a8028d6085bffe4a2757c32abb6/GPT_SoVITS/configs/tts_infer.yaml#L1-L55)；[官方版本对比](https://github.com/RVC-Boss/GPT-SoVITS/wiki/GPT%E2%80%90SoVITS%E2%80%90features-(%E5%90%84%E7%89%88%E6%9C%AC%E7%89%B9%E6%80%A7))。
3. **让参考文本逐字对应参考录音，并正确设置 `prompt_lang`。** 官方 UI 把该字段定义为“参考音频的文本”，代码将其参与参考提示的音素/语义处理；官方没有自动校验文本与录音是否一致，因此错字、漏字和语言标错不会被提前发现。本项目应人工复核三份 `.txt`。[官方推理 UI 的参考文本输入](https://github.com/RVC-Boss/GPT-SoVITS/blob/d523079fc05d9a8028d6085bffe4a2757c32abb6/GPT_SoVITS/inference_webui.py#L1231-L1256)；[官方 API 字段定义](https://github.com/RVC-Boss/GPT-SoVITS/blob/d523079fc05d9a8028d6085bffe4a2757c32abb6/api_v2.py#L154-L177)。
4. **显式控制文本切分，避免合同句子被 `cut5` 切得过碎。** 当前项目客户端没有发送切分参数，因此 API 使用 `cut5`；它会在逗号、分号、句号等多种标点处切开，每个音频片段默认又插入 0.3 秒静音，容易形成“逗号都停很久、语气不连续”的听感。对于本项目已经切成短段的请求，先 A/B `cut0`；较长段落再试约 50 字聚合的 `cut2`。这是结合当前分段架构的建议。[官方 API 默认参数](https://github.com/RVC-Boss/GPT-SoVITS/blob/d523079fc05d9a8028d6085bffe4a2757c32abb6/api_v2.py#L154-L177)；[官方六种切分实现](https://github.com/RVC-Boss/GPT-SoVITS/blob/d523079fc05d9a8028d6085bffe4a2757c32abb6/GPT_SoVITS/TTS_infer_pack/text_segmentation_method.py#L91-L186)；[片段静音的实现](https://github.com/RVC-Boss/GPT-SoVITS/blob/d523079fc05d9a8028d6085bffe4a2757c32abb6/GPT_SoVITS/TTS_infer_pack/TTS.py#L1540-L1561)。
5. **固定种子后再小范围调采样参数。** 先保留官方默认 `top_k=15, top_p=1, temperature=1, repetition_penalty=1.35` 建立基线；合同朗读可试 `temperature=0.7/0.85/1.0` 与 `top_p=0.85/1.0`，其余不动。降低随机性是否更清楚必须用本项目文本盲听确认，官方没有承诺某个非默认组合一定更好。评测时使用固定 `seed`，避免把随机差异误判为参数提升。[官方 API 默认值](https://github.com/RVC-Boss/GPT-SoVITS/blob/d523079fc05d9a8028d6085bffe4a2757c32abb6/api_v2.py#L154-L177)；[官方 WebUI 的默认滑块](https://github.com/RVC-Boss/GPT-SoVITS/blob/d523079fc05d9a8028d6085bffe4a2757c32abb6/GPT_SoVITS/inference_webui.py#L1341-L1350)。
6. **保持非流式 WAV 作为音质基线。** 官方 API 将流式模式分为不同质量/延迟档位，`0/False` 为关闭；当前项目已经使用 `streaming_mode=false` 和 WAV，适合先排除流式拼接和有损编码影响。官方支持 WAV、raw、Ogg、AAC，其中 AAC 路径会调用 FFmpeg 编为 192 kbps。[流式质量档位与媒体参数](https://github.com/RVC-Boss/GPT-SoVITS/blob/d523079fc05d9a8028d6085bffe4a2757c32abb6/api_v2.py#L154-L181)；[官方封装实现](https://github.com/RVC-Boss/GPT-SoVITS/blob/d523079fc05d9a8028d6085bffe4a2757c32abb6/api_v2.py#L232-L283)。
7. **zero-shot 仍不够时，再做约一分钟的少样本微调。** 官方把 5 秒参考定义为 zero-shot，把约一分钟训练数据的微调定义为可提高相似度和真实感的 few-shot 路径。它的投入高于更换参考音频和模型，所以放在后面。[官方功能说明](https://github.com/RVC-Boss/GPT-SoVITS/blob/d523079fc05d9a8028d6085bffe4a2757c32abb6/README.md#L28-L37)。

## 当前项目与官方默认值

`backend/engines/gptsovits_client.py` 当前只发送 `text`、目标语言、参考音频路径、参考文本、参考语言、`media_type=wav` 和 `streaming_mode=false`。其余参数全部由远程 `api_v2.py` 默认：

| 参数 | 官方 API 默认值 | 对音质排查的意义 |
|---|---:|---|
| `top_k` | `15` | GPT 采样候选范围；先保持默认 |
| `top_p` | `1` | 核采样范围；作为小范围 A/B 项 |
| `temperature` | `1` | 采样随机性；作为首要参数 A/B 项 |
| `text_split_method` | `cut5` | 按多种标点切分；可能让合同朗读过碎 |
| `batch_size` | `1` | 主要是吞吐/显存项，不应先当作音质旋钮 |
| `batch_threshold` | `0.75` | 分桶阈值，主要影响批处理 |
| `split_bucket` | `true` | 主要影响批处理；流式和变速时会被关闭 |
| `speed_factor` | `1.0` | 控制语速；非 1 时官方代码自动关闭分桶 |
| `fragment_interval` | `0.3` 秒 | 每个合成片段之间插入的静音 |
| `seed` | `-1` | 随机种子；A/B 时应固定 |
| `parallel_infer` | `true` | 主要是推理策略/性能 |
| `repetition_penalty` | `1.35` | 抑制语义 token 重复；先保持默认 |
| `sample_steps` | `32` | v3/v4 声码路径的采样步数；官方 Wiki 称 32 为最佳音质设置 |
| `super_sampling` | `false` | API 注释定义为 v3 超采样；v4 已原生 48 kHz |

默认值来源：[官方 `api_v2.py`](https://github.com/RVC-Boss/GPT-SoVITS/blob/d523079fc05d9a8028d6085bffe4a2757c32abb6/api_v2.py#L154-L177)。`speed_factor`、流式模式与分桶的互斥逻辑见[官方 `TTS.py`](https://github.com/RVC-Boss/GPT-SoVITS/blob/d523079fc05d9a8028d6085bffe4a2757c32abb6/GPT_SoVITS/TTS_infer_pack/TTS.py#L1089-L1105)。v3/v4 采样步数说明见[官方 v3/v4 Wiki](https://github.com/RVC-Boss/GPT-SoVITS/wiki/GPT%E2%80%90SoVITS%E2%80%90v3v4%E2%80%90features-(%E6%96%B0%E7%89%B9%E6%80%A7))。

## 版本和权重选择

- **v2**：从 v1 增加了普通话/英语文本前端优化、粤语支持、语速控制和更好的混合语种切分；官方还特别说明它改善了低音质参考音频的合成结果。[官方 v2 说明](https://github.com/RVC-Boss/GPT-SoVITS/wiki/GPT%E2%80%90SoVITS%E2%80%90v2%E2%80%90features-(%E6%96%B0%E7%89%B9%E6%80%A7))。
- **v3**：zero-shot 音色相似度、重复/漏字稳定性和情感表达优于 v2，但原生输出为 24 kHz，特定低步数、小样本微调场景可能出现电音。[官方 v3/v4 说明](https://github.com/RVC-Boss/GPT-SoVITS/wiki/GPT%E2%80%90SoVITS%E2%80%90v3v4%E2%80%90features-(%E6%96%B0%E7%89%B9%E6%80%A7))。
- **v4**：修复 v3 非整数倍上采样导致的金属音问题并原生输出 48 kHz，适合优先排查“电音、闷、波形质感差”。官方作者把它定位为 v3 的直接替代，但也注明仍需实际测试。[官方 README v4 发布说明](https://github.com/RVC-Boss/GPT-SoVITS/blob/d523079fc05d9a8028d6085bffe4a2757c32abb6/README.md#L339-L352)。
- **v2Pro/v2ProPlus**：官方版本表称其以接近 v2 的硬件成本和速度取得超过 v4 的综合表现与高 zero-shot 相似度；对普通合同朗读，`v2ProPlus` 应进入首轮候选。[官方版本对比](https://github.com/RVC-Boss/GPT-SoVITS/wiki/GPT%E2%80%90SoVITS%E2%80%90features-(%E5%90%84%E7%89%88%E6%9C%AC%E7%89%B9%E6%80%A7))。

建议至少做同一组文本的 `当前 v2`、`v2ProPlus`、`v4` 三方盲听。官方也提醒，WER/SIM 不能衡量自然度和音质，最终应以自己的测试集和人工听感为准。[官方版本 Wiki 的评测边界说明](https://github.com/RVC-Boss/GPT-SoVITS/wiki/GPT%E2%80%90SoVITS%E2%80%90features-(%E5%90%84%E7%89%88%E6%9C%AC%E7%89%B9%E6%80%A7))。

## 参考音频与参考文本

官方推理代码会把参考音频重采样到 16 kHz 提取语义，并强制检查 3～10 秒；用于声谱条件的参考音频则会按模型采样率重采样，双声道会折为单声道。因此，单纯把 WAV 保存成更高采样率不会凭空增加模型可用信息。[官方参考音频处理](https://github.com/RVC-Boss/GPT-SoVITS/blob/d523079fc05d9a8028d6085bffe4a2757c32abb6/GPT_SoVITS/TTS_infer_pack/TTS.py#L764-L826)。

本项目的实用筛选标准（工程建议）是：

- 选择约 5～8 秒完整陈述句，不从音素或单词中间截断；
- 无背景音乐、无第二人、无明显房间混响、无强降噪水声、无削波；
- 音量稳定但保留余量，不通过有损格式反复转码；
- 语速、情绪和停顿接近“正式合同朗读”；
- 每种语言录 2～3 个候选，固定模型、参数、种子，仅替换参考音频做盲听；
- `.txt` 逐字转写实际录音，包含真实出现的数字、字母和停顿标点，不把目标合同文字误当成参考文本。

v3/v4 官方说明其合成语气和音色比 v2 更忠实于参考音频，这也是为什么参考录音的噪声、语气和口音在新版本中更加关键。[官方版本特性 Wiki](https://github.com/RVC-Boss/GPT-SoVITS/wiki/GPT%E2%80%90SoVITS%E2%80%90features-(%E5%90%84%E7%89%88%E6%9C%AC%E7%89%B9%E6%80%A7))。

## 普通话、粤语、英语分别建议

- **普通话**：使用普通话参考音频、普通话逐字文本、`prompt_lang=zh`、`text_lang=zh`。官方 v2 中文前端依赖额外的 G2PW 模型，应确认远程安装完整；本项目继续在引擎边界做繁转简有利于减少前端不一致。[官方 README 的中文模型要求](https://github.com/RVC-Boss/GPT-SoVITS/blob/d523079fc05d9a8028d6085bffe4a2757c32abb6/README.md#L177-L186)。
- **粤语**：必须使用 v2 或更新版本，因为官方从 v2 开始加入粤语；优先粤语母语参考、`prompt_lang=yue`、`text_lang=yue`。不要用普通话音频配粤语参考文本。[官方 v2 发布说明](https://github.com/RVC-Boss/GPT-SoVITS/blob/d523079fc05d9a8028d6085bffe4a2757c32abb6/README.md#L295-L317)。
- **英语**：使用英语参考音频、英语逐字文本、`prompt_lang=en`、`text_lang=en`。合同中的日期、金额、缩写和地址应继续在本项目归一化层先展开，避免把文本前端和音色模型问题混在一起。英文长句若需要引擎内切分，可 A/B `cut4`（按英文句号且保护小数点）和 `cut2`；当前短段请求优先 `cut0`。[官方切分实现](https://github.com/RVC-Boss/GPT-SoVITS/blob/d523079fc05d9a8028d6085bffe4a2757c32abb6/GPT_SoVITS/TTS_infer_pack/text_segmentation_method.py#L117-L186)。

官方确认五种语言可以跨语言合成；但这只代表能力边界，不代表跨语言参考一定比同语言参考音质更好。微调数据较大且单一语言时，底模的跨语言能力还可能被覆盖。因此，本项目已有三套参考文件时，应默认使用同语言参考，把粤语参考回退给普通话/英语只作为容错路径。[官方跨语言能力说明](https://github.com/RVC-Boss/GPT-SoVITS/wiki/%E4%B8%8D%E5%90%8C%E8%AE%AD%E7%BB%83%E9%9B%86%E7%9A%84%E8%B7%A8%E8%AF%AD%E7%A7%8D%E8%83%BD%E5%8A%9B(Cross%E2%80%90Language-Ability-of-Different-Training-Sets))。

## 建议的最小 A/B 方案

使用 9～12 条固定合同测试句，覆盖普通话、粤语、英语，以及日期、金额、地址、字母数字混合。评价维度分开记录：错读/漏字/重复、语气连续性、音色相似度、底噪/电音/闷、片段衔接。

1. 固定当前 v2、API 默认采样参数、`seed=固定值`，每种语言只轮换 2～3 个原生参考音频；选出最佳参考。
2. 固定最佳参考，对比 v2、v2ProPlus、v4。
3. 固定最佳模型与参考，对比 `cut5` 和 `cut0`；若单段过长，再加入 `cut2`。同时试听 `fragment_interval=0.15/0.3`，它主要改变停顿而非声码器音质。
4. 最后只调一项采样参数：先比较 `temperature=0.7/0.85/1.0`；仍有随机漏读或重复时，再比较 `top_p=0.85/1.0`，保持 `top_k=15` 和 `repetition_penalty=1.35`。
5. v3/v4 保持 `sample_steps=32` 做最高质量基线；只有性能不足时再比较 8 步。官方把 32 步描述为最佳音质、4/8 步描述为速度档。[官方 v3/v4 Wiki](https://github.com/RVC-Boss/GPT-SoVITS/wiki/GPT%E2%80%90SoVITS%E2%80%90v3v4%E2%80%90features-(%E6%96%B0%E7%89%B9%E6%80%A7))。

只有完成上述对照后，才值得决定是否给 `GPTSoVITSClient` 增加这些参数的环境变量配置；否则一次开放所有旋钮会让问题难以归因。

## 第一方来源清单

- [GPT-SoVITS 官方 README（固定提交）](https://github.com/RVC-Boss/GPT-SoVITS/blob/d523079fc05d9a8028d6085bffe4a2757c32abb6/README.md)
- [官方 `api_v2.py`（固定提交）](https://github.com/RVC-Boss/GPT-SoVITS/blob/d523079fc05d9a8028d6085bffe4a2757c32abb6/api_v2.py)
- [官方推理管线 `TTS.py`（固定提交）](https://github.com/RVC-Boss/GPT-SoVITS/blob/d523079fc05d9a8028d6085bffe4a2757c32abb6/GPT_SoVITS/TTS_infer_pack/TTS.py)
- [官方文本切分实现（固定提交）](https://github.com/RVC-Boss/GPT-SoVITS/blob/d523079fc05d9a8028d6085bffe4a2757c32abb6/GPT_SoVITS/TTS_infer_pack/text_segmentation_method.py)
- [官方推理配置及权重组合（固定提交）](https://github.com/RVC-Boss/GPT-SoVITS/blob/d523079fc05d9a8028d6085bffe4a2757c32abb6/GPT_SoVITS/configs/tts_infer.yaml)
- [官方各版本特性 Wiki](https://github.com/RVC-Boss/GPT-SoVITS/wiki/GPT%E2%80%90SoVITS%E2%80%90features-(%E5%90%84%E7%89%88%E6%9C%AC%E7%89%B9%E6%80%A7))
- [官方 v3/v4 特性 Wiki](https://github.com/RVC-Boss/GPT-SoVITS/wiki/GPT%E2%80%90SoVITS%E2%80%90v3v4%E2%80%90features-(%E6%96%B0%E7%89%B9%E6%80%A7))
- [官方跨语言能力 Wiki](https://github.com/RVC-Boss/GPT-SoVITS/wiki/%E4%B8%8D%E5%90%8C%E8%AE%AD%E7%BB%83%E9%9B%86%E7%9A%84%E8%B7%A8%E8%AF%AD%E7%A7%8D%E8%83%BD%E5%8A%9B(Cross%E2%80%90Language-Ability-of-Different-Training-Sets))
