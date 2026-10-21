import asyncio, json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    sp = StdioServerParameters(
        command=".venv/bin/python",
        args=["server.py"],
        env={"JEV_API_KEY": open(".key").read().strip()},
        cwd=".",
    )
    async with stdio_client(sp) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            print("DISCOVERED:", [t.name for t in tools.tools])
            res = await s.call_tool("jev_route", {
                "task": "把这份10中心入组数据算出总完成率，判断是否达到60%门槛",
            })
            print("CALL jev_route ->", res.content[0].text[:300])
            res = await s.call_tool("jev_route", {
                "task": "为三期试验设计一份GCP合规审计SOP",
                "options": {
                    "outline": "先出章节框架与检查清单目录，确认后再写正文",
                    "full": "一次性写出完整SOP全文，含检查清单、抽样规则与流程图",
                    "skip": "不写SOP，直接口头答复",
                },
            })
            print("CALL jev_route(custom) ->", res.content[0].text[:300])
            res = await s.call_tool("jev_front_door", {
                "task": "判断药明康德在手订单597.7亿元是否超过600亿元门槛",
            })
            print("CALL jev_front_door(numeric) ->", res.content[0].text[:400])
            res = await s.call_tool("jev_front_door", {
                "task": "为三期试验写一份GCP合规审计SOP，含检查清单与偏离处理流程",
            })
            print("CALL jev_front_door(generate) ->", res.content[0].text[:500])

asyncio.run(main())
