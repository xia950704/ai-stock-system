#!/usr/bin/env python3
"""src/monitor 单元测试（离线，不触发真实 JEV / 真实网络）。

运行：
    python3 src/monitor/tests/test_monitor.py

覆盖：
  - JEV 重试/退避（429 / bridge_error / 非重试错误）
  - error_code 归一化（http_status 429 -> rate_limit）
  - 动作映射（JEV 方向性优先、margin 阈值、价格分档兜底）
  - 交易时段守卫
"""
import os
import sys
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.dirname(os.path.dirname(_HERE))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from monitor import action_map, jev_questions, session_guard


def _ok(choice="no", yes=0.4, no=0.6):
    return {
        "ok": True,
        "model": "Clef",
        "answers": {
            "answer": {
                "type": "choice",
                "choice": choice,
                "confidence": abs(yes - no),
                "probabilities": {"yes": yes, "no": no},
            }
        },
    }


def _rate_limited():
    return {
        "ok": False,
        "http_status": 429,
        "detail": '{"error":{"code":"global_concurrency_rate_limit_exceeded"}}',
    }


class TestJevRetry(unittest.TestCase):
    """T-MR: JEV 重试与退避。"""

    def setUp(self):
        self.quote = {"code": "sh600276", "name": "恒瑞医药", "price": 46.0,
                      "anchor": 47, "deviation": -2.13, "status": "偏低估",
                      "change_pct": -2.91, "pe": 36.0}
        self.news = {"items": [{"title": "回购公告"}]}
        self.market = {"verdict": "中性", "summary": "四大指数普跌"}
        self.state = jev_questions.build_state(self.quote, self.news, self.market)

    def test_rate_limit_then_success(self):
        """T-MR01: 首次 429，重试后成功 -> 返回 ok 结果。"""
        with mock.patch.object(jev_questions.time, "sleep") as sleeper:
            with mock.patch.object(
                jev_questions.jev_adapter, "jev_yes_no",
                side_effect=[_rate_limited(), _ok()],
            ) as call:
                out = jev_questions.run_jev(
                    self.state, "entry", self.quote, self.news, self.market)
        self.assertTrue(out["ok"])
        self.assertEqual(out["answer"], "no")
        self.assertEqual(call.call_count, 2)
        # 退避 4s + 调用间隔 3s
        slept = [c.args[0] for c in sleeper.call_args_list]
        self.assertIn(4.0, slept)

    def test_exhausted_retries_returns_rate_limit(self):
        """T-MR02: 连续 429 直到耗尽重试 -> error_code=rate_limit（非 unknown）。"""
        with mock.patch.object(jev_questions.time, "sleep"):
            with mock.patch.object(
                jev_questions.jev_adapter, "jev_yes_no",
                return_value=_rate_limited(),
            ) as call:
                out = jev_questions.run_jev(
                    self.state, "entry", self.quote, self.news, self.market)
        self.assertFalse(out["ok"])
        self.assertEqual(out["error_code"], "rate_limit")
        self.assertEqual(call.call_count, jev_questions.JEV_MAX_RETRIES)

    def test_non_retryable_error_not_retried(self):
        """T-MR03: 不可重试错误（如 no_key）不重试，直接返回。"""
        err = {"ok": False, "error_code": "no_key", "error_message": "no key"}
        with mock.patch.object(jev_questions.time, "sleep"):
            with mock.patch.object(
                jev_questions.jev_adapter, "jev_yes_no", return_value=err
            ) as call:
                out = jev_questions.run_jev(
                    self.state, "entry", self.quote, self.news, self.market)
        self.assertFalse(out["ok"])
        self.assertEqual(out["error_code"], "no_key")
        self.assertEqual(call.call_count, 1)

    def test_bridge_error_is_retryable(self):
        """T-MR04: bridge_error 属瞬时错误，纳入重试。"""
        err = {"ok": False, "error_code": "bridge_error",
               "error_message": "ExceptionGroup: boom"}
        with mock.patch.object(jev_questions.time, "sleep"):
            with mock.patch.object(
                jev_questions.jev_adapter, "jev_yes_no",
                side_effect=[err, _ok(choice="yes", yes=0.8, no=0.2)],
            ) as call:
                out = jev_questions.run_jev(
                    self.state, "entry", self.quote, self.news, self.market)
        self.assertTrue(out["ok"])
        self.assertEqual(call.call_count, 2)

    def test_classify_429_without_error_code(self):
        """T-MR05: MCP bridge 透传的 429（无 error_code）归一化为 rate_limit。"""
        code = jev_questions._classify_result_error(_rate_limited())
        self.assertEqual(code, "rate_limit")

    def test_classify_preserves_existing_code(self):
        """T-MR06: 已有 error_code 时不被覆盖。"""
        code = jev_questions._classify_result_error(
            {"ok": False, "error_code": "timeout", "http_status": 429})
        self.assertEqual(code, "timeout")

    def test_mock_mode_skips_sleep(self):
        """T-MR07: mock 模式不做调用间隔（保持测试快速）。"""
        with mock.patch.object(jev_questions.time, "sleep") as sleeper:
            out = jev_questions.run_jev(
                self.state, "entry", self.quote, self.news, self.market,
                use_mock=True)
        self.assertTrue(out["ok"])
        sleeper.assert_not_called()


