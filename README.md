<p align="center">
  <img src="assets/banner.svg" width="100%" alt="BioLit Agent —— 生物医学 × 计算 文献自动追踪 + AI 深度精读模板">
</p>

<h1 align="center">BioLit Agent</h1>

<p align="center">
  <strong>生物医学 × 计算交叉领域的文献自动追踪 + AI 深度精读模板</strong><br/>
  用 GitHub Actions 按周期自动追踪 <b>PubMed · arXiv · bioRxiv · medRxiv · chemRxiv</b> 上的最新文献，存档落盘、生成 Issue 周报，再用 LLM 为每篇产出「评分 + 一句话 + 摘要翻译 + 16 节 Paper Card + 审稿人评审」，并同步部署一个可全文检索的 GitHub Pages 站点，配合 Zotero 完成筛选与入库。
</p>

<p align="center">
  <img src="https://img.shields.io/badge/pyPaperFlow-powered-7C3AED?style=for-the-badge" alt="pyPaperFlow powered">
  <img src="https://img.shields.io/badge/platforms-PubMed%C2%B7arXiv%C2%B7bioRxiv%C2%B7medRxiv%C2%B7chemRxiv-0EA5E9?style=for-the-badge" alt="Supported platforms">
  <img src="https://img.shields.io/badge/schedule-weekly%C2%B7GitHub%20Actions-0D9488?style=for-the-badge" alt="Weekly via GitHub Actions">
  <img src="https://img.shields.io/badge/AI-LLM%20deep%20reading-F59E0B?style=for-the-badge" alt="LLM deep reading">
  <img src="https://img.shields.io/badge/output-Archive%20%2B%20Discovery%20%2B%20Site-4F46E5?style=for-the-badge" alt="Outputs">
  <img src="https://img.shields.io/badge/reading-Zotero%20ready-10B981?style=for-the-badge" alt="Zotero reading">
</p>

<p align="center">
  <a href="#-三步上手">三步上手</a> ·
  <a href="#-设计思路">设计思路</a> ·
  <a href="#-抓取与产出">抓取与产出</a> ·
  <a href="#-ai-深度精读流水线">AI 深度精读</a> ·
  <a href="#-静态站点与站内搜索">站点与搜索</a> ·
  <a href="#-平台检索要点">平台检索要点</a> ·
  <a href="#-密钥与仓库配置">密钥与仓库配置</a> ·
  <a href="#-本地运行与调试">本地运行与调试</a> ·
  <a href="#-每周阅读工作流">每周阅读工作流</a>
</p>

