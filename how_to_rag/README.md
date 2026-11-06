# 用第三方 RAG 消化文献仓库 —— 使用文档与执行方案

本目录回答一个问题：**我们爬取并沉淀在 `Archive/` 里的文献，如何用现成的第三方 RAG 工具变成「可问、可溯源到原文段落」的记忆。**

> 文献 RAG 不替你读、不替你写——它把私有语料里"归档的文本"变成可检索、可引用的问答对象。省掉的是检索与引用核对的摩擦，留下的是你自己的判断。

---

## 一、我们的语料是什么

`Archive/{source}/{year}/{month}/{id}/` 下每篇文献一个目录：

| 文件 | 内容 | RAG 角色 |
|---|---|---|
| `fulltext.md` | 全文原文（拿不到全文则回落摘要） | **主料**：英文原文，RAG 检索效果最好 |
| `paper-card.md` | 16 节中文精读卡片（score ≥ 5） | 辅料：中文精读，问答时可作补充 |
| `review.md` | 中文审稿人评审（score ≥ 5） | 辅料：批判视角 |
| `analysis.json` | 评分 / 一句话 / 摘要翻译 | 结构化元数据，一般不直接进 RAG |

量级：约 **3000 篇、每周 +30 篇**（2026-09 实测）。

工具要的是**扁平的文本文件列表**，而 `Archive/` 是嵌套目录 + 每篇多文件。先用 `export_corpus.py` 归一化，见 [00-语料准备](./00-corpus.md)。

---

## 二、五个工具一句话定位

| 工具 | 一句话 |
|---|---|
| **paper-qa** | 专为科学文献的 agentic RAG，**带引用的答案** + 增量索引，最贴「可溯源问答」 |
| **mcp-local-rag** | 本地 MCP RAG server，在 Claude Code / MCP 客户端里私有检索（README 已演示过） |
| **ragflow** | 企业级 RAG 引擎，DeepDoc 解析 + 混合检索 + 重排 + 图形门户，最重但检索最强 |
| **anything-llm** | 一体化单容器私有 LLM，最轻的「和文献聊天」Web 门户 |
| **dify** | LLMOps 平台，知识库 + 工作流/Agent 编排，适合把 RAG 嵌进自动化流水线 |

---

## 三、对比矩阵

| 维度 | paper-qa | mcp-local-rag | anything-llm | ragflow | dify |
|---|---|---|---|---|---|
| 形态 | Python 包 + `pqa` CLI | MCP server + CLI | 单 Docker 容器 | Docker 多容器平台 | Docker 多容器平台 |
| 资源 | 轻（CPU） | 轻（CPU） | 轻（~2GB） | 重（~8GB，多容器） | 中重（≥4GB） |
| 向量库 | Tantivy（内置） | LanceDB | LanceDB | ES/Infinity/… 可选 | Weaviate（默认） |
| 语料接入 | 目录递归（建议 `.txt`） | `.md` 递归 | `.md` 上传 | `.md` 上传 | `.md` 上传 |
| **增量更新** | `pqa index` 原生增量（hash 去重） | `sync` 原生增量（SHA-256） | UI/API 重传 | 无 delta，脚本逐文件上传 | 单文件异步索引 |
| 溯源 | **答案内联引用 + References** | 返回原文 chunk（filePath/chunkIndex） | 引用来源 | 引用来源 + 重排 | 引用来源 |
| 查询接口 | CLI / Python API | MCP 工具 / CLI | Web + REST + OpenAI 兼容 | Web + REST + OpenAI 兼容 | Web + REST |
| 适合 | 带引用的论文问答 | Claude Code 内私有 RAG | 最简单 UI 门户 | 团队门户 + 最强检索 | 编排 agent 工作流 |

---

## 四、选型建议

按你的目标对号入座：

1. **要「带溯源引用的科学问答」** → **paper-qa**（首选）。它生来就是为论文设计的，答案内联 citation、末尾带 References，增量索引也最省心。
2. **要「在 Claude Code / MCP 里本地私有 RAG」** → **mcp-local-rag**（已集成、已演示，继续用，`sync` 做每周增量）。
3. **要「团队可访问的 Web 门户 + 强混合检索」** → **ragflow**（重但检索最强）/ **anything-llm**（轻、够用）。
4. **要「把 RAG 编进 agent / 工作流」** → **dify**。

