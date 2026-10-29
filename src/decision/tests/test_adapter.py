#!/usr/bin/env python3
"""src/decision 单元测试（离线，不触发真实 AMD API / 真实网络）。"""
import os
import sys
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.dirname(os.path.dirname(_HERE))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from decision import adapter


class TestEndpoints(unittest.TestCase):
    """_endpoints() 读取新旧 env 名的优先级与去重逻辑。"""

    def setUp(self):
        # 清理所有相关 env
        for k in ("AMD_API_BASE", "AMD_API_BASE_FALLBACKS", "AMD_FALLBACK_URLS", "AMD_API_KEY"):
            os.environ.pop(k, None)

    def tearDown(self):
        self.setUp()
        import importlib
        importlib.reload(adapter)

    def test_A_empty(self):
        """全空 → 只有默认主 endpoint"""
        import importlib
        importlib.reload(adapter)
        eps = adapter._endpoints()
        self.assertEqual(len(eps), 1)
        self.assertEqual(eps[0], "https://developer.amd.com.cn/radeon/api/v1")

    def test_B_new_name_only(self):
        """仅新名 AMD_API_BASE_FALLBACKS → 生效 3 个"""
        os.environ["AMD_API_BASE_FALLBACKS"] = "https://n1/v1,https://n2/v1"
        import importlib
        importlib.reload(adapter)
        eps = adapter._endpoints()
        self.assertEqual(len(eps), 3)
        self.assertEqual(eps[0], "https://developer.amd.com.cn/radeon/api/v1")
        self.assertIn("https://n1/v1", eps)
        self.assertIn("https://n2/v1", eps)

    def test_C_new_over_old(self):
        """新旧并存 → 新名优先，旧名被忽略"""
        os.environ["AMD_API_BASE_FALLBACKS"] = "https://n1/v1,https://n2/v1"
        os.environ["AMD_FALLBACK_URLS"] = "https://o1/v1"
        import importlib
        importlib.reload(adapter)
        eps = adapter._endpoints()
        self.assertEqual(len(eps), 3)
        self.assertNotIn("https://o1/v1", eps)
        self.assertIn("https://n1/v1", eps)

    def test_D_old_name_only(self):
        """仅旧名 AMD_FALLBACK_URLS → 兜底生效"""
        os.environ["AMD_FALLBACK_URLS"] = "https://o1/v1,https://o2/v1"
        import importlib
        importlib.reload(adapter)
        eps = adapter._endpoints()
        self.assertEqual(len(eps), 3)
        self.assertIn("https://o1/v1", eps)
        self.assertIn("https://o2/v1", eps)

    def test_E_dedupe(self):
        """去重：重复 URL 只保留首次出现"""
        os.environ["AMD_API_BASE_FALLBACKS"] = "https://x/v1,https://x/v1,https://y/v1"
        import importlib
        importlib.reload(adapter)
        eps = adapter._endpoints()
        # 主 + x + y = 3 个（x 只出现一次）
        self.assertEqual(len(eps), 3)


class TestIsAvailable(unittest.TestCase):
    """is_available() 空 key 早返回，不发请求。"""

    def setUp(self):
        for k in ("AMD_API_KEY", "AMD_API_BASE", "AMD_API_BASE_FALLBACKS", "AMD_FALLBACK_URLS"):
            os.environ.pop(k, None)

    def tearDown(self):
        self.setUp()
        import importlib
        importlib.reload(adapter)

    def test_no_key_early_return(self):
        """无 AMD_API_KEY → (False, 'missing AMD_API_KEY')，不发 HTTP"""
        import importlib
        importlib.reload(adapter)
        ok, msg = adapter.is_available()
        self.assertFalse(ok)
        self.assertEqual(msg, "missing AMD_API_KEY")

    def test_with_key_reaches_httpx(self):
        """有 key → 不早返回，走 httpx 路径（离线环境报 transport/网络错，但非 missing key）"""
        os.environ["AMD_API_KEY"] = "test-key"
        import importlib
        importlib.reload(adapter)
        ok, msg = adapter.is_available()
        self.assertFalse(ok)
        self.assertNotEqual(msg, "missing AMD_API_KEY")
        # 证明没有走早返回：报错来自 httpx 路径
        self.assertTrue(msg.startswith("transport error") or msg.startswith("HTTP"),
                        "expected httpx-path error, got: " + msg)


if __name__ == "__main__":
    unittest.main()


class TestCallAmdApiEarlyReturn(unittest.TestCase):
    """call_amd_api() 空 key 早返回，不发请求。"""

    def setUp(self):
        for k in ("AMD_API_KEY", "AMD_API_BASE", "AMD_API_BASE_FALLBACKS", "AMD_FALLBACK_URLS"):
            os.environ.pop(k, None)

    def tearDown(self):
        self.setUp()
        import importlib
        importlib.reload(adapter)

    @mock.patch("decision.adapter._call_amd_api_once")
    def test_empty_key_early_return_no_http(self, mock_once):
        """显式传空 key → 直接返回 (False, {}, "missing AMD_API_KEY")，底层未被调用"""
        import importlib
        importlib.reload(adapter)

        r = adapter.call_amd_api(
            system_prompt="test",
            user_prompt="test",
            model="Clef",
            api_key="",        # 空 key
            timeout_s=60,
        )
        ok, parsed, err = r
        self.assertFalse(ok)
        self.assertEqual(parsed, {})
        self.assertEqual(err, "missing AMD_API_KEY")
        mock_once.assert_not_called()

    @mock.patch("decision.adapter._call_amd_api_once")
    def test_missing_env_key_uses_default_early_return(self, mock_once):
        """环境变量未设 AMD_API_KEY → 默认值为空 → 同样早返回"""
        import importlib
        importlib.reload(adapter)

        r = adapter.call_amd_api(
            system_prompt="test",
            user_prompt="test",
            # 不传 api_key，走默认参数 AMD_API_KEY（模块常量，空字符串）
        )
        ok, parsed, err = r
        self.assertFalse(ok)
        self.assertEqual(parsed, {})
        self.assertEqual(err, "missing AMD_API_KEY")
        mock_once.assert_not_called()
