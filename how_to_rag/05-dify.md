# 05 · Dify

> 版本：本目录 clone 的是 **1.17.1**（`langgenius/dify-api:1.17.1`）。

## 定位

LLMOps 平台：**知识库 + 工作流/Agent 可视化编排 + Service API**。适合把「文献检索 → 生成」编进可复用、可调度的流水线，而不是单点问答。

## 语料接入

原生 Markdown：`.md/.markdown/.mdx → MarkdownExtractor`，`.txt → TextExtractor`。建 Dataset（知识库）上传 `corpus_flat/` 文件；分块可配（automatic：`delimiter=\n, max_tokens=500, overlap=50`；custom 可改 delimiter/max_tokens/overlap）。

## 部署

```bash
cd how_to_rag/dify/docker
cp .env.example .env
docker compose up -d        # 端口 80/443 (nginx)，API 内部 5001
```

服务较多：`api`/`worker`/`worker_beat`/`web`、`postgres`（默认 DB）、`mysql`、`redis`、`weaviate`（默认向量库）、`sandbox`、`plugin_daemon`、`agent_backend`、`ssrf_proxy`、`nginx`。

| 项 | 值 |
|---|---|
| 门户 | `http://localhost` |
| RAM | ≥4GB |

## 配置（`docker/.env`）

| 键 | 说明 |
|---|---|
| `OPENAI_API_BASE` | OpenAI 兼容网关 base URL（= `LLM_BASE_URL`），key 在 UI 填 |
| `VECTOR_STORE` | 默认 `weaviate`（可 qdrant/pgvector/chroma） |
| `WEAVIATE_ENDPOINT` / `WEAVIATE_API_KEY` | 向量库连接 |
| `INIT_PASSWORD` | 首跑向导设管理员密码（空则向导里设） |

- **LLM provider**：首次 web setup 建管理员后，在 UI（plugin marketplace）添加模型 provider，key 填在 UI 里，不入 `.env`。Embedding 在**每个 dataset 创建时**选。
- 可 `NEW_USER_DEFAULT_MODELS` 预设新用户默认模型。

## 摄入 / 增量

**Web UI**：知识库 → 添加文件。

**Service API**（`Authorization: Bearer <dataset-scoped API key>`，key 在 UI 生成）：

```bash
curl -X POST "http://localhost/v1/datasets/{dataset_id}/document/create-by-file" \
  -H "Authorization: Bearer $DIFY_API_KEY" \
  -F "file=@corpus_flat/pubmed_42079037_fulltext.md"
```

- **增量**：每个新文件**独立异步索引**（不整库重 embedding）；用 `GET /v1/datasets/{id}/documents/{batch}/indexing-status` 追踪。
- 批量上传受 `NGINX_CLIENT_MAX_BODY_SIZE=100M` 限制；`update-by-file` 可更新已有文档。

## 查询 / 编排

- **Web UI**：知识库 hit-testing、Chatflow、Workflow。
- **Service API**：
  - `GET /v1/datasets/{id}/retrieve`（纯检索，hit testing）
  - `POST /v1/chat-messages`（对话式）
  - `POST /v1/completion-messages`（补全式）
  - `POST /v1/workflows/run`（跑工作流）
- **检索**：`hybrid_search`（`semantic_search | full_text_search | hybrid_search`）+ **rerank** + **metadata 过滤**（`metadata_filtering_mode` + conditions）。

## 资源与注意

- 中重（4GB+），强在**工作流编排 + 可视化 + 生态**；检索/重排/元数据能力齐全。
- 适合**把 RAG 嵌进 agent 工作流**（如「检索 → 对比 → 生成综述」），而非单纯的「问一句答一句」。
- API 是 Service API（dataset-scoped key），比 ragflow 的 API 更面向应用集成。
