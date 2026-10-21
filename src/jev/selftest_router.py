import asyncio, json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    sp = StdioServerParameters(command=".venv/bin/python", args=["server.py"],
                               env={"JEV_API_KEY": open(".key").read().strip()}, cwd=".")
    async with stdio_client(sp) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()

            r1 = await s.call_tool("jev_route", {"task": "把这 40 张 OCR 病历的缺失字段列个优先级清单"})
            d = json.loads(r1.content[0].text)
            a = d.get("answers", {}).get("route", {})
            print("[jev_route 默认三档] ok=", d.get("ok"), "-> choice=", a.get("choice"),
                  "probs=", a.get("probabilities"))

            # 自定义候选：故意把其中一个描述写得很长，验证「偏向最长选项」这条偏置
            unbalanced = {"A": "简单做法",
                          "B": "稳妥做法：先 git tag 基线，再出 dry-run 映射表，"
                               "逐条 str.replace，最后复扫验证并 commit，"
                               "任何一步失败都能从 tag 回滚，不会影响其他步骤"}
            r2 = await s.call_tool("jev_route", {"task": "批量重命名 40 个病历 md", "options": unbalanced})
            d2 = json.loads(r2.content[0].text)
            a2 = d2.get("answers", {}).get("route", {})
            print("[选项长短不对齐]     -> choice=", a2.get("choice"), "probs=", a2.get("probabilities"),
                  "  (B 是写得最长的那个)")

            r3 = await s.call_tool("jev_front_door", {"task": "计算 383 个病例里已完成 EDC 录入的占比"})
            d3 = json.loads(r3.content[0].text)
            print("[jev_front_door]    ok=", d3.get("ok"), "->", json.dumps(
                d3.get("answers", {}), ensure_ascii=False)[:220])

asyncio.run(main())
