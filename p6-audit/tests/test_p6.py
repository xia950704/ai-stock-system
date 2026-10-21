# P6 回归测试（离线，不触发真实 JEV / 真实网络）。

import os
import sys
from pathlib import Path

WS = Path("/Users/xiashuang/AI-股票系统")
sys.path.insert(0, str(WS / "src"))

PASS = 0
FAIL = 0

def check(tid, desc, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"[PASS] {tid} {desc}")
    else:
        FAIL += 1
        print(f"[FAIL] {tid} {desc} | {detail}")

from engine import jev_adapter

def test_provider_config_defaults():
    cfg = jev_adapter.provider_config()
    # 当前 Workspace 通过 MCP Server 目录下的 .env 选择 AMD/Clef，
    # 这里只验证 provider_config() 能正确反映该配置，不重复断言硬编码的默认值。
    check("T-P6-01", "provider 与本地 .env 一致", cfg["provider"] == "amd", detail=str(cfg))
    check("T-P6-02", "base_url 指向 AMD decision API", cfg["base_url"] == "https://developer.amd.com.cn/radeon/api/v1", detail=str(cfg))
    check("T-P6-03", "model 与 .env 一致", cfg["model"] == "Clef", detail=str(cfg))
    check("T-P6-04", "timeout 为 60s", cfg["timeout_s"] == 60.0, detail=str(cfg))
    check("T-P6-05", "key_source 来自 mcp_env 或 file", cfg["key_source"] in ("mcp_env", "file"), detail=str(cfg))

def test_provider_config_env_override(monkeypatch_env=None):
    import importlib
    saved = {k: os.environ.get(k) for k in ("JEV_PROVIDER", "JEV_MODEL", "JEV_BASE_URL", "JEV_API_KEY")}
    try:
        os.environ["JEV_PROVIDER"] = "openrouter"
        os.environ["JEV_MODEL"] = "inception/mercury-decide:free"
        os.environ["JEV_BASE_URL"] = "https://openrouter.ai/api/v1"
        os.environ["JEV_API_KEY"] = "sk-test-123"
        importlib.reload(jev_adapter)
        cfg = jev_adapter.provider_config()
        check("T-P6-06", "env 覆盖 provider", cfg["provider"] == "openrouter")
        check("T-P6-07", "env 覆盖 model", cfg["model"] == "inception/mercury-decide:free")
        check("T-P6-08", "env 覆盖 base_url", cfg["base_url"] == "https://openrouter.ai/api/v1")
        check("T-P6-09", "env 覆盖后 key_source 为 env", cfg["key_source"] == "env")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        importlib.reload(jev_adapter)

def test_mock_call_unchanged():
    r = jev_adapter.jev_yes_no({"x": 1}, "1 < 2", use_mock=True,
                                mock_response={"ok": True, "model": "mock",
                                               "answers": {"answer": {"noul": 0.99}}})
    check("T-P6-10", "Mock 调用仍可用", r.get("ok") is True and r.get("answers"))
    req = r.get("request")
    check("T-P6-11", "Mock 请求含 model/state/questions", set(req.keys()) == {"model", "state", "questions"})
    check("T-P6-12", "Mock 请求含 instructions", req["questions"]["answer"].get("instructions") == "1 < 2")

def test_no_key_returns_no_key():
    saved = {k: os.environ.get(k) for k in ("JEV_API_KEY", "BYNARA_API_KEY")}
    saved_server_dir = os.environ.get("JEV_MCP_SERVER_DIR")
    saved_key_file = jev_adapter.KEY_FILE
    try:
        os.environ.pop("JEV_API_KEY", None)
        os.environ.pop("BYNARA_API_KEY", None)
        # 将 MCP Server 目录指向一个不存在的路径，从而禁用本地 .env / .key。
        os.environ["JEV_MCP_SERVER_DIR"] = "/nonexistent/p6-server"
        import importlib
        importlib.reload(jev_adapter)
        jev_adapter.KEY_FILE = "/nonexistent/p6-fake-key"
        r = jev_adapter.jev_yes_no({"x": 1}, "1 < 2", use_mock=False)
        check("T-P6-13", "无 key 时返回 no_key", r.get("ok") is False and r.get("error_code") == "no_key")
    finally:
        jev_adapter.KEY_FILE = saved_key_file
        if saved_server_dir is None:
            os.environ.pop("JEV_MCP_SERVER_DIR", None)
        else:
            os.environ["JEV_MCP_SERVER_DIR"] = saved_server_dir
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        importlib.reload(jev_adapter)

