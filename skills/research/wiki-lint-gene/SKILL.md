---
name: wiki-lint-gene
category: research
description: Wiki全面健康评估 — Gene式。lint + 文件统计 + index覆盖率 + stub检测 + ingest状态，输出结构化报告。
---

# Wiki Health Assessment (Gene式)

## 🔬 GENE对象

### signals_match（触发信号）
```
死链|检查知识库|lint|健康检查|wiki检查|孤立页|知识库健康|wiki健康度|评估知识库
```

### strategy（执行步骤）
```
1. 运行诊断脚本：
   python3 ~/wiki/scripts/wiki-lint.py ~/wiki/

2. 文件统计（5个层）：
   entities=$(ls ~/wiki/entities/ | wc -l)
   concepts=$(ls ~/wiki/concepts/ | wc -l)
   comparisons=$(ls ~/wiki/comparisons/ | wc -l)
   queries=$(ls ~/wiki/queries/ | wc -l)
   raw_sources=$(find ~/wiki/raw/sources/ -name '*.md' | wc -l)
   summaries=$(ls ~/wiki/summaries/ 2>/dev/null | wc -l)

3. Index覆盖率检查（Python）：
   python3 -c "
   import re
   from pathlib import Path
   index = Path('~/wiki/index.md').read_text()
   indexed = set(re.findall(r'\[\[([^\]]+)\]\]', index))
   concept_files = {f.stem for f in Path('~/wiki/concepts').glob('*.md')}
   entity_files = {f.stem for f in Path('~/wiki/entities').glob('*.md')}
   print('Missing from index:', sorted((concept_files | entity_files) - indexed))
   "

4. Stub/垃圾文件检测：
   - 过小文件(<200字节)：wc -c 检查 entities/concepts/comparisons/
   - 测试残留：留意 concepts/yuenan.md 这类文件名撞衫但内容是stub的情况
   - 对比 entities/ 和 concepts/ 是否有同名slug

5. Ingest状态：
   python3 -c "import json; d=json.load(open('~/.hermes/wiki/.ingest-processed.json')); print(len(d['hashes']))"

6. 输出结构化报告：
   | 维度 | 状态 | 详情 |
   |------|------|------|
   | 死链 | ✅/❌ | N条 |
   | 孤立页 | ✅/❌ | N条 |
   | concepts收录率 | N/N | 百分比 |
   | stub文件 | ✅/❌ | 列表 |
   | ingest处理量 | N个 | vs raw/sources |
```

### AVOID（禁止行为）
```
禁止：
• 仅凭 wiki-lint.py 通过就宣称"知识库健康"（lint只检死链+孤立页）
• 不检查同名slug（entity和concept可以同名，需确认哪个是主版本）
• 忽略<200字节的小文件（通常是测试残留）
```

### constraints
```
只读操作为主
发现stub/testing文件时先确认再删除，不盲目删
输出格式：结构化表格
```

### validation
```
✓ lint 0死链/0孤立页
✓ concepts 100%收录于index.md
✓ 无<200字节的异常小文件
✓ entities和concepts无意外同名slug
✓ raw/sources ingest已全量处理
```
