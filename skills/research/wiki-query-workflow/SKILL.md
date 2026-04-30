---
name: wiki-query-workflow
category: research
description: 知识库查询工作流 — Gene式。回答前强制读 wiki，附来源。触发→查wiki→组织答案→注明来源。
---

# Wiki Query Workflow (Gene式)

> 涉及出海HR/政策/EOR/合规/国别等问题时，强制执行本流程。

---

## 🗺️ LLM Wiki 五大能力全景

| # | 能力 | 触发语境 | 产出 |
|---|------|---------|------|
| 1 | **ingest** | "把这个入库"、"归档到知识库" | raw/articles/ + wiki/summaries/ |
| 2 | **compile** | "整理知识库"、"梳理一下结构" | 重构 concepts/ + 重建 index.md |
| 3 | **query** | "查一下马来西亚用工政策" | 有据可查的回答 + 来源标注 |
| 4 | **lint** | "跑一下知识库检查"、"检查死链" | 诊断报告（死链/孤立页/索引缺失）|
| 5 | **audit** | "第X条过时了"、"帮我修正" | audit/resolved/ 归档 |

**一句话：用知识库相关的事，直接告诉我意图就行。**

---

## 🔬 GENE对象

### signals_match（触发信号）
```
出海|海外|德国|英国|越南|新加坡|合规|EOR|最低工资|社保|签证|
劳动法|薪酬|雇主|招聘|用工|人力资源|各国|
hr-policy|policy|daily|日报|国别|区域|
问：|请问|how to|what is|哪个国家|
```

### strategy（执行步骤）
```
1. 识别问题主题（国家/地区 or HR主题）
2. 判断是否命中知识库覆盖范围
3. 命中时：
   a. 搜索 wiki/entities/ 对应国别页（如越南→yuenan.md）
   b. 搜索 wiki/concepts/ 对应主题页（如EOR→eor-fuwu.md）
   c. 读完相关页面后再组织答案
4. 答案中关键数据必须引用页面：如"越南2026年最低工资上调7.2%（[[yuenan|越南政策时间线]]）"
5. 结尾强制附来源一行：来源：[[页面名]]
6. 知识库无覆盖时：明示"知识库暂无此信息，基于[信源]回答"
```

### AVOID（禁止行为）
```
禁止：
• 不查 wiki 直接凭记忆回答政策数据
• 引用数值但不注明来源
• 捏造知识库中没有的具体条款/数字
• 以"一般来说"/"通常"模糊处理具体政策数据
```

### constraints（执行约束）
```
必须读页面：entities/ + concepts/ + comparisons/
禁止臆测：数值/法规/日期必须有据可查
来源格式：[[wikilink|显示名]] 或 [[概念页]]
查不到时：明示知识库缺失，不虚构
```

---

## Wiki 现有覆盖（截至2026-04-24）

**Entities（22国）**：yingguo/英国, deguo/德国, faguo/法国, bolan/波兰, xiongyali/匈牙利, helan/荷兰, xibanya/西班牙, yidali/意大利, baxi/巴西, riben/日本, hanguo/韩国, yuenan/越南, xinjapo/新加坡, shate/沙特, ahlianda/阿联酋, taiguo/泰国, malaixiya/马来西亚, yindu/印度, yinni/印尼, feilvbin/菲律宾, jianada/加拿大, meiguo/美国

**Concepts（19页）**：hr-policy-daily, eor-fuwu, quyu-guihua, hegui-fengkong, hegui-sida-lingyu, chuhai-san-jieduan, zhongqi-chuhai, zhongxiao-chuhai, luodi-10bu, zhaopin, yongyou-payroll, yongyou-qianzheng, chuhai-hr-course, hegui-shengsi, zimeiti-yunying, zuzhi-jiagou, xinchou, redian-ku, shai-chai-pei

**Comparisons（4页）**：eor-fuwu对比, 出海阶段对比, 区域合规对比, 薪酬体系对比

## 关键路径
- wiki根目录：`~/wiki/`
- entities：`~/wiki/entities/{guojia}.md`
- concepts：`~/wiki/concepts/{topic}.md`
- comparisons：`~/wiki/comparisons/{name}.md`

## validation（验证命令）
```
✓ 回答涉及政策数据时，附了 [[wikilink]] 来源
✓ 数值/法规有据可查，不是臆测
✓ 知识库无覆盖时，主动说明
```
