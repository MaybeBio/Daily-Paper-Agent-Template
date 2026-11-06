# 00 · 语料准备（Archive/ → RAG-ready）

## 语料结构

`Archive/{source}/{year}/{month}/{id}/`，`source ∈ {pubmed, arxiv, biorxiv, medrxiv, chemrxiv}`，`id` 为平台主键（PubMed=PMID，预印本=DOI），`{year}/{month}` 为归档日期（PubMed 用 `[edat]`）。

每篇一个目录，含 5 个文件，其中 3 个是 RAG 可用的文本：

```
Archive/pubmed/2026/09/42079037/
  fulltext.md       # 全文（英文），主料
  paper-card.md     # 16 节中文精读卡片（score>=5 才有）
  review.md         # 中文评审（score>=5 才有）
  analysis.json     # 元数据 + 评分/一句话/摘要翻译
  42079037.json     # pyPaperFlow 原始元数据
```

## 为什么需要归一化

五个 RAG 工具的摄入单元都是**扁平的文件列表**（上传一个文件 / 扫描一个目录），而 `Archive/` 是嵌套目录 + 每篇多文件。直接把 `Archive/` 喂给工具会：
- 混入 `*.json`（元数据）等非文本；
- 每篇 3 个 md 文件难以区分主次；
- 文件名 `fulltext.md` 重复几千次，丢失来源/ID 溯源信息。

`export_corpus.py` 把「嵌套 + 多文件」压成「扁平 + 带溯源的文件名」：

```
corpus_flat/
  pubmed_42079037_fulltext.md
  pubmed_42079037_card.md
  pubmed_42079037_review.md
  arxiv_2401.01234_fulltext.md
  ...
```

文件名 `{source}_{id}_{doctype}.{ext}` 保留了溯源所需的来源与主键。

## 用法

```bash
# 默认：只导 fulltext.md，.md 后缀
python how_to_rag/export_corpus.py --archive Archive --out corpus_flat

# 导出全部三种文本（fulltext + card + review）
python how_to_rag/export_corpus.py --archive Archive --out corpus_flat --doc-type all

# 为 paper-qa 导 .txt（见下）
python how_to_rag/export_corpus.py --archive Archive --out corpus_flat_txt \
    --doc-type fulltext --ext txt

# 只软链接、不复制（省磁盘，但 symlink 跨工具要小心）
python how_to_rag/export_corpus.py --archive Archive --out corpus_flat --mode symlink --dry-run
```

参数：`--archive`（默认 `Archive`）、`--out`（默认 `corpus_flat`）、`--doc-type fulltext|card|review|all`、`--ext md|txt`、`--mode copy|symlink`、`--force`、`--dry-run`。

脚本幂等：已存在的目标文件默认跳过，加 `--force` 覆盖。

## 各工具对语料的偏好

| 工具 | 建议喂 | 后缀 | 备注 |
|---|---|---|---|
| paper-qa | `fulltext` | **`.txt`** | ⚠️ `.md` 会走 code chunker（见 [04](./04-paper-qa.md)） |
| mcp-local-rag | `fulltext`（+ 可选 card/review） | `.md` | 目录递归，`sync` 增量 |
| anything-llm | `fulltext`（+ 可选 card/review） | `.md`/`.txt` | 原生支持 |
| ragflow | `fulltext`（+ 可选 card/review） | `.md` | 原生 Markdown，Naive/DeepDoc 解析 |
| dify | `fulltext`（+ 可选 card/review） | `.md` | MarkdownExtractor 原生 |

**主料永远是 `fulltext.md`（英文原文）**：检索干净、无翻译损耗、引用可对回原文。中文的 `paper-card.md` / `review.md` 是我们 LLM 精读的产物，适合作为**补充 scope**（让工具也能检索到中文观点），但不要让它稀释英文原文的信号——建议先只喂 fulltext 跑通，再按需加 card/review。

## 每周增量

`export_corpus.py` 幂等 + 跳过已存在文件，每周 monitor/backfill 跑完后重跑一次即可（只新增新论文的文件）。后续各工具的增量更新命令见各自文档「增量更新」一节。
