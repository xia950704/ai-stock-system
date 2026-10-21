#!/usr/bin/env python3
"""P4 Decision Model 注册表 (P4-3, 6.4)。

当前状态：空候选列表，等待用户填写。
Codex 不自动填充、不自动选择、不自动调用候选模型。
"""
import json
import os
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime

# 注册表路径
REGISTRY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "registry.json")

@dataclass
class DecisionModelSpec:
    """Decision Model 规格。"""
    model_id: str
    display_name: str
    provider: str
    base_url: str
    api_key_env: str  # 环境变量名（不含真实密钥）
    api_key_location: str  # 本地配置文件路径说明
    context_window: Optional[int] = None
    priority: int = 0  # 0=primary, 1+=fallback
    enabled: bool = False
    allowed_data_scope: str = ""  # 允许发送的数据范围
    restrictions: str = ""  # 调用限制
    notes: str = ""

@dataclass
class DecisionModelRegistry:
    """Decision Model 注册表。"""
    models: List[DecisionModelSpec] = field(default_factory=list)
    primary_model_id: Optional[str] = None
    last_updated: Optional[str] = None

    def add(self, spec: DecisionModelSpec) -> bool:
        """添加模型（用户调用）。"""
        if any(m.model_id == spec.model_id for m in self.models):
            return False  # 不覆盖
        self.models.append(spec)
        self.last_updated = datetime.now().isoformat()
        return True

    def get(self, model_id: str) -> Optional[DecisionModelSpec]:
        for m in self.models:
            if m.model_id == model_id:
                return m
        return None

    def list_enabled(self) -> List[DecisionModelSpec]:
        return [m for m in self.models if m.enabled]

    def set_primary(self, model_id: str) -> bool:
        if any(m.model_id == model_id for m in self.models):
            self.primary_model_id = model_id
            self.last_updated = datetime.now().isoformat()
            return True
        return False

    def clear(self) -> None:
        """清空（用户重置）。"""
        self.models = []
        self.primary_model_id = None
        self.last_updated = datetime.now().isoformat()

# ---- 持久化 ----
def save_registry(reg: DecisionModelRegistry) -> str:
    """保存到 registry.json。"""
    data = {
        "models": [asdict(m) for m in reg.models],
        "primary_model_id": reg.primary_model_id,
        "last_updated": reg.last_updated,
    }
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return REGISTRY_PATH

def load_registry() -> DecisionModelRegistry:
    """从 registry.json 加载。"""
    if not os.path.exists(REGISTRY_PATH):
        return DecisionModelRegistry()
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        data = json.load(f)
    reg = DecisionModelRegistry()
    reg.primary_model_id = data.get("primary_model_id")
    reg.last_updated = data.get("last_updated")
    for md in data.get("models", []):
        reg.models.append(DecisionModelSpec(**md))
    return reg

# ---- 对比测试框架 ----
def compare_outputs(output1: Dict, output2: Dict) -> Dict[str, Any]:
    """
    对比两个 DecisionOutput（用于一致性/回归测试）。
    返回差异摘要。
    """
    diffs = []
    # model_id
    if output1.get("model_id") != output2.get("model_id"):
        diffs.append({"field": "model_id", "v1": output1.get("model_id"), "v2": output2.get("model_id")})
    # market_verdict
    if output1.get("market_verdict") != output2.get("market_verdict"):
        diffs.append({"field": "market_verdict", "v1": output1.get("market_verdict"), "v2": output2.get("market_verdict")})
    # 每只股票
    stocks1 = {s.get("code"): s for s in output1.get("stocks", [])}
    stocks2 = {s.get("code"): s for s in output2.get("stocks", [])}
    for code in set(stocks1) | set(stocks2):
        s1 = stocks1.get(code, {})
        s2 = stocks2.get(code, {})
        if s1.get("action") != s2.get("action"):
            diffs.append({"field": f"{code}.action", "v1": s1.get("action"), "v2": s2.get("action")})
        if s1.get("confidence") != s2.get("confidence"):
            diffs.append({"field": f"{code}.confidence", "v1": s1.get("confidence"), "v2": s2.get("confidence")})
    return {
        "identical": len(diffs) == 0,
        "diff_count": len(diffs),
        "diffs": diffs,
    }

def check_contract_compliance(output: Dict, required_fields: set) -> List[str]:
    """检查输出是否包含所有必需字段。"""
    errors = []
    for f in required_fields:
        if f not in output:
            errors.append(f"缺少字段: {f}")
    return errors

