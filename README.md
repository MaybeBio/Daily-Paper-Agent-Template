# idp-interaction-ai — 无序蛋白互作 × AI

无序蛋白/无序区（IDP/IDR）介导的蛋白质互作，含相分离与凝聚体；方法限定为深度学习、分子动力学与对接。

每周从 PubMed / arXiv / bioRxiv / medRxiv / chemRxiv 抓取最新文献元数据，提交并推送回本仓库，同时创建一条 Issue 汇总。本地用 Zotero 按 `_ids.txt` 批量导入筛选。

## 作为模板使用（换课题）

本仓库把「课题相关」的内容收敛到 **两个文件**，其余代码、模板、工作流全部通用。换一个新研究领域，只改这两个文件 + 清理历史产出即可：

| 文件 | 内容 | 换课题要改什么 |
| --- | --- | --- |
| `config.yaml` | `topic`、`title`、`site_base_url`、`window_days`、`llm`、`platforms.*.query` | 改 `topic`（slug）、`title`（站点显示名）、`site_base_url`（新仓库的 Pages 地址，形如 `https://<user>.github.io/<repo>`），并按新领域重写每平台的布尔检索式 |
| `prompts.yaml` | `score` / `translate` / `paper_card` / `review` 四个 system prompt | 把课题方向、对象/互作/方法轴、16 节 Paper Card 的「课题相关」措辞替换成新领域 |

换课题步骤：

1. 用 GitHub「Use this template」新建仓库（会自动带上全部代码与这两个文件）。
2. 改 `config.yaml`：`topic`、`title`、`site_base_url`，并按新领域重写 `platforms.*.query`（检索语法调优见母仓 `docs/topics-catalog.md`）。
3. 改 `prompts.yaml`：把四个 prompt 里的课题措辞替换成新领域。
4. 删除历史产出目录 `Archive/`、`Discovery/`、`site/`（首次运行会自动重建；`.git` 按需自行清理）。
5. 配置 Secrets：`ENTREZ_EMAIL`、`NCBI_API_KEY`、`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`（见下文「密钥」与「LLM Agent」）。
6. 手动 `workflow_dispatch` 跑一次验证，或等周一自动跑。

**不要动**：`scripts/`、`templates/`、`.github/workflows/`、`tests/` 全部与课题无关——站点标题/品牌从 `config.yaml` 的 `title` 读，URL 路径前缀从 `site_base_url` 的路径段推导（`build_site.py` 的 `site_base_path()`），无需在模板里改任何硬编码字符串。

## 仓库结构

- `scripts/monitor.py` — 读取 `config.yaml`，逐平台检索，规范化后写入 `Discovery/`（合并 CSV + `_ids.txt`）与 `Archive/`（逐篇元数据 JSON），并生成 Issue 正文与标题；末尾调用 `run_agent_pipeline_all` 并发跑 LLM 流水线。
- `scripts/agent.py` — LLM 层：OpenAI 兼容客户端 + 评分/翻译/Paper Card/Reviewer 四个生成函数；system prompt 从 `prompts.yaml` 读取。
- `scripts/fulltext.py` — 全文获取封装：优先原生全文 HTML / PMC XML，失败回退摘要。
- `scripts/build_site.py` + `templates/` — 静态站点生成，产出 `papers/{source}/{id}/index.html` 解析页。站点标题/品牌从 `config.yaml` 的 `title` 读，路径前缀从 `site_base_url` 的路径段推导。
- `config.yaml` — 检索与站点配置：`topic`（slug）、`title`（站点显示名）、`site_base_url`、时间窗口、每平台一条布尔检索式，以及 `llm` 块（开关与并发）。PubMed 邮箱、API key 与 LLM 密钥均通过环境变量注入，不写入文件。
- `prompts.yaml` — 四个 system prompt（score / translate / paper_card / review）的正文，集中于此文件，换课题只改这里。
- `.github/workflows/monitor.yml` — 每周一 09:23 UTC 自动运行，支持 `workflow_dispatch` 手动触发。

