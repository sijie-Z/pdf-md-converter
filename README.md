# PDF → Markdown Skill Assignment

**技术栈**: Python 3.12 + PyMuPDF + pdfplumber

---

## 快速开始

```bash
pip install pymupdf pdfplumber
python convert_pdf.py sample_pdf_to_markdown_note.pdf
```

## 输出文件

| 文件 | 大小 | 说明 |
|------|------|------|
| `outputs/document.md` | 1.5 KB | Markdown 文档，含页码标记、表格、扫描页提示 |
| `outputs/blocks.json` | 6.4 KB | 结构化中间结果，12 个 block，每个含 bbox 溯源信息 |
| `outputs/qa_report.md` | 2.0 KB | 自动生成的解析质量报告 + 人工复核清单 |

## 实际用时

| 阶段 | 用时 |
|------|------|
| PDF 分析 | 10 min |
| 编码 + Debug | 40 min |
| 输出验证 | 10 min |
| Skill/SOP 文档 | 25 min |
| README | 15 min |
| **总计** | **~1.5 h**（含前期思考约 2 h） |

## AI 使用情况

| 内容 | Claude 做的事 | 人工复核 |
|------|-------------|---------|
| convert_pdf.py | 生成 90% 代码 | 逻辑、分类规则、错误处理 |
| blocks.json 结构 | 设计 | bbox + source 字段确认 |
| QA 报告格式 | 生成 | 问题和复核项已核对 |
| Skill 文档 | 生成 95% | 确认不是 Prompt，而是结构化 SOP |
| README | 生成 90% | 时间记录、AI 使用描述已核实 |

**人工发现的关键 Bug**：Claude 初版使用 `page.get_text("dict")` 提取文本，但 PyMuPDF 的 dict 模式下 `block["text"]` 为空，文本实际嵌套在 `block["lines"][]["spans"][]` 中。若不修复，document.md 会缺失所有标题和正文。

---

## 项目结构

```
pdf-md-skill-assignment/
├── README.md
├── convert_pdf.py                    # PDF → Markdown + blocks + QA report
├── sample_pdf_to_markdown_note.pdf   # 3 页：文本、表格、扫描页
├── outputs/
│   ├── document.md                   # 页码标记、标题、表格、扫描页提示
│   ├── blocks.json                   # 12 个结构化 block，含 source locator
│   └── qa_report.md                  # 解析质量评估 + 复核清单
└── skills/
    └── pdf_to_markdown_review_skill.md  # 可复用 SOP（10 个章节）
```

---

## 输出文件说明

### `outputs/document.md`

- 页码标记：每页 `<!-- page: N -->`
- 标题：`## 附注36 租赁负债`
- 表格：GitHub Flavored Markdown `| 列 | 列 |`
- 表格标题：`**表36-1 租赁负债到期分析**`
- 脚注：`_注：金额单位为百万元..._`
- 扫描页：`> ⚠️ **Page 3 为图片/扫描页 — 需要 OCR**`
- 页眉/页码：自动过滤

### `outputs/blocks.json`

每个 block 包含：
- `page`、`block_id`、`type`（heading / paragraph / table_caption / footnote / table / image_page）
- `source.bbox`（x0, y0, x1, y1）用于追溯到原始 PDF
- 表格：`header`、`rows`、`row_count`、`col_count`
- 图片页：`needs_ocr: true`

### `outputs/qa_report.md`

- 摘要统计表（页数、标题数、表格数、问题数）
- 逐页解析情况
- 问题清单（严重级别：error / warning）
- 人工复核清单（扫描页、合计数值、表格结构、来源追溯）
- 优化建议

---

## 实际用时

| 阶段 | 用时 | 说明 |
|------|------|------|
| PDF 结构分析 | 10 min | 使用 Claude Code 分析 PDF 页数、文本/表格/图片分布 |
| 初始代码编写 | 25 min | 核心 convert_pdf.py |
| Debug 与修复 | 15 min | 修复 PyMuPDF dict 模式的 text 提取 bug |
| 输出验证 | 10 min | 检查 document.md, blocks.json, qa_report.md |
| Skill 文档 | 25 min | 编写 pdf_to_markdown_review_skill.md |
| README | 15 min | 编写本文档 + AI 使用说明 |
| **总计** | **~1.5 h** | 加上前期分析和思考总计约 2 小时 |

---

## AI 使用说明

### 使用的 AI 工具

| 工具 | 用途 |
|------|------|
| **Claude Code** | 分析 PDF 结构、编写 convert_pdf.py、生成 Skill 文档、撰写 README、分析 bug |
| **Claude (Web)** | 架构建议和技术方案确认（非强制） |

### 每个环节的 AI 参与程度

| 环节 | AI 完成度 | 人工复核内容 |
|------|----------|-------------|
| PDF 结构分析 | 100% (Claude) | 人工确认页数、类型判断是否正确 |
| 架构设计 | 80% (Claude 建议 + 人工判断) | 确定使用 PyMuPDF + pdfplumber |
| convert_pdf.py 编写 | 90% (Claude 生成) | **重点复核**: 逻辑流程、分类规则、错误处理 |
| 第一次运行 bug 修复 | 50% (Claude 发现 + 人工指导) | Claude 发现 blocks.json 缺失 text blocks；人工指示检查 PyMuPDF 的 dict 模式结构 |
| 分类规则调整 | 70% (Claude 调整 + 人工确认) | 人工确认 table_caption 和 footnote 分类顺序 |
| Skill 文档 | 95% (Claude 生成) | **重点复核**: 内容是否太像 Prompt 而非 SOP |
| README | 90% (Claude 生成) | 人工确认时间记录、AI 使用说明的真实性 |
| 输出质量检查 | 50% (Claude 分析 + 人工确认) | 人工交叉验证 document.md 的页码、表格、扫描页标记 |

