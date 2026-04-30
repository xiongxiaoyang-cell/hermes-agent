---
name: document-extraction-gene
description: 统一文档读取 — Word(docx)/Excel(xlsx)/PPT(pptx)/PDF，强制完整性自检，表格丢失自动OCR验证
signals: 用户上传或提到 docx/xlsx/pptx/pdf 文件，需要读取/分析/入库
strategy: markitdown统一入口 → 完整性自检 → 表格异常触发OCR验证
AVOID: 单独使用 python-docx/python-pptx（表格处理有已知bug）；trust空表格为"原文缺失"
constraints: 所有文档必须输出「页数/字数/表格数/图片数」摘要，确认完整后再分析
validation: 表格行数>0才结束，异常时强制OCR验证；关键文档读取后必须自检完整性
created: 2026-04-30
---

# Document Extraction — Gene式统一入口

## 核心原则

**所有格式一律先用 `markitdown`**（微软官方工具），不用 python-docx/python-pptx 直接读。
markitdown 对表格处理正确，python-docx 对 docx 表格有已知 bug（表格内容返回空）。

## 工具集

| 工具 | 安装 | 用途 |
|------|------|------|
| `markitdown[all]` | `pip install "markitdown[all]"` | docx/xlsx/pptx 统一入口 |
| pymupdf | `pip install pymupdf pymupdf4llm` | PDF 文本提取 |
| marker-pdf | `pip install marker-pdf` | OCR扫描件（~5GB） |
| tesseract | 系统安装 | OCR备选（中文需 chi_sim+eng） |

## Step 1 — 统一读取

```python
/usr/bin/python3 << 'EOF'
import markitdown, os, sys

path = sys.argv[1]
label = os.path.basename(path)

try:
    result = markitdown.MarkItDown().convert(path)
    text = result.text_content or result.markdown or ""
    title = getattr(result, 'title', '') or ""

    # 完整性自检
    lines = [l for l in text.splitlines() if l.strip()]
    table_markers = text.count("| --- |") + text.count("|----|----|")

    print(f"[{label}]")
    print(f"  字符数: {len(text)}")
    print(f"  非空行: {len(lines)}")
    print(f"  表格标记(估): {table_markers}")
    print(f"  标题: {title}")
    print()
    print("--- 内容预览（前800字）---")
    print(text[:800])
    if len(text) > 800:
        print(f"... [还有 {len(text)-800} 字]")
except Exception as e:
    print(f"ERROR: {e}")
EOF
```

**输出格式：**
```
[文件名.docx]
  字符数: 4531
  非空行: 87
  表格标记(估): 8
  标题: 出海人力资源智能体共创会议程设计

--- 内容预览（前800字）---
...
```

## Step 2 — 完整性自检

读取后必须回答三个问题：

1. **内容长度是否合理？** （例如8页文档应有2000+字）
2. **表格是否非空？** （表格标记>0，且表格区域有文字）
3. **与文中描述是否一致？** （文中提到"三类信息"但表格为空 → 触发OCR）

### 自检决策树

```
内容长度 < 预期 50%?
  → YES → 触发OCR验证
  → NO  → 检查表格
表格区域为空但文中有表格描述?
  → YES → 触发OCR验证
  → NO  → 通过，可以分析
```

## Step 3 — OCR验证（当Step2触发时）

**方法：LibreOffice转PDF → pdftoppm → Tesseract**

```bash
# 1. 转PDF
libreoffice --headless --convert-to pdf --outdir /tmp/ 输入文件.docx

# 2. PDF转图片
pdftoppm -r 200 -png 文件.pdf /tmp/page

# 3. OCR（中文需 chi_sim+eng）
for p in /tmp/page-*.png; do
    tesseract "$p" stdout -l chi_sim+eng --psm 6
done
```

**关键：Tesseract对中文需要预处理**
```bash
/usr/bin/python3 << 'PYEOF'
from PIL import Image, ImageEval

img = Image.open('page-1.png').convert('RGB')
img = img.resize((img.width*2, img.height*2), Image.LANCZOS)
img = img.convert('L')
img = ImageEval(lambda x: 255 if x > 140 else 0).image(img)
img.save('/tmp/ocr_prep.png')
PYEOF
tesseract /tmp/ocr_prep.png stdout -l chi_sim+eng --psm 6
```

## 格式特殊说明

### PDF

- **文本PDF**：pymupdf，即时快速
  ```bash
  python3 -c "import pymupdf; doc=pymupdf.open('f.pdf'); [print(p.get_text()) for p in doc]"
  ```
- **扫描件**：marker-pdf（需~5GB空间）
  ```bash
  marker_single scanned.pdf --output_dir ./out
  ```
- **远程URL**：web_extract 优先

### Excel（xlsx）

markitdown 通过 openpyxl 读取。**注意**：公式计算结果会被读出，公式本身不会。

### PowerPoint（pptx）

markitdown 保留幻灯片编号和备注（`<!-- Slide N -->` 和 `### Notes:`）。
读取后检查是否有 `<!-- Slide number:` 标记来确认页数。

## 已知Bug

| Bug | 影响 | 规避 |
|-----|------|------|
| python-docx 表格返回空 | docx分析错误 | 用 markitdown 或 OCR |
| markitdown stdin模式需安装额外依赖 | 不能`cat f.docx \| markitdown` | 用 python API 或 `markitdown f.docx` |
| marker-pdf 需要~5GB磁盘 | OCR功能受限 | 先用 `df -h` 检查磁盘空间 |

## 完整性检查清单

读取每个文档后，必须确认：

- [ ] 输出字符数 > 预期（8页文档>2000字）
- [ ] 表格区域有内容（非空行）
- [ ] 文中描述的要素全部出现（如"三类信息""Day2-3""往期反馈"等关键词）
- [ ] 幻灯片页数与预期一致（pptx）
- [ ] 自检通过后才能进入分析阶段