## 产出

```
Archive/                                # 逐篇完整元数据 JSON，只增不删，按年月归档（PubMed 按 entrez date，见「日期口径」）
  {source}/{year}/{month}/{id}/{id}.json
Discovery/                              # 每次运行一份合并 CSV 与 _ids.txt，按抓取日归档
  {year}/{month}/idp-interaction-ai_{date}.csv
  {year}/{month}/idp-interaction-ai_{date}_ids.txt
```

`source` 取值为 `pubmed`、`arxiv`、`biorxiv`、`medrxiv`、`chemrxiv`。

CSV 共 9 列：`source, id, doi, title, authors, journal, published_date, url, abstract`。`id` 为各平台主键（PubMed 为 PMID，预印本为 DOI），`doi` 为跨平台规范标识，`published_date` 统一为 ISO 日期 `YYYY-MM-DD`（PubMed 用 entrez date，预印本用 posting 日期，见「日期口径」）。

`_ids.txt` 每行一个标识符，带类型前缀（`pmid:xxx`、`arXiv:xxx`，DOI 裸写），供 Zotero「按标识符添加」批量导入。

不做跨平台去重，也不判定是否已入库；重复与筛选由 Zotero 处理。当周无命中时，CSV 仅含表头。

## 站内搜索（两段式索引）

静态站点无后端，搜索完全在浏览器端完成：`build_site.py` 在导出阶段预生成两份 JSON 索引，`templates/assets/search.js` 加载并做加权子串匹配。

### 索引分层

| 索引 | 文件 | 字段 | 加载时机 |
| --- | --- | --- | --- |
| 头索引（head） | `site/data/search.json` | 标题、一句话、作者/期刊/日期、摘要（原文 + 中文） | 页面加载即取 |
| 深索引（deep） | `site/data/search-deep.json` | 仅 `{id, deep}`，`deep` 为 Paper Card + Review 的纯文本 | 勾选「深度搜索」时惰性拉取 |

两份索引都**覆盖全部文献**，按 `id` 对齐；深索引是头索引的**超集**而非替换——勾选深度搜索后，摘要、一句话等字段仍在，只是追加了 card/review 文本。

### 原理

- 分层依据是**字段类型**（小字段 / 大字段），不是命中结果：头索引只装天然小的字段，深索引装天然大的 card/review 正文。常驻下载的头索引体积可控，大字段在需要时再取。
- 检索为朴素加权子串匹配：查询先做 NFKD 折叠 + 小写 + 去除非字母数字，拆词后按 **AND** 语义（每个词均需命中）打分。字段权重 `title(18) > summary(6) > meta(4) > abstract(1)`；`subtitle`、`tags` 为预留空字段，`deep` 文本并入后按 `1` 计。命中标题/副标题整短语另有加成。
- 无词干、无模糊、无倒排索引；索引体积随文献数线性增长，`search.js` 是固定代码，不随文献增长。

### 注意点

- 内容**一字未动**：拆分只发生在 `build_site.py` 导出阶段，`Archive/` 内每篇的 `analysis.json` / `paper-card.md` / `review.md` 保持不变。
- 深度索引惰性加载：仅勾选「深度搜索」才下载 `search-deep.json`，加载失败自动回退到头索引搜索。
- 空结果提示：普通搜索无命中时，页面提示可勾选深度搜索到 card/review 中再找。

### 未来可扩展

- **倒排索引**：把每篇拆成「词项 → 文档列表」，查询取交集而非全表扫描，支撑更大语料。
- **中文分词**：当前折叠对中文逐字处理，改用 jieba 等分词可提升中文召回与短语匹配。
- **模糊 / 词干**：加入编辑距离、n-gram 或英文词干化，容忍拼写与形态差异。
- **分片索引**：文献量更大时按年份分片、按需加载，进一步压缩常驻体积。
- **托管 / 语义检索**：引入 Algolia、Typesense、Meilisearch 等托管搜索，或用 embedding 做语义相似检索（需额外服务或静态向量索引）。