def test_failure_not_interpreted_as_signal():
    failed = {"ok": False, "error_code": "model_na", "error_message": "model not available"}
    check("T-P6-14", "失败 JEV 不可用", jev_adapter.is_available(failed) is False)
    check("T-P6-15", "失败状态可追溯", jev_adapter.failure_status(failed) == "model_na")

test_provider_config_defaults()
test_provider_config_env_override()
test_mock_call_unchanged()
test_no_key_returns_no_key()
test_failure_not_interpreted_as_signal()

from search import client as search_client

def test_env_dotenv_loaded():
    """T-P6-16: .env 中的 SEARCH_API_BASE_URL / SEARCH_API_KEY 被正确加载（不打印密钥）。"""
    cond = search_client.BASE_URL == "http://127.0.0.1:31415/v1/search" and bool(search_client.API_KEY)
    check("T-P6-16", ".env 配置已加载（密钥未打印）", cond,
          detail=f"BASE_URL={search_client.BASE_URL} key_set={bool(search_client.API_KEY)}")

def test_env_var_takes_precedence():
    """T-P6-17: 环境变量优先级高于 .env（已有 env 时 .env 不覆盖）。"""
    import os, importlib
    saved = os.environ.get("SEARCH_API_BASE_URL")
    try:
        os.environ["SEARCH_API_BASE_URL"] = "http://override.example/v1/search"
        importlib.reload(search_client)
        check("T-P6-17", "环境变量优先于 .env", search_client.BASE_URL == "http://override.example/v1/search")
    finally:
        if saved is None:
            os.environ.pop("SEARCH_API_BASE_URL", None)
        else:
            os.environ["SEARCH_API_BASE_URL"] = saved
        importlib.reload(search_client)

def test_no_key_when_missing():
    """T-P6-18: 环境变量与 .env 均无 key 时返回 no_key（不发起真实请求）。"""
    import os, importlib
    saved_url = os.environ.get("SEARCH_API_BASE_URL")
    saved_key = os.environ.get("SEARCH_API_KEY")
    import tempfile
    tmp = tempfile.NamedTemporaryFile("w", suffix=".env", delete=False)
    tmp.write("# empty config for test\n")
    tmp.close()
    try:
        os.environ.pop("SEARCH_API_KEY", None)
        os.environ["SEARCH_API_CONFIG_FILE"] = tmp.name
        importlib.reload(search_client)
        r = search_client.search("test", use_mock=False)
        check("T-P6-18", "无 key 时返回 no_key", r.get("ok") is False and r.get("error_code") == "no_key")
    finally:
        os.unlink(tmp.name)
        if saved_url is None:
            os.environ.pop("SEARCH_API_BASE_URL", None)
        else:
            os.environ["SEARCH_API_BASE_URL"] = saved_url
        if saved_key is None:
            os.environ.pop("SEARCH_API_KEY", None)
        else:
            os.environ["SEARCH_API_KEY"] = saved_key
        os.environ.pop("SEARCH_API_CONFIG_FILE", None)
        importlib.reload(search_client)

test_env_dotenv_loaded()
test_env_var_takes_precedence()
test_no_key_when_missing()

print(f"\n=== test_p6: {PASS} passed, {FAIL} failed ===")
sys.exit(1 if FAIL else 0)
