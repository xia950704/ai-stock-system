"""
P4 多日历史回放模块 (P4-1)。

提供：
- provenance: 数据源日期溯源与反前视验证
- replay: 按交易日顺序逐日重放，严格防前视偏差
- evaluate: 研判质量评估指标
"""
from . import provenance, replay
# evaluate 后续加载