## 日期口径（entrez date）

PubMed 的「发表日期」（DP）经常残缺或滞后——ahead-of-print 无日期、只到年月、空值，且文献被 PubMed 收录的时间晚于正式发表（标引时滞）。因此 PubMed 全线改用 **entrez date**（`[edat]`，即文献被 PubMed 收录的日期，形如 `YYYY/MM/DD HH:MM`），搜索、归档、Issue 三处同源：

- **搜索**：查询窗口用 `[edat]` 过滤，抓取「本周新进 PubMed 的文献」。每篇只在被收录那一周出现一次，无需重叠窗口与去重，`window_days: 7` 即可。
- **归档**：`Archive/pubmed/{year}/{month}/{id}/` 按 entrez date 归档，不再因 DP 残缺落进 `unknown/`。
- **Issue**：日期列显示 entrez date（归一为 `YYYY-MM-DD`），并按它升序排序。

真实发表日期并未丢弃——每篇完整元数据（含 DP）仍保留在 `Archive/*.json` 的 `data.source.pub_date` 中，需要时可随时取出。

预印本（arXiv / bioRxiv / medRxiv / chemRxiv）无标引时滞，仍用各自 posting 日期，不受影响。

## 密钥（PubMed）

PubMed 检索需要邮箱（必填）与 NCBI API key（可选），通过环境变量注入，不写入仓库：

- 本地：`export ENTREZ_EMAIL=you@example.com`，可选 `export NCBI_API_KEY=...`
- GitHub Actions：仓库 Settings → Secrets and variables → Actions → New repository secret，添加 `ENTREZ_EMAIL` 与 `NCBI_API_KEY` 两个 secret。

## LLM Agent

每篇命中文献跑一次 LLM 流水线，产出深度阅读材料，写入 `Archive/{source}/{year}/{month}/{id}/`：

- **评分 + 一句话**（`score_paper`，`max_tokens=500`，JSON 模式）：0–10 相关性打分 + 一句中文概括，写入 `analysis.json` 的 `score` / `one_liner_zh`，并进入 Issue 表格。
- **摘要翻译**（`translate_abstract`，`max_tokens=2000`）：原文摘要的精确中文翻译，写入 `analysis.json` 的 `abstract_zh`。
- **Paper Card**（`build_paper_card`，`max_tokens=16000`）：固定 16 节的深度阅读卡片，写入 `paper-card.md`。
- **Reviewer 报告**（`build_review`，`max_tokens=12000`）：单人评审报告，写入 `review.md`。

### 评分阈值门控

`config.yaml` 的 `llm.min_score`（默认 5）控制后两类深度产物的生成：仅当 `score >= min_score` 时才调用 Paper Card + Reviewer 报告；低于阈值则只保留「评分 + 一句话 + 摘要 + 摘要翻译」，不再生成 card/review。对应评分分档 0–4 / 5–7 / 8–10，5 为「部分命中」入口。

同时写入 `fulltext.md`（全文原文，含获取来源）与 `analysis.json`（元数据 + 各产物路径），并据此生成静态站点页面 `papers/{source}/{id}/index.html`（Issue「链接」列指向它）。站点页面顺序为 head 信息 → 摘要 → 摘要翻译 →（高分时）Paper Card → Reviewer 报告；低分篇只有前两者。

### 配置与密钥

- 模型与网关全部从环境变量读取，不写入仓库：`LLM_BASE_URL`（OpenAI 兼容网关）、`LLM_API_KEY`、`LLM_MODEL`（默认 `deepseek-chat`）。
- `config.yaml` 的 `llm` 块：
  - `enable_card` / `enable_reviewer`：是否生成 Paper Card / 评审报告（默认 `true`）。
  - `min_score`：生成 Paper Card + Reviewer 报告的评分阈值（默认 5）。
  - `concurrency`：LLM 并发线程数（默认 8）。