**推荐组合（双轨）：**
- **主引擎 = paper-qa**：承接「问文献、要引用」的深度问答。
- **交互兜底 = mcp-local-rag**：Claude Code 里随手问，走 MCP，本地私有、零成本。
- 需要**分享给他人**时，再按轻/重上 **anything-llm** 或 **ragflow**。

---

## 五、执行方案（分阶段）

### Phase 0 —— 语料标准化（半天）
1. 跑 `export_corpus.py` 产出扁平语料：`python how_to_rag/export_corpus.py --archive Archive --out corpus_flat --doc-type all`。
2. 为 paper-qa 单独导一份 `.txt`：`--doc-type fulltext --ext txt --out corpus_flat_txt`。
3. 定语料边界：默认只喂 `fulltext.md`（英文原文，检索最干净）；需要中文精读问答时再加 `paper-card.md` / `review.md`。

### Phase 1 —— 落地 paper-qa（主引擎，1–2 天）
1. `uv sync` 装依赖，配 OpenAI 兼容网关（`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`）与 embedding。
2. `python how_to_rag/feed_paperqa.py --archive Archive --out paperqa_corpus` 生成 `.txt` 语料 + `manifest.csv`（引用元数据）+ settings。
3. `pqa --settings rag index paperqa_corpus` 全量建索引（~3000 篇）。
4. `pqa --settings rag ask "..."` 验证：答案是否有内联引用、References 是否点得到原文段落。
5. 详见 [04-paper-qa](./04-paper-qa.md)。

### Phase 2 —— 固化 mcp-local-rag（本地 MCP，半天）
1. 用 `claude mcp add` 把 mcp-local-rag 挂进 Claude Code，`BASE_DIR` 指向 `corpus_flat`。
2. 首跑 `ingest`，之后每周 `sync` 增量。
3. 详见 [02-mcp-local-rag](./02-mcp-local-rag.md)。

### Phase 3（可选）—— 上 Web 门户
- 团队共享、要界面 → 轻量先试 **anything-llm**（单容器 2GB）；检索要求高再上 **ragflow**。
- 详见 [03-anything-llm](./03-anything-llm.md) / [01-ragflow](./01-ragflow.md)。

### Phase 4 —— 接入每周自动化
把「monitor / backfill 跑完 → 增量更新 RAG」串进工作流（脚本或 workflow 追加一步）：

| 工具 | 增量命令 / 动作 |
|---|---|
| paper-qa | `pqa index corpus_flat_txt`（hash 去重，秒级跳过已索引文件） |
| mcp-local-rag | `mcp-local-rag sync corpus_flat` |
| anything-llm | `POST /v1/document/upload` 上传新增文件 |
| ragflow | `POST /api/v1/datasets/{id}/documents` 逐文件上传 |
| dify | `POST /v1/datasets/{id}/document/create-by-file` |

---

## 六、文件索引

| 文件 | 内容 |
|---|---|
| [00-corpus.md](./00-corpus.md) | 语料结构 + `export_corpus.py` 用法 + 各工具语料偏好 |
| [01-ragflow.md](./01-ragflow.md) | RAGFlow 部署 / 配置 / 摄入 / 增量 / 查询 |
| [02-mcp-local-rag.md](./02-mcp-local-rag.md) | mcp-local-rag 安装 / MCP 配置 / ingest+sync / query |
| [03-anything-llm.md](./03-anything-llm.md) | AnythingLLM 部署 / 配置 / 上传 / API |
| [04-paper-qa.md](./04-paper-qa.md) | PaperQA2 安装 / Settings / index+ask / 增量 |
| [05-dify.md](./05-dify.md) | Dify 部署 / 配置 / 知识库 / 工作流 / API |
| [export_corpus.py](./export_corpus.py) | 语料归一化脚本（扁平化） |
| [feed_paperqa.py](./feed_paperqa.py) | 生成 paper-qa 语料 + 引用 manifest + settings |

> 所有命令 / 配置均以本目录下已 clone 的工具源码为准（ragflow v1.0.0-rc1、mcp-local-rag 0.21.0、paper-qa、dify 1.17.1、anything-llm）。不同版本以各自 `--help` / `.env.example` 为准。
