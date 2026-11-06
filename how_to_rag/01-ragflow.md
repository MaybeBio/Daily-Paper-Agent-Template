# 01 · RAGFlow

> 版本：本目录 clone 的是 **v1.0.0-rc1**（Go 重写版，2026-09-29）。镜像 `infiniflow/ragflow:v1.0.0-rc1`。

## 定位

开源企业级 RAG 引擎（InfiniFlow）。核心卖点：**DeepDoc 深度文档解析**（版面/表格/公式理解）+ **混合检索（BM25 + 向量）+ 重排** + 图形门户 + 完整 HTTP API。检索能力是五者中最强的，但部署最重。

## 语料接入

原生支持 Markdown。把 `export_corpus.py` 导出的 `.md` 文件（`corpus_flat/`）作为文档上传。每篇 `fulltext.md` = 一个 document；`paper-card.md`/`review.md` 可作为额外文档加入同一知识库（KB）。

## 部署

```bash
cd how_to_rag/ragflow/docker
# 先看 .env：DEVICE=cpu|gpu、TEI_MODEL、MEM_LIMIT
docker compose up -d
```

服务较多：`ragflow-cpu`（API+ingest+DeepDoc）、`mysql`、`minio`（对象存储）、`kvrocks`/`nats`（缓存/MQ）、文档引擎（`es01`/`opensearch01`/`infinity` 等按 profile 选）、`clickhouse`、`tei`（embedding）、`jaeger`、`kibana`、`sandbox`。

| 项 | 值 |
|---|---|
| Web 门户 | `http://localhost`（80/443） |
| HTTP API | `:9380` |
| Admin | `:9381` |
| MCP | `:9382` |
| 内存 | 每 DB/ES 容器 `MEM_LIMIT` 约 8GB，整栈建议 8GB+ |
| GPU | 可选（`DEVICE=gpu`，tei-gpu 用 NVIDIA；DeepDoc 在 1.0 是 CPU-only） |

## LLM / Embedding 配置

**LLM（v1.0 起改为 UI 内配置，不再是 env）**：登录后 `User settings → Model providers` 添加 provider，或走 Admin API。对接我们的 OpenAI 兼容网关，选 OpenAI-compatible 类 provider，填 `base_url=LLM_BASE_URL`、`api_key=LLM_API_KEY`、`model=LLM_MODEL`。

> 首启默认账号：`admin@ragflow.io` / 密码 `admin`（`docker/.env` 的 `ADMIN_DEFAULT_PASSWORD`）。Bootstrap 默认 LLM 在 `conf/service_conf.yaml` 的 `user_default_llm`（`factory`/`api_key`/`base_url`/`default_models`）。

**Embedding**：在 `docker/.env` 里设 `TEI_MODEL`（默认 `Qwen/Qwen3-Embedding-0.6B`，可改 `BAAI/bge-m3`、`bge-small-en-v1.5`）。TEI 服务端口 `TEI_PORT=6380`。

## 摄入

**Web UI**：建 Knowledge Base → 上传文件（支持文件夹上传，直接把 `corpus_flat/` 拖进去）。

**HTTP API**（脚本化，推荐）——单次可带多个 `-F file=`：

```bash
# 先建 KB，拿到 dataset_id
curl -X POST "http://localhost:9380/api/v1/datasets" \
  -H "Authorization: Bearer $RAGFLOW_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "idp-interaction-ai", "embedding_model": "BAAI/bge-m3", "chunk_method": "naive"}'

# 上传文档（可循环，可多 -F）
curl -X POST "http://localhost:9380/api/v1/datasets/{dataset_id}/documents" \
  -H "Authorization: Bearer $RAGFLOW_API_KEY" \
  -F "file=@corpus_flat/pubmed_42079037_fulltext.md"
```

- API key：UI 头像 → API 里生成，请求头 `Authorization: Bearer <key>`。
- **解析器**：`DeepDoc`（默认，CPU-only）、`Naive`、`MinerU`、`Docling`。纯 Markdown 文本建议用 **`Naive`**（快、够用）；要版面理解才用 DeepDoc。
- **分块**：`naive`/`general`（默认 512 token）、Title/Token chunker、父子 sub-chunk。

## 增量更新

**没有原生 delta/同步**。每周 monitor 跑完，脚本循环上传**新增**文件到已有 dataset：

```bash
# 只传新文件（corpus_flat 里新增的那批）
for f in corpus_flat/*_fulltext.md; do
  curl -X POST "http://localhost:9380/api/v1/datasets/{dataset_id}/documents" \
    -H "Authorization: Bearer $RAGFLOW_API_KEY" -F "file=@$f"
done
```

上传后 document 进入 `run` 状态（解析+切分+embedding），用 `GET /api/v1/datasets/{id}/documents` 查状态。已存在的 document 不会自动去重，所以**增量脚本要自己维护「已上传清单」**，或用 `export_corpus.py --force` 的产物做 diff。

## 查询

- **Web UI**：KB 内 Chat。
- **REST**：`POST /api/v1/chats/{chat_id}/completions`。
- **OpenAI 兼容**：`POST /api/v1/openai/{chat_id}/chat/completions`。

## 资源与注意

- 最重（多容器、8GB+），适合**长期跑 + 要图形门户 + 要最强混合检索/重排**时选。
- 版本刚从 v0.x 迁到 v1.0.0-rc1（Go 重写），API/配置与旧教程对不上的地方以 `docs/` 为准。
- 增量去重要自己管理；3000 篇 × 3 文件 ≈ 9000 次上传，建议脚本化并留进度。