### 如何避免盲信 AI 输出

1. **代码层面**: 每段由 AI 生成的逻辑，人工都读了代码并理解其原理
2. **数据层面**: 生成的 outputs/ 文件人工逐页对照 PDF 验证
3. **分类层面**: blocks.json 中每个 block 的 type 字段都检查过
4. **数值层面**: 表格的合计一致性检查逻辑由人工确认不会误报
5. **文档层面**: Skill 文档人工通读，确认它不是一段 Prompt 而是一个可执行的 SOP

### 最关键的复核发现

在第一次运行时，Claude 生成的代码没有正确提取文本 block（PyMuPDF 的 dict 模式下 `block["text"]` 为空，需要从 `block["lines"][]["spans"][]` 中逐级读取）。如果不复核输出，会得到一个只有表格没有正文的 `document.md`。

---

## 已完成与未完成

### 已完成

- PDF 文本页的标题、正文、脚注提取
- 表格提取（pdfplumber）并输出为 Markdown 表格
- 图片/扫描页检测并标记（`needs_ocr: true`）
- 页码标记保留（`<!-- page: N -->`）
- 结构化 blocks.json（含 bbox source locator，12 blocks）
- 合计数一致性自动检查
- 自动生成 QA 报告（含问题清单 + 人工复核清单）
- 可复用 Skill / SOP 文档
- AI 使用说明 + Git 协作规范

### 未完成

| 未完成项 | 原因 | 如何补上 |
|---------|------|---------|
| OCR 扫描页 | 本地未安装 Tesseract / PaddleOCR | 安装 PaddleOCR 后接入；当前标记 `needs_ocr: true` |
| 跨页表格拼接 | 本次 PDF 只有 3 页，无跨页表格 | 通过相同 `table_id` 检测，手动确认是否需要拼接 |
| 复杂表格（合并单元格等） | 题目 PDF 结构简单 | pdfplumber 对合并单元格支持有限，需人工标注 |
| 版面分析（多栏布局） | 本次 PDF 版面固定 | 如需处理多栏 PDF，接入 LayoutParser |
| 批量处理 | 只要求单文件 | 加 `--batch` 参数遍历目录 |

### 最大风险

| 风险 | 缓解措施 |
|------|---------|
| 分类规则基于 font_size 阈值，对字体敏感的 PDF 可能误判 | blocks.json 保留 max_font_size，可事后调整 |
| 表格提取依赖 pdfplumber 默认参数 | QA 报告标记 extraction_error |
| 扫描页 OCR 缺失 | 标记 `needs_ocr: true`，在 QA 报告和 README 中提示 |
| 水印文字可能混入正文 | 当前无检测逻辑 |

---

## 优先优化项（如果多给半天）

### 第 1 优先级（2 小时）

1. **接入 OCR**（PaddleOCR 轻量版） — 扫描页自动 OCR，置信度 < 0.8 的标记
2. **增强表格提取** — 跨页表格拼接、`--table_strategy` 参数

### 第 2 优先级（1 小时）

3. **Bad Case 库** — `bad_cases/` 目录 + 自动化回归测试
4. **数值格式增强** — 保留千分位逗号、括号负数、单位自动检测

### 第 3 优先级（1 小时）

5. **批量处理 + 并行** — `--batch` 模式，`concurrent.futures`
6. **版本号管理** — `__version__` + `--version`

---

## Git 协作规范

### 分支策略

```
main                  # 稳定版本
└── develop           # 日常开发
    ├── feature/pdf-parser
    ├── feature/ocr-integration
    ├── feature/skill-doc
    ├── fix/table-column-misalign
    └── refactor/block-model
```

### AI 修改工作流

```
1. 从 develop 创建 feature 分支
2. AI 在 feature 分支上修改代码
3. 人工 review git diff
   git diff develop --name-only   # 看改了哪些文件
   git diff develop --            # 逐行审查变更
4. 确认：没有不当删除 / 不必要依赖 / 配置变更
5. 跑一遍验证：python convert_pdf.py test.pdf
6. 审查 outputs/ 是否正常
7. 提交 → PR → Approve → merge to develop
```

### Review Checklist（AI 修改场景）

- [ ] 代码是否能运行？
- [ ] 输出文件是否完整？
- [ ] 新逻辑分支是否有对应的错误处理？
- [ ] AI 注释是否准确？有没有 hallucinate 的 API？
- [ ] 是否有硬编码路径或密钥泄露？
- [ ] 是否修改了本不应修改的文件？

---

## 示例输出预览

### document.md 节选

```markdown
<!-- page: 1 -->

## 附注36 租赁负债

以下数据用于测试 PDF 转 Markdown、表格抽取、页码来源保留和 GT 候选审核。

**表36-1 租赁负债到期分析**

<!-- t1 -->
| 项目 | 2026-06-30 | 2025-12-31 |
| --- | --- | --- |
| 一年以内 | 120.50 | 110.25 |
| 一至两年 | 88.00 | 91.00 |
| 两至五年 | 160.75 | 149.30 |
| 合计 | 369.25 | 350.55 |

_注：金额单位为百万元；合计数应等于各明细项目之和。_
```

### QA Report 节选

```markdown
| Metric | Value |
|--------|-------|
| Total pages | 3 | Text pages | 2 | Image pages | 1 |
| Tables extracted | 2 | Issues (error) | 0 | Issues (warning) | 1 |

### 🟡 Page 3: image_page_no_ocr
- **Severity**: warning
- **Detail**: Page detected as image-only; no OCR applied.
```
