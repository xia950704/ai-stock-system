#!/usr/bin/env python3
"""P4 Decision Model 统一输入输出契约 (P4-3)。

定义：
- DecisionInput: 送入模型的标准化输入
- DecisionOutput: 模型必须返回的标准化输出
- validate_output(): 校验输出是否符合契约
"""
import json
from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Any, Dict, List, Optional, Literal, Tuple
from enum import Enum

class ActionType(str, Enum):
    """行动类型（与现有引擎一致）。"""
    CONSIDER_ENTRY = "CONSIDER_ENTRY"
    CONSIDER_ADD = "CONSIDER_ADD"
    HOLD = "HOLD"
    WAIT = "WAIT"
    OBSERVE = "OBSERVE"
    CONSIDER_REDUCE = "CONSIDER_REDUCE"
    CONSIDER_EXIT = "CONSIDER_EXIT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

class EvidenceTier(int, Enum):
    """证据来源层级（与 search/evidence 一致）。"""
    OFFICIAL = 1      # 交易所/公司公告/监管文件
    REGULATORY = 2    # 监管机构/注册机构
    REPUTABLE_MEDIA = 3  # 有明确采编来源的财经媒体
    INDUSTRY_RESEARCH = 4  # 行业研究/券商研报
    SOCIAL_UNVERIFIED = 5  # 社交/论坛/未经证实消息

@dataclass
class EvidenceSource:
    """单个证据来源。"""
    url: str
    title: str
    snippet: str
    tier: int  # EvidenceTier
    publish_date: Optional[str] = None  # YYYY-MM-DD
    retrieved_at: Optional[str] = None  # ISO datetime
    domain: Optional[str] = None

@dataclass
class Claim:
    """被核验的事实/命题。"""
    claim_id: str
    statement: str
    status: Literal["confirmed", "refuted", "single_source", "unverified", "conflicting"]
    supporting_sources: List[EvidenceSource] = field(default_factory=list)
    refuting_sources: List[EvidenceSource] = field(default_factory=list)
    independent_source_count: int = 0
    notes: List[str] = field(default_factory=list)

@dataclass
class DecisionInput:
    """送入 Decision Model 的标准化输入。"""
    report_date: str  # YYYY-MM-DD
    market_context: Dict[str, Any]  # 大盘判断、情景、限制
    stocks: List[Dict[str, Any]]  # 每只股票的 price/fund/rd/order/jev/search layer
    data_provenance: Dict[str, Any]  # 各数据源可用性、as_of、局限
    freshness_gate: Dict[str, Any]  # 新鲜度门槛状态
    constraints: Dict[str, Any]  # 用户配置的风险约束、仓位上限等
    historical_judgments: Optional[List[Dict]] = None  # 历史研判（如可用）
    model_config: Dict[str, Any] = field(default_factory=dict)  # 模型专属参数

@dataclass
class StockDecision:
    """单只股票的决策输出。"""
    code: str
    name: str
    action: ActionType
    confidence: float  # 0-1，模型自评置信度
    reasoning: str  # 核心推理
    supports: List[str] = field(default_factory=list)  # 支持证据摘要
    conflicts: List[str] = field(default_factory=list)  # 冲突/反证
    gaps: List[str] = field(default_factory=list)  # 信息缺口
    conditions: List[str] = field(default_factory=list)  # 成立条件
    invalidation: List[str] = field(default_factory=list)  # 失效条件
    evidence_claims: List[Claim] = field(default_factory=list)  # 关键事实核验
    unknown_fields: List[str] = field(default_factory=list)  # 明确标记未知
    provenance: Dict[str, Any] = field(default_factory=dict)  # 输入溯源

@dataclass
class DecisionOutput:
    """Decision Model 必须返回的标准化输出。"""
    model_id: str  # 模型标识（如 "clef-flash", "mercury-decide"）
    model_version: Optional[str] = None
    report_date: str = ""  # YYYY-MM-DD
    generated_at: str = ""  # ISO datetime
    market_verdict: Optional[str] = None  # 偏多/中性/偏空/无法判断
    market_confidence: Optional[float] = None
    market_reasoning: Optional[str] = None
    stocks: List[StockDecision] = field(default_factory=list)
    overall_notes: List[str] = field(default_factory=list)
    trace: Dict[str, Any] = field(default_factory=dict)  # 输入输出追溯

# ---- 契约校验 ----
REQUIRED_STOCK_FIELDS = {
    "code", "name", "action", "confidence", "reasoning",
    "supports", "conflicts", "gaps", "conditions", "invalidation",
    "evidence_claims", "unknown_fields", "provenance",
}

VALID_ACTIONS = {a.value for a in ActionType}

def validate_decision_output(output: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    校验 DecisionOutput 是否符合契约。
    返回 (is_valid, errors)。
    """
    errors = []

    # 必须字段
    for f in ("model_id", "report_date", "generated_at", "stocks"):
        if f not in output:
            errors.append(f"缺少必需字段: {f}")

    if "stocks" not in output:
        return False, errors

    # 股票逐只校验
    for i, s in enumerate(output["stocks"]):
        if not isinstance(s, dict):
            errors.append(f"stocks[{i}] 必须为对象")
            continue
        # 必需字段
        missing = REQUIRED_STOCK_FIELDS - set(s.keys())
        if missing:
            errors.append(f"stocks[{i}] 缺少字段: {sorted(missing)}")
        # action 有效性
        action = s.get("action")
        if action not in VALID_ACTIONS:
            errors.append(f"stocks[{i}] action 无效: {action} (有效: {sorted(VALID_ACTIONS)})")
        # confidence 范围
        conf = s.get("confidence")
        if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
            errors.append(f"stocks[{i}] confidence 必须在 0-1: {conf}")
        # evidence_claims 结构
        claims = s.get("evidence_claims", [])
        if not isinstance(claims, list):
            errors.append(f"stocks[{i}] evidence_claims 必须为数组")
        else:
            for j, cl in enumerate(claims):
                if not isinstance(cl, dict):
                    errors.append(f"stocks[{i}].evidence_claims[{j}] 必须为对象")
                else:
                    for cf in ("claim_id", "statement", "status", "supporting_sources"):
                        if cf not in cl:
                            errors.append(f"stocks[{i}].evidence_claims[{j}] 缺少 {cf}")

    # 模型标识
    mid = output.get("model_id")
    if not mid or not isinstance(mid, str):
        errors.append("model_id 必须为非空字符串")

    return len(errors) == 0, errors

def validate_decision_input(input_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """校验 DecisionInput（轻量级）。"""
    errors = []
    for f in ("report_date", "market_context", "stocks", "data_provenance", "freshness_gate"):
        if f not in input_data:
            errors.append(f"缺少必需输入字段: {f}")
    return len(errors) == 0, errors

# ---- 序列化辅助 ----
def input_to_json(input_obj: DecisionInput) -> str:
    return json.dumps(asdict(input_obj), ensure_ascii=False, default=str)

def output_to_json(output_obj: DecisionOutput) -> str:
    return json.dumps(asdict(output_obj), ensure_ascii=False, default=str)

def json_to_input(json_str: str) -> DecisionInput:
    """反序列化（简化，实际需完整 dataclass 转换）。"""
    return json.loads(json_str)

def json_to_output(json_str: str) -> DecisionOutput:
    return json.loads(json_str)