- GitHub Actions：repo Settings → Secrets and variables → Actions 添加 `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`。

### 模型选型与升级

模型经 `LLM_MODEL` 环境变量注入（`agent.py` 的 `model_name()`，默认 `deepseek-chat`），不写入仓库。**当前四个阶段（评分+一句话 / 摘要翻译 / Paper Card / Reviewer）共用同一个 `LLM_MODEL`。**

选型与升级时的注意点：

- **JSON 模式**：`score_paper` 以 `response_format={"type":"json_object"}` 请求结构化输出，所选模型必须支持 JSON mode，否则评分解析失败。DeepSeek 的 `deepseek-reasoner`（思考模型）通常不支持 JSON 输出，不能直接替换。
- **翻译忠实度**：`translate_abstract` 要求逐句忠实，思考/推理模式易「发挥」，不宜用于该阶段。
- **推理开销**：思考模型额外产生推理 token，计入输出、更慢更贵；卡片/评审单次输出已达 16k / 12k token，逼近客户端 180 s 超时（`make_client` 的 `timeout`）与 Actions 单 job 6 h 上限，改用思考模型前应先实测单篇延迟与 token 成本。
- **上下文长度**：需覆盖输入上限 `MAX_INPUT_CHARS = 180_000` 字符，256k token 上下文即够。
- **网关兼容**：需 OpenAI 兼容，支持 `chat.completions` 且可 `stream`。

未来按阶段分配更强模型时的注意点：

- 现为「单一模型全阶段」。若要按阶段分模型（如 `deepseek-chat` 跑评分/翻译、`deepseek-reasoner` 跑 card/review，或更强模型只跑高分篇），需把 `model_name()` 扩展为按阶段/按阈值取模型（如 `card_model` / `review_model`），或迁到 `config.yaml` 配置。
- 升级应逐阶段 A/B，先确认该模型的 JSON mode 支持、`max_tokens` 语义与实测延迟，再全量切换。
- 评分模型能力变化会改变分档分布，进而影响 `min_score` 门控通过率——换模型后应观察高分篇数量与 Card/Review 生成量是否失控。

### 并发与时长

LLM 调用以网关 IO 等待为主：每篇必跑「评分 + 翻译」两段短生成，`score >= min_score` 的篇再追加 Paper Card + Reviewer 两段长生成。每周 80+ 篇顺序跑会超过 GitHub Actions 单 job 6 小时上限，因此用线程池并发：墙钟时间从「每篇耗时之和」压到约「每篇耗时 × (篇数 / 并发)」。`concurrency` 按网关 QPS 承受力调，默认 8。

全文获取本身（约 2–4 s/篇，命中限流 30–90 s）远小于任一次 LLM 生成，不是瓶颈；LLM 调用失败会重试（指数退避，最多 4 次），单篇失败只跳过该篇、不中断整批。

## 本地运行

```bash
pip install pyPaperFlow
export ENTREZ_EMAIL=you@example.com
python scripts/monitor.py --config config.yaml --out-dir . --issue-body /tmp/issue.md
python scripts/build_site.py --out-dir . --config config.yaml
```

调整时间窗口：`--window-days 1`，或修改 `config.yaml` 中的 `window_days`。

## 测试

`tests/` 是 pytest 自检用例（不参与部署，可安全删除）。`tests/conftest.py` 会把 `scripts/` 注入 `sys.path`，所以测试里可直接 `import agent` / `import monitor` 等。

```bash
pip install pytest        # 或 pip install -r requirements.txt（已含 pytest）
pytest                    # 或 python -m pytest tests/ -q
```

平台 query 语法与调优记录见母仓 `docs/topics-catalog.md` 与本课题 `topics/idp-interaction-ai/test-notes.md`。
