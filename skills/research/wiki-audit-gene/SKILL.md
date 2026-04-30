---
name: wiki-audit-gene
category: research
description: Wiki审核修正 — Gene式。收集反馈→人工审核→执行→归档，三类决策（接受/拒绝/延期）。
---

# Wiki Audit (Gene式)

## 🔬 GENE对象

### signals_match（触发信号）
```
wiki内容有误|信息过时|第.*条错了|帮我修正|修正知识库
审核|audit|反馈|知识库修正
```

### strategy（执行步骤）
```
1. 接收反馈：用户描述错误/过时内容
2. 创建反馈文件 → wiki/audit/inbox/<timestamp>-<类型>.md
3. 运行审核：python3 ~/wiki/scripts/wiki-audit-review.py ~/wiki/ --open
4. 三类决策：
   a. accept → 执行修改 → 追加 AUDIT marker 到目标页面
   b. reject → 无操作 → 归档为已拒绝
   c. defer → 移入 inbox/deferred/ → 后续处理
5. 自动归档到 audit/resolved/
```

### constraints
```
不接受匿名反馈（需有 reporter）
不接受无具体页面的反馈
所有决策可追溯，不可删除 resolved/ 归档
```

### validation
```
✓ 反馈 → inbox 有文件
✓ inbox → resolved 归档完整
✓ accept 时目标页面有 AUDIT marker
```
