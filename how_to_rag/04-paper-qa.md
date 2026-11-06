# 04 · PaperQA2（paper-qa）

> 专为科学文献设计的 agentic RAG。**首选主引擎**。

## 定位

Python 包 + `pqa` CLI。核心差异点：**答案内联引用（citation key）+ 末尾 References 书目**，天然可溯源；agentic 多轮（`paper_search → gather_evidence → gen_answer`）；**Tantivy 持久索引 + 文件 hash 去重**，增量最省心。

## 语料接入（含引用元数据）

目录递归（`recurse_subdirectories=True`，`rglob`），接受 `.txt .pdf .html .md .xlsx .docx .pptx`。

> ⚠️ **关键坑**：`read_doc` 只对 `.txt`/`.html` 走文本 chunker（`chunk_text`），`.md` 会落到 `else` 分支走 **code chunker**（`chunk_code_text`），分块质量对论文正文是退化的。**所以喂它请导出 `.txt`**。

**推荐用专用脚本 `feed_paperqa.py`**：它一次性完成三件事——导出 `.txt` 语料、生成 `manifest.csv`（把 DOI/标题/作者/年份/期刊的引用元数据绑到每个文件）、生成 `paperqa_settings.json`。这样 paper-qa 的 **References 显示的是真实引文**（"Smyth, John A, Jones, B, et al. (2026). Title. J Mol Biol. doi:..."），而不是文件名。

```bash
# 生成语料 + manifest + settings
python how_to_rag/feed_paperqa.py --archive Archive --out paperqa_corpus \
    [--doc-type fulltext|card|review|all]

# 安装为命名设置，然后建索引 / 提问
mkdir -p ~/.pqa/settings
cp paperqa_settings.json ~/.pqa/settings/rag.json
export OPENAI_API_KEY="$LLM_API_KEY"
pqa --settings rag index paperqa_corpus
pqa --settings rag ask "Which diffusion models generate IDP ensembles?"
```

要点：
- **manifest** 是 paper-qa 原生机制（`Settings.agent.index.manifest_file`），按 `file_location` 列把每个文件映射到 `DocDetails` 字段。
- 脚本把 `parsing.use_doc_details` 设为 `false`：**离线、确定性地用我们自己的引文**，不让 paper-qa 在索引时去 Crossref/S2 做网络水合而覆盖本地题录。
- DOI 来源：PubMed 从原始 `{id}.json` 的 `identity.doi` 提取；预印本（bioRxiv/medRxiv/chemRxiv）的 `id` 本身就是 DOI；拿不到就留空（引文仍完整可用）。

> 若只想快速裸跑、不挂引用元数据（References 会退化成文件名），也可用 `export_corpus.py --ext txt` 只导 `.txt`，直接 `pqa index corpus_flat_txt`。

## 安装

```bash
cd how_to_rag/paper-qa
uv sync                 # 或 pip install paper-qa
# 需要本地 embedding 时：uv sync --extra local
```

Python ≥3.11（`.python-version` 写 3.13）。CLI 入口只有一个：`pqa`。

## 配置（Settings）

pydantic `Settings`，**无 `PAPERQA_*` 前缀**；env 用字段名（大小写不敏感）+ 标准 LiteLLM 的 key（`OPENAI_API_KEY` 等）。

| 字段 | 默认 | 作用 |
|---|---|---|
| `Settings.llm` | `gpt-4o` | 答案 LLM（改成我们网关模型） |
| `Settings.llm_config` | — | LLM 连接配置（base_url 等） |
| `Settings.embedding` | `text-embedding-3-small` | embedding 模型 |
| `Settings.agent.agent_type` | `ToolSelector` | agent 类型 |
| `Settings.agent.index.paper_directory` | cwd | 文献目录（指向 `corpus_flat_txt`） |
| `Settings.answer.answer_max_sources` | 5 | 答案最多引用来源数 |
| `Settings.answer.evidence_k` | 10 | 每条证据的检索 chunk 数 |
| `Settings.parsing.reader_config` | `chunk_chars 5000 / overlap 250` | 分块参数 |

- 预置 presets：`high_quality` / `fast` / `debug`（`src/paperqa/configs/*.json`）。
- 自定义：`pqa save` 写入 `~/.pqa/settings/<name>.json`（`PQA_HOME` 可改路径）。

**对接 OpenAI 兼容网关**（DeepSeek 等）：

```bash
export OPENAI_API_KEY="$LLM_API_KEY"
# 用 Settings 指定 base_url 与 model，或写一个 JSON preset：
#   { "llm": "deepseek-chat", "llm_config": {"base_url": "$LLM_BASE_URL"} }
```

## 摄入 / 增量

```bash
# 建索引（首次全量，之后增量：hash 去重，跳过已索引文件）
pqa index corpus_flat_txt

# 直接问（无索引时自动先建索引）
pqa ask "Which diffusion models generate conformational ensembles of IDPs?"

# 检索已有索引
pqa search "sampling techniques for disordered proteins"
pqa search --index answers "..."     # 检索历史答案
```

- `--settings high_quality`（或你保存的 preset）、`--index default` 控制预设与索引名。
- **增量机制**：Tantivy 持久索引 + `files.zip` 记录 `{file: hash}`；`add_document` 对 hash 未变的文件**跳过、不重 embedding**；`sync_with_paper_directory=True`（默认）自动移除目录里已删的文件。
- 索引名默认 `pqa_index_<md5>`（由 paper_directory + embedding + chunk 参数哈希生成，换配置自动换索引）。

## 查询 / 编程

- **CLI**：`pqa ask`（答案 + 内联 `[citation]` + References）、`pqa search`、`pqa view`、`pqa save`。
- **Python API**：`from paperqa import Settings, Docs, QueryRequest`，可编程跑批、自定义 agent。

## 资源与注意

- 轻量（Python 进程 + Tantivy），面向论文、带引用，最贴「文献 RAG 可溯源」。
- 需一个支持 JSON/工具调用的 LLM（我们的 DeepSeek 网关即可）。
- 坑：`.md → code chunker`，务必 `.txt` 导出；`answer_max_sources` 控制引用数量防冗长。