> **模板即实例。** 仓库内的 `config.yaml` 与 `prompts.yaml` 已内置一套完整可跑的示例检索式与提示词 —— 拿到后你只需改**两个文件**：`config.yaml`（换成你的研究领域）与 `prompts.yaml`（换成你领域的措辞）。工具与平台默认面向 **生物医学 × 计算**交叉课题。核心驱动为我们自研的文献检索获取工具 [pyPaperFlow](https://github.com/MaybeBio/pyPaperFlow)。

---

## 🚀 三步上手

| 步骤 | 你要做的 | 具体内容 |
|---|---|---|
| **1 · 换领域** | 编辑 [`config.yaml`](./config.yaml) 与 [`prompts.yaml`](./prompts.yaml) | 改检索式与命名、换 4 个 prompt 的领域措辞，具体见下方「换课题（最终操作）」 |
| **2 · 设定时与密钥** | 配置 [`workflow`](./.github/workflows/monitor.yml)、Secrets 与 Pages | 确认 `monitor.yml` 的 cron；在 **Settings → Secrets and variables → Actions** 添加 `ENTREZ_EMAIL`（必填）、`NCBI_API_KEY`（可选）与 `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`（AI 必填）；并在 **Settings → Pages** 启用 Pages（来源选 GitHub Actions） |
| **3 · 每周收报** | 等待或手动触发 actions | 有新文献时自动开一条 **Issue 周报**，同时更新 **GitHub Pages 站点**：按相关度评分排序，逐篇可读摘要翻译、16 节 Paper Card 与审稿人评审，并支持全文检索 |

### 🔄 换课题（最终操作）

1. GitHub 上 **Use this template** 建新仓库
2. 改 `config.yaml`：`topic`、`title`、`site_base_url`、`platforms.*.query`
3. 改 `prompts.yaml`：4 个 prompt 里与领域相关的措辞
4. 配 Secrets：`ENTREZ_EMAIL`、`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`
5. **先启用 Pages**：**Settings → Pages** 把来源设为 **GitHub Actions**（不启用则站点不会部署）
6. 手动 `workflow_dispatch` 跑一次验证

> 推送到 `main` 后也可在仓库 **Actions** 页手动触发试跑；想先本地验证见「本地运行与调试」。

---

## 💡 设计思路

一句话：

> **每周自动「替你搜一遍研究领域」→ 新文献永久存档、另出一张可筛选清单 → LLM 为每篇写深度阅读材料 → 开一条 Issue 提醒、部署一个站点沉淀下来。** 最后是否精读、入库、去重，都留给你自己判断。

设计取舍：

- **元数据分发，不碰版权全文** —— 只抓题录 / 作者 / 摘要 / DOI，轻量合规；要全文时按需走你自己的文献工具，或继续使用我们自研的 pyPaperFlow。
- **双份数据落盘，职责分离** —— 只增的 `Archive/` 当文献库底账；按周的 `Discovery/` 快照当筛选清单；`site/` 再把这些数据渲染成可检索的静态站点。
- **AI 负责「读」，你负责「判」** —— 每篇自动产出评分、翻译、Paper Card 与评审报告，把「要不要读原文」的决策成本压到最低，但最终判断仍在你。
- **Issue 即提醒，站点即沉淀** —— 不额外接邮件推送，有命中才开、零命中不打扰；静态站点把每周产出永久沉淀、可全文检索。
- **密钥不入库** —— PubMed 凭据与 LLM 密钥一律走环境变量 / Actions Secret。
- **一个课题一个仓** —— 同一骨架可复制成多个独立仓库，并行追踪多个方向。

---

## 🧬 抓取与产出

**抓什么：** 每周期一次，逐平台用 pyPaperFlow 检索「窗口内新文献」；窗口 = 运行日往前 `window_days` 个自然日（不含当天）。

**三类产物：**

| 产物 | 内容 | 归档路径 | 口径 |
|---|---|---|---|
| `Archive/` | 逐篇**完整**元数据 JSON + LLM 深度阅读材料 | `Archive/<source>/<year>/<month>/<id>/` | 只增不删，按月归档 |
| `Discovery/` | 合并 CSV + `_ids.txt` | `Discovery/<year>/<month>/<topic>_<date>.csv` | 按抓取日归档 |
| `site/` | 静态站点（解析页 + 搜索索引） | `site/`，由 Pages 部署 | 每次运行重建 |

`Archive/` 下每篇文献是一个目录：

```
Archive/{source}/{year}/{month}/{id}/
  {id}.json         # 完整元数据（pyPaperFlow 原始 JSON）
  fulltext.md       # 全文原文（含获取来源；拿不到则回落摘要）
  analysis.json     # 元数据 + 评分 / 一句话 / 摘要翻译 + 各产物路径
  paper-card.md     # 16 节深度阅读卡片（score ≥ min_score 才生成）
  review.md         # 审稿人评审报告（score ≥ min_score 才生成）
```

**CSV 固定 9 列**（`utf-8-sig`，Excel 友好）：

```
source, id, doi, title, authors, journal, published_date, url, abstract
```

`id` 为平台主键（PubMed = PMID，预印本 = DOI）。**`_ids.txt`** 每行一个标识符，供 Zotero「按标识符添加」批量导入：`pmid:xxx` / `arXiv:xxx`（自动去版本号）/ 其余预印本裸 DOI。

**日期口径（entrez date）：** PubMed 的 DP 常残缺且存在标引时滞，故搜索、归档、Issue 三处统一用 `[edat]`（被 PubMed 收录的日期）；真实 DP 仍保存在各 JSON 的 `data.source.pub_date`。预印本用 posting 日期。**不做跨平台去重、不判重**，当周某平台 0 命中时 CSV 仅含表头。

<details>
<summary><b>🗂️ 仓库结构</b></summary>

```
.
├── scripts/
│   ├── monitor.py                   # 主脚本：读 config → 逐平台检索 → 落盘 → 生成 Issue → 触发 LLM 流水线
│   ├── agent.py                     # LLM 层：OpenAI 兼容客户端 + 评分/翻译/Paper Card/评审 四个生成函数
│   ├── fulltext.py                  # 全文获取封装：优先原生全文，失败回落摘要
│   └── build_site.py                # 静态站点生成：遍历 Archive/ 渲染 Jinja2 模板
├── templates/                       # 站点模板（本周 / 归档 / 搜索 / 单篇解析页）+ 样式与搜索脚本
├── config.yaml                      # 检索配置：topic / title / window_days / llm / 每平台一条 query
├── prompts.yaml                     # 四个 system prompt（score / translate / paper_card / review）集中于此
├── assets/banner.svg                # README 头图
├── requirements.txt                 # 依赖：pyPaperFlow + openai + jinja2 等
├── tests/                           # pytest 自检用例（不参与部署，可删除）
└── .github/workflows/
    ├── monitor.yml                  # 定时任务 + 手动触发；跑完 commit+push 并开 Issue
    └── deploy_pages.yml             # monitor 成功后自动把 site/ 部署到 Pages
```

</details>

---

## 🤖 AI 深度精读流水线

每篇命中文献跑一次 LLM 流水线（OpenAI 兼容网关，system prompt 全部来自 `prompts.yaml`），产出深度阅读材料：

| 阶段 | 函数 | 产出 | 输出上限 |
|---|---|---|---|
| **评分 + 一句话** | `score_paper` | `analysis.json` 的 `score` / `one_liner_zh`：0–10 相关度打分 + 一句中文概括，进入 Issue 表格与站点排序 | 500 token（JSON 模式） |
| **摘要翻译** | `translate_abstract` | `analysis.json` 的 `abstract_zh`：原文摘要的忠实中文译文 | 2000 token |
| **Paper Card** | `build_paper_card` | `paper-card.md`：固定 16 节的深度阅读卡片 | 16000 token |
| **审稿人评审** | `build_review` | `review.md`：Nature 风格单人评审报告 | 12000 token |

### 评分阈值门控

`config.yaml` 的 `llm.min_score`（默认 5）控制后两类深度产物的生成：仅当 `score >= min_score` 时才调用 Paper Card + 评审报告；低于阈值则只保留「评分 + 一句话 + 摘要 + 摘要翻译」。对应评分分档 0–4 / 5–7 / 8–10，5 为「部分命中」入口。

站点单篇解析页的顺序为 head 信息 → 摘要 → 摘要翻译 →（高分时）Paper Card → （高分时）评审报告；低分篇只有前三者。

### 并发与时长

LLM 调用以网关 IO 等待为主，用线程池并发（`llm.concurrency`，默认 8）把墙钟时间从「每篇耗时之和」压到约「每篇耗时 × (篇数 / 并发)」，避免顺序跑 80+ 篇超出 GitHub Actions 单 job 6 小时上限。单篇失败只跳过该篇、不中断整批。

---

## 🌐 静态站点与站内搜索

`build_site.py` 遍历 `Archive/` 渲染出无后端静态站点，由 `deploy_pages.yml` 在 monitor 成功后自动部署到 GitHub Pages。页面包括：**本周推荐**（按评分排序）、**按年/周归档**、**全文搜索**、**单篇解析页**。

**站内搜索（两段式索引）**：站点无后端，搜索完全在浏览器端完成，索引在导出阶段预生成：

| 索引 | 文件 | 字段 | 加载时机 |
|---|---|---|---|
| 头索引（head） | `site/data/search.json` | 标题、一句话、作者/期刊/日期、摘要（原文 + 中文） | 页面加载即取 |
| 深索引（deep） | `site/data/search-deep.json` | 仅 `{id, deep}`，`deep` 为 Paper Card + 评审的纯文本 | 勾选「深度搜索」时惰性拉取 |

检索为朴素加权子串匹配：查询做 NFKD 折叠 + 小写 + 去除非字母数字，按 **AND** 语义打分；字段权重 `title(18) > summary(6) > meta(4) > abstract(1)`。深索引是头索引的**超集**而非替换——勾选深度搜索后摘要等字段仍在，只是追加了 card/review 正文。

> 全文获取来源（`fulltext_source`）：PubMed → PMC 全文，arXiv → ar5iv，bioRxiv/medRxiv → Europe PMC，chemRxiv 无全文路由恒回落摘要。

---

## 🧩 平台检索要点

各平台检索语法差异很大，详细的召回与噪声踩坑结论都写在各 query 正上方的注释里，改写时请务必保持：

- **PubMed** —— `(对象) AND (方法)` 括号两段式；Mesh 受标引时滞影响，周窗召回主要靠 `[tiab]` 精确词；`[edat]` 时间窗由代码自动拼接。
- **arXiv** —— 布尔项须写成 `all:"phrase"` / `all:word`，裸词会被强 AND、OR 失效；建议设 `max_results` 上限，否则会翻整周全部命中导致限速挂起。
- **bioRxiv / medRxiv** —— 同一检索器（Europe PMC + Crossref 超集）。**必须保留括号两段式，不可拍平成无括号 DNF**——Europe PMC（Lucene）会把无括号 AND/OR 混排错乱。
- **chemRxiv** —— 仅 Crossref 收录（Europe PMC 不覆盖），是唯一无严格索引的平台，接受一定噪声，交给 Zotero 兜底。

---

## 🔑 密钥与仓库配置

PubMed 与 LLM 凭据一律走环境变量，**不写入仓库**：

| 用途 | 环境变量 | 必填 |
|---|---|---|
| PubMed 邮箱 | `ENTREZ_EMAIL` | 必填 |
| NCBI API key | `NCBI_API_KEY` | 可选 |
| LLM 网关地址 | `LLM_BASE_URL` | AI 必填 |
| LLM API key | `LLM_API_KEY` | AI 必填 |
| LLM 模型 | `LLM_MODEL` | 可选（默认 `deepseek-chat`） |

- 本地：`export ENTREZ_EMAIL=you@example.com` 等。
- GitHub Actions：**Settings → Secrets and variables → Actions → Repository secrets / Variables** 新建对应项，workflow 以 `${{ secrets.* }}` / `${{ vars.* }}` 注入。

推送周期在 `monitor.yml` 的 `schedule.cron`（默认**周一 09:23 UTC**，避开整点）；workflow 权限为 `contents: write` + `issues: write`：跑完 commit+push 产物，再按是否命中决定开 Issue。站点部署由 `deploy_pages.yml` 监听 monitor 成功后自动触发，**需先在仓库 Settings → Pages 启用 Pages**（来源设为 **GitHub Actions**），否则 `deploy_pages.yml` 会因 Pages 未开启而失败。

> **模型选型提示：** 评分阶段走 `response_format={"type":"json_object"}`，所选模型必须支持 JSON mode（如 DeepSeek 的 `deepseek-reasoner` 通常不支持，不能直接替换）；评分/翻译要忠实、不宜用思考/推理模式；卡片/评审单次输出达 16k / 12k token，需留意网关超时与 token 成本。

---

## 🖥️ 本地运行与调试

```bash
pip install -r requirements.txt          # 或 pip install pyPaperFlow

export ENTREZ_EMAIL=you@example.com
export LLM_BASE_URL=... LLM_API_KEY=...   # 可选 LLM_MODEL=...

python scripts/monitor.py \
  --config config.yaml \                  # 指定检索配置
  --out-dir . \                           # Archive/ 与 Discovery/ 落在仓库根
  --issue-body /tmp/issue.md \            # （可选）生成的 Issue 正文
  --issue-title /tmp/issue.title          # （可选）生成的 Issue 标题

python scripts/build_site.py \
  --out-dir . \                           # 从 Archive/ 重建 site/
  --config config.yaml
```

| 常用参数 | 作用 |
|---|---|
| `--window-days 1` | 把窗口收窄到 1 天快速试跑，无需改 config |
| `--run-date 2026-09-03` | 固定运行日，便于回测某周 |

窗口默认不含运行当天；单平台失败仅告警，全部失败才非零退出。

**测试：** `tests/` 是 pytest 自检用例（不参与部署，可安全删除）。`pip install pytest && pytest` 即可。

---

## 📚 每周阅读工作流

1. 打开仓库 **Issues** 看当周推送报告，按平台与「评分 / 一句话」粗筛，点标题直达原文、点链接直达pages站点；
2. 打开 **Pages 站点**按相关度排序细读——需要深入了解时点进单篇解析页，读摘要翻译、16 节 Paper Card 与审稿人评审；
3. 感兴趣的先入库：用 Zotero 按本次 `Discovery/` 下 `_ids.txt`「按标识符添加」批量导入，去重与精筛在这一层完成；
4. 需要原文或深挖时，用文献工具按 DOI / PMID 二次获取，再走你自己的精读、检索与分析流程——下游工具（Zotero、agent、skill 等）自由接入。

---

<details>
<summary><b>❓ 常见问题</b></summary>

- **为什么按周而不是每日？** 默认 `window_days: 7` + cron 每周一运行；想改频次，改 config 与 cron 两处即可。
- **抓不全 / 有噪声怎么办？** 平台 query 的召回与噪声实测都记录在各 query 上方的注释里，按注释微调；残余噪声由 Zotero 层也就是人工筛掉。
- **能不能不要 AI 精读？** 把 `config.yaml` 的 `llm.enable_card` / `enable_reviewer` 设为 `false`，或直接不配置 LLM 密钥——检索、落盘、Issue 与站点仍照常运行，只是少了评分 / 翻译 / Card / 评审。
- **评分模型换了会影响什么？** 评分能力变化会改变分档分布，进而影响 `min_score` 门控通过率——换模型后应观察高分篇数量与 Card/Review 生成量是否失控。
- **能抓全文吗？** 本模板只做**元数据分发**，全文仅用于喂给 LLM 精读、不落版权文件；原文按需走你已有的文献工具获取。

</details>

---

> 这是一个刻意保持通用的**模板仓库**：属于你的只有 `config.yaml` 与 `prompts.yaml`，脚本、模板、工作流、测试基本不必动。把它复制成「一个课题 topic = 一个独立仓库」，即可同时追踪多个研究方向。
