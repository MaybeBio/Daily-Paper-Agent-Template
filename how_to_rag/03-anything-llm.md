# 03 · AnythingLLM

## 定位

一体化私有 LLM 应用：Workspace + 文档 + 向量库（LanceDB）+ Agent，**单 Docker 容器**跑完整服务。最轻的「和文献聊天」Web 门户。

## 语料接入

原生 `.md` / `.txt`（`collector` 接受的纯文本扩展名含 `.txt .md .org .adoc .rst`）。喂 `corpus_flat/` 的 fulltext.md（每个 Workspace 一个知识库，把同一课题的文献放进去）。

## 部署

```bash
cd how_to_rag/anything-llm/docker
cp .env.example .env
docker compose up -d        # 端口 3001
```

单 all-in-one 容器（内跑 `server` + `collector` 两个进程），`cap_add: SYS_ADMIN`（供 headless Chromium 用）。

| 项 | 值 |
|---|---|
| 门户 | `http://localhost:3001` |
| 内存 | ≥2GB（4–8GB 舒适） |
| 磁盘 | ≥10GB |

## 配置（`docker/.env`，即 `server/.env.example`）

| 键 | 说明 |
|---|---|
| `LLM_PROVIDER` | LLM 提供商（用 OpenAI 兼容网关填 generic-openai 类） |
| `GENERIC_OPEN_AI_BASE_PATH` | 网关 base URL（= `LLM_BASE_URL`） |
| `GENERIC_OPEN_AI_API_KEY` | 网关 key（= `LLM_API_KEY`） |
| `GENERIC_OPEN_AI_MODEL_PREF` | 模型（= `LLM_MODEL`） |
| `EMBEDDING_ENGINE` | 默认 `native`（本地 transformers.js） |
| `EMBEDDING_MODEL_PREF` | native 默认 `Xenova/all-MiniLM-L6-v2` |
| `VECTOR_DB` | 默认 `lancedb`（可改 pgvector/chroma/qdrant 等） |
| `JWT_SECRET` / `AUTH_TOKEN` | 认证 |

## 摄入

- **Web UI**：建 Workspace → 上传文档。
- **HTTP API**（`Authorization: Bearer <API key>`，key 在 UI 生成）：

```bash
curl -X POST "http://localhost:3001/api/v1/document/upload" \
  -H "Authorization: Bearer $ANYTHINGLLM_API_KEY" \
  -F "file=@corpus_flat/pubmed_42079037_fulltext.md"
```

> ⚠️ `collector/hotdir` 名带 "hot"，但**不是热文件夹**（无文件系统 watcher）——不能直接 drop 文件，必须走 UI 或 API 上传。

## 增量更新

UI / API 重新上传 → 自动重解析 + 重 embedding。**无本地文件同步**。每周 monitor 跑完，脚本对**新增文件** `POST /v1/document/upload`（已上传的同名文件需自己留意去重）。

## 查询

- **Web UI**：Workspace 内 Chat / 向量检索。
- **REST**：`POST /api/v1/workspace/:slug/chat`、`/vector-search`。
- **OpenAI 兼容**：`POST /api/v1/openai/chat/completions`。

## 资源与注意

- 最轻的 UI 门户（单容器 2GB），适合**快速要一个可分享的「和文献聊天」界面**，不想维护一堆容器。
- 检索能力中等（LanceDB + native embedding），不如 ragflow 的混合检索/重排。
- 3000 篇 markdown 是它最便宜的一类输入（纯文本，无 OCR），磁盘压力小。
