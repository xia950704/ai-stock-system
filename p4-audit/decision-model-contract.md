# P4-3 Decision Model 统一输入输出契约

> 生成时间：2026-10-20 18:57
> 模块：`src/decision/contract.py`

---

## 一、设计原则

1. **职责分离**：数据采集/校验/风控/模型/报告 独立
2. **模型不可绕过**：新鲜度门槛/权限/来源验证/风险约束在模型外层执行
3. **失败显式化**：模型失败返回错误结构，不伪装为中性/买入/卖出
4. **可追溯**：输入输出均带 provenance 字段

---

## 二、DecisionInput (送入模型)

```json
{
  "report_date": "YYYY-MM-DD",
  "market_context": {
    "verdict": "偏多|中性|偏空|无法判断",
    "confidence": "high|medium|low",
    "evidence": [...],
    "counter_evidence": [...],
    "scenarios": {...},
    "limitations": [...]
  },
  "stocks": [
    {
      "code": "sh600276",
      "name": "恒瑞医药",
      "price_layer": {...},
      "fund_layer": {...},
      "rd_layer": {...},
      "order_layer": {...},
      "jev_layer": {...},
      "search_layer": {...},
      "synthesis": {...},
      "action": {...}
    }
  ],
  "data_provenance": {
    "as_of": "2026-10-20",
    "kline": {"available": true},
    "anchor": {"available": true, "as_of": "2026-09-23"},
    "ranking": {"available": false},
    "realtime": {"available": true, "as_of": "2026-10-20"},
    "research": {"sh600276": {"available": true, "commit": "..."}},
    "search": {"available": true},
    "jev": {"available": false}
  },
  "freshness_gate": {
    "verdict": "FRESH|STALE|DATE_UNKNOWN",
    "blocking": true/false
  },
  "constraints": {
    "position_limits": {},
    "risk_budget": {}
  },
  "historical_judgments": [...],
  "model_config": {}
}
```

---

## 三、DecisionOutput (模型必须返回)

```json
{
  "model_id": "clef-flash",
  "model_version": "v1.0",
  "report_date": "2026-10-20",
  "generated_at": "2026-10-20T18:00:00+08:00",
  "market_verdict": "中性",
  "market_confidence": 0.65,
  "market_reasoning": "锚价池平均偏离 +12%，买卖信号均衡...",
  "stocks": [
    {
      "code": "sh600276",
      "name": "恒瑞医药",
      "action": "HOLD",
      "confidence": 0.72,
      "reasoning": "价格接近锚价，技术面中性",
      "supports": ["价格偏离 +1.8%", "技术评分 50"],
      "conflicts": ["锚价失效风险"],
      "gaps": ["无订单数据", "JEV 不可用"],
      "conditions": ["锚价有效", "无重大利空"],
      "invalidation": ["价格跌破锚价 -5%", "锚价失效"],
      "evidence_claims": [
        {
          "claim_id": "hsh600276-pe-20261020",
          "statement": "恒瑞医药 PE-TTM 约 36x",
          "status": "confirmed",
          "supporting_sources": [...],
          "refuting_sources": [],
          "independent_source_count": 2
        }
      ],
      "unknown_fields": ["order_book", "实际成交量"],
      "provenance": {
        "input_hash": "sha256:...",
        "data_sources": ["kline", "anchor_2026-09-23", "ranking_2026-10-20"]
      }
    }
  ],
  "overall_notes": ["整体风险偏好偏高", "建议关注百利天恒"],
  "trace": {
    "input_hash": "sha256:...",
    "model_latency_ms": 1250,
    "tokens_used": 3421
  }
}
```

---

## 四、字段规范

### 4.1 必需字段

| 字段 | 类型 | 说明 |
|------|------|------|
| model_id | string | 模型标识 (如 "clef-flash") |
| report_date | string | YYYY-MM-DD |
| generated_at | string | ISO datetime |
| stocks | array | 每只股票决策 |

### 4.2 StockDecision 必需字段

| 字段 | 类型 | 约束 |
|------|------|------|
| code | string | 标准代码 |
| name | string | 名称 |
| action | enum | 8种有效值 |
| confidence | float | 0-1 |
| reasoning | string | 核心推理 |
| supports | array<string> | 支持证据 |
| conflicts | array<string> | 冲突/反证 |
| gaps | array<string> | 信息缺口 |
| conditions | array<string> | 成立条件 |
| invalidation | array<string> | 失效条件 |
| evidence_claims | array<Claim> | 关键事实核验 |
| unknown_fields | array<string> | 明确标记未知 |
| provenance | object | 输入溯源 |

### 4.3 Claim 结构

| 字段 | 类型 | 说明 |
|------|------|------|
| claim_id | string | 唯一标识 |
| statement | string | 待核验事实 |
| status | enum | confirmed/refuted/single_source/unverified/conflicting |
| supporting_sources | array | 支持来源 |
| refuting_sources | array | 反驳来源 |
| independent_source_count | int | 独立来源数 |

---

## 五、校验规则

| 规则 | 行为 |
|------|------|
| 缺少 model_id | 拒绝 |
| action 不在 8 种有效值 | 拒绝 |
| confidence 不在 0-1 | 拒绝 |
| 缺少必需字段 | 拒绝 |
| evidence_claims 结构不完整 | 拒绝 |

---

## 六、错误处理

模型失败时返回：
```json
{
  "model_id": "clef-flash",
  "ok": false,
  "error": "timeout|auth|rate_limited|server_error|bad_request",
  "error_message": "...",
  "partial_results": [...]
}
```

**不得**：将失败转为中性/HOLD/任何确定性建议。
