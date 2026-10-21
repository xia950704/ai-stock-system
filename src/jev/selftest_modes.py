import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ST = {"age":68,"bp":"128/78","egfr":42,
      "exclusion":["eGFR<45","uncontrolled HTN","malignancy<5y"],"malignancy":"none"}
Q = "This patient meets an exclusion criterion and must be screened out."

async def main():
    sp = StdioServerParameters(command=".venv/bin/python", args=["server.py"],
                               env={"JEV_API_KEY": open(".key").read().strip()}, cwd=".")
    async with stdio_client(sp) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            print("DISCOVERED:", [t.name for t in (await s.list_tools()).tools])
            for mode in ("choice", "noul"):
                res = await s.call_tool("jev_yes_no", {"state": ST, "question": Q, "mode": mode})
                print(f"mode={mode:6}", res.content[0].text.replace("\n"," ")[:190])

asyncio.run(main())
