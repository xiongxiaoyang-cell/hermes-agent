---
name: document-verify-gene
description: 文档完整性校验 — Word/Excel/PDF/PPT 读取后强制完整性摘要，关键文档必须OCR验证后才能分析
signals: 用户上传文档（.docx/.xlsx/.pptx/.pdf）时触发；任何文档读取后入库分析前必须执行
strategy: 读取后输出结构化完整性摘要 → 异常检测 → 触发对应格式的OCR验证流程
AVOID: 读取后不验证直接分析；关键文档跳过OCR；将"表格为空"直接判定为"原文缺失"
constraints: 所有文档必须经过完整性摘要；发现异常必须走docx-table-extraction-gene或ocr-and-documents验证
validation: 完整性摘要必须包含（页数/字数/段落数/表格数/图表数）; 异常项目逐项说明原因
---

# Document Verify — Gene式

## 核心理念

**单一读取方式 ≠ 内容完整**。任何文档读取后，必须输出结构化完整性摘要，人工或自动判断是否存在异常，只有通过验证的内容才能送分析。

## 信号识别

触发本流程的条件（满足任一）：
- 用户上传 .docx / .xlsx / .pptx / .pdf 文件
- 用户要求分析/入库某个文档
- 文档读取结果与预期页数/内容差异明显
- 用户反馈"内容不全"

## 完整性摘要格式

读取后必须输出以下结构（每个文档）：

```
=== [文件名] 完整性摘要 ===
格式: DOCX/PDF/PPTX/XLSX
文件大小: X KB
-----------------------------------
页数/总页数: 估算或已知
非空段落字数: XX
段落/文本块数: XX
表格数: X（异常: 空/与预期不符）
图片/图表数: X（异常: 缺失）
嵌入对象数: X（异常: 有/无）
-----------------------------------
- 异常项目:
  1. [异常项] → 原因 → 触发验证
  2. ...
-----------------------------------
结论: [通过 / 需OCR验证 / 人工确认]
```

## 异常判断规则

| 格式 | 异常信号 | 验证方式 |
|------|---------|---------|
| DOCX | 字数<预期50%或表格标记=0 | PDF→Tesseract OCR（见document-extraction-gene） |
| XLSX | 工作表数量与预期不符 | openpyxl逐表读取验证 |
| XLSX | 关键数据区域为空 | PDF→Tesseract OCR |
| PPTX | 幻灯片数量不符 | markitdown提取文本对比 |
| PDF | 扫描件/文字无法选中 | marker-pdf OCR |
| PDF | 文字内容与目录差异大 | marker-pdf 逐页验证 |

## Excel 专用校验（补充）

```python
import openpyxl
wb = openpyxl.load_workbook(path, data_only=True)
print(f"工作表数: {len(wb.sheetnames)}")
print(f"工作表: {wb.sheetnames}")
for name in wb.sheetnames:
    ws = wb[name]
    print(f"  [{name}]: {ws.max_row}行 x {ws.max_column}列")
    # 前5行内容样本
    for i, row in enumerate(ws.iter_rows(max_row=5, values_only=True)):
        if any(row):
            print(f"    行{i+1}: {row}")
```

## 工作流

```
文档上传/读取请求
  ↓
执行对应格式的标准读取（python-docx / openpyxl / pymupdf / markitdown）
  ↓
输出完整性摘要
  ↓
判断异常 → 触发对应验证（document-extraction-gene / ocr-and-documents）
  ↓
验证结果与原读取对比
  ↓
├─ 一致 → 送分析
└─ 不一致 → 以OCR/验证结果为准，注明原读取缺失内容
  ↓
人工确认（关键文档必须David确认后才入库）
```

## 关键原则

1. **不信任单一读取方式** — python-docx 读不了的表格就用 OCR
2. **不跳过摘要** — 每个文档必须有完整性摘要才能送分析
3. **异常不过夜** — 发现异常立即触发验证，不带着疑问入库
4. **人工确认** — 关键文档（涉及决策/分析的）必须David确认验证结果后才入库
