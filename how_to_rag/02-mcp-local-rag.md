# 02 · mcp-local-rag

> 版本：本目录 clone 的是 **0.21.0**。README 的「RAG 尝试」一节已用它做过单篇 + 多篇演示。

## 定位

本地 MCP RAG server（stdio）+ 同名 CLI。用 transformers.js 在本地跑 embedding（默认 `Xenova/all-MiniLM-L6-v2`），存储用 **LanceDB**（向量 + FTS 全文索引）。适合「在 Claude Code / 任意 MCP 客户端里做本地私有 RAG」，零外部依赖、CPU 即可。

## 语料接入

直接吃 `.md`，目录递归（BFS，`MAX_SCAN_DEPTH=10`，跳过 symlink 与 db/cache 目录）。喂 `export_corpus.py` 的 `corpus_flat/`（fulltext.md 为主，可按需加 card/review）。

## 安装

```bash
npm i -g mcp-local-rag           # 或 npx -y mcp-local-rag
# 本目录已 clone 源码：how_to_rag/mcp-local-rag
```

### 挂进 Claude Code（MCP）

```bash
claude mcp add mcp-local-rag -- npx -y mcp-local-rag \
  --db-path /path/to/corpus_flat/lancedb \
  --base-dir /path/to/corpus_flat
```

> 也支持 `skills install --claude-code` 装配套 skill；其他客户端（Codex/Cursor/OpenCode）见 README 的 JSON/TOML 块。

## 配置

无 config 文件，全部走 **env（MCP 模式）或 flag（CLI 模式）**：

| 键 | 默认 | 作用 |
|---|---|---|
| `BASE_DIR` / `BASE_DIRS` | — | 检索根目录（`BASE_DIRS` 是 JSON 数组，可多目录） |
| `DB_PATH` | `./lancedb/` | LanceDB 向量库路径 |
| `CACHE_DIR` | `./models/` | HF 模型缓存 |
| `MODEL_NAME` | `Xenova/all-MiniLM-L6-v2` | embedding 模型 |
| `RAG_HYBRID_WEIGHT` | `0.6` | 向量/FTS 混合权重 |
| `RAG_MAX_DISTANCE` / `RAG_MAX_FILES` | — | 召回距离/文件数上限 |
| `RAG_GROUPING` | `similar` | `similar`/`related` 分组 |
| `CHUNK_MIN_LENGTH` | `50` | 最小 chunk 长度 |
| `RAG_DEVICE` / `RAG_DTYPE` | `cpu` / `fp32` | 推理设备/精度 |
| `EMBED_TITLE_PREFIX` / `EMBED_HEADING_PREFIX` | — | 标题/小标题加权前缀 |
| `RAG_RERANK_CMD` / `RAG_RERANK_TIMEOUT_MS` | — | 外部重排命令 |

> 注意：**chunk size / overlap 不可调**——语义 chunker（Max-Min）参数硬编码。召回条数用 `query --limit` 控制。

## 摄入 / 增量

```bash
# 全量重建（delete + insert，适合首跑）
mcp-local-rag ingest corpus_flat

# 增量同步（SHA-256 contentHash 去重 + 清理已删文件）← 每周更新用这个
mcp-local-rag sync corpus_flat
```

- `ingest`：全量重建，每次把选中文件全部重新切分 + embedding。
- `sync`：**增量**——按文件字节 SHA-256 比对，只处理新增/变更文件，并 prune 已删除文件。
- 接受 `.pdf .docx .txt .md`。
- 换 `MODEL_NAME` / `RAG_DTYPE` / 前缀后，需**换新 `DB_PATH` 并重新 ingest**。

## 查询

**CLI**：

```bash
mcp-local-rag query "What is the role of the disordered N-terminus of 4E-BP2?" --limit 10
mcp-local-rag read-neighbors --file-path corpus_flat/xxx.md --chunk-index 60 --before 2 --after 2
mcp-local-rag list
mcp-local-rag status
mcp-local-rag delete corpus_flat/xxx.md      # 或 --source <url>
```

**MCP 模式**：Claude Code 自动调用其工具（search / ingest / query 等），返回 `{filePath, chunkIndex, text, score, fileTitle}`，可溯源到原文段落。

## 资源与注意

- 最轻：CPU、本地 embedding、LanceDB 单进程。模型首次下载约 90MB。
- FTS 用 ngram（min=2 max=3），支持中英混排检索。
- 语义 chunker 非定长，长段落可能混入干扰（README 已见 chunk 干扰案例）——回答时仍需「逐条判断」。
- 已在我们 README 演示过，**是当前最顺手、零成本的本地方案**。