class TestActionMap(unittest.TestCase):
    """T-MA: JEV 结论 -> 动作映射。"""

    def test_high_margin_yes_triggers_entry(self):
        """T-MA01: entry=yes 且 margin 达标 -> CONSIDER_ENTRY。"""
        jev = {
            "entry": {"ok": True, "answer": "yes", "margin": 0.5,
                      "yes_prob": 0.75, "no_prob": 0.25},
            "add": {"ok": True, "answer": "no", "margin": 0.4},
            "reduce": {"ok": True, "answer": "no", "margin": 0.6},
        }
        quote = {"deviation": -2.0}
        out = action_map.map_action(jev, quote)
        self.assertEqual(out["action"], action_map.ACTION_ENTRY)
        self.assertEqual(out["basis"], "jev_entry")

    def test_low_margin_yes_falls_back_to_price_band(self):
        """T-MA02: entry=yes 但 margin 不足 -> 回落到价格分档。"""
        jev = {
            "entry": {"ok": True, "answer": "yes", "margin": 0.06,
                      "yes_prob": 0.53, "no_prob": 0.47},
            "add": {"ok": True, "answer": "no", "margin": 0.3},
            "reduce": {"ok": True, "answer": "no", "margin": 0.3},
        }
        quote = {"deviation": -2.54}
        out = action_map.map_action(jev, quote)
        self.assertEqual(out["action"], action_map.ACTION_WAIT)
        self.assertEqual(out["basis"], "price_band")
        self.assertIn("margin", out["reason"])

    def test_jev_unavailable_is_insufficient_not_neutral(self):
        """T-MA03: JEV 不可用 -> INSUFFICIENT_EVIDENCE，不静默降级为 HOLD。"""
        jev = {
            "entry": {"ok": False, "error_code": "rate_limit"},
            "add": {"ok": False, "error_code": "rate_limit"},
            "reduce": {"ok": False, "error_code": "rate_limit"},
        }
        quote = {"deviation": -15.09}
        out = action_map.map_action(jev, quote)
        self.assertEqual(out["action"], action_map.ACTION_INSUFFICIENT)
        self.assertEqual(out["basis"], "jev_unavailable")

    def test_price_band_entry(self):
        """T-MA04: 无方向性结论 + 偏离 <-5% -> CONSIDER_ENTRY。"""
        jev = {
            "entry": {"ok": True, "answer": "no", "margin": 0.3},
            "add": {"ok": True, "answer": "no", "margin": 0.3},
            "reduce": {"ok": True, "answer": "no", "margin": 0.3},
        }
        out = action_map.map_action(jev, {"deviation": -12.76})
        self.assertEqual(out["action"], action_map.ACTION_ENTRY)

    def test_no_anchor_is_insufficient(self):
        """T-MA05: 无锚价（ETF）-> INSUFFICIENT_EVIDENCE。"""
        jev = {
            "entry": {"ok": True, "answer": "no", "margin": 0.3},
            "add": {"ok": True, "answer": "no", "margin": 0.3},
            "reduce": {"ok": True, "answer": "no", "margin": 0.3},
        }
        out = action_map.map_action(jev, {"deviation": None})
        self.assertEqual(out["action"], action_map.ACTION_INSUFFICIENT)
        self.assertEqual(out["basis"], "no_anchor")

    def test_reduce_yes_above_anchor_is_exit(self):
        """T-MA06: reduce=yes 且偏离 >10% -> CONSIDER_EXIT。"""
        jev = {
            "entry": {"ok": True, "answer": "no", "margin": 0.3},
            "add": {"ok": True, "answer": "no", "margin": 0.3},
            "reduce": {"ok": True, "answer": "yes", "margin": 0.5,
                       "yes_prob": 0.75, "no_prob": 0.25},
        }
        out = action_map.map_action(jev, {"deviation": 12.0})
        self.assertEqual(out["action"], action_map.ACTION_EXIT)

    def test_reduce_yes_below_anchor_notes_conflict(self):
        """T-MA07: 低于锚价却出现减仓信号 -> 保留方向但标注分歧。"""
        jev = {
            "entry": {"ok": True, "answer": "no", "margin": 0.3},
            "add": {"ok": True, "answer": "no", "margin": 0.3},
            "reduce": {"ok": True, "answer": "yes", "margin": 0.5,
                       "yes_prob": 0.75, "no_prob": 0.25},
        }
        out = action_map.map_action(jev, {"deviation": -8.0})
        self.assertEqual(out["action"], action_map.ACTION_REDUCE)
        self.assertIn("分歧", out["reason"])


class TestSessionGuard(unittest.TestCase):
    """T-MS: 交易时段守卫。"""

    def test_mid_session_blocked(self):
        """T-MS01: 连续竞价时段内 -> 禁止运行。"""
        status = session_guard.session_status(_dt(2026, 10, 22, 10, 30))
        self.assertTrue(status["in_trading_session"])
        self.assertFalse(status["allow_run"])

    def test_after_close_allowed(self):
        """T-MS02: 收盘后 -> 允许运行。"""
        status = session_guard.session_status(_dt(2026, 10, 22, 15, 30))
        self.assertFalse(status["in_trading_session"])
        self.assertTrue(status["allow_run"])

    def test_lunch_break_allowed(self):
        """T-MS03: 午休非连续竞价 -> 允许运行。"""
        status = session_guard.session_status(_dt(2026, 10, 22, 12, 0))
        self.assertFalse(status["in_trading_session"])


def _dt(y, m, d, hh, mm):
    from datetime import datetime, timezone, timedelta
    return datetime(y, m, d, hh, mm,
                    tzinfo=timezone(timedelta(hours=8)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
