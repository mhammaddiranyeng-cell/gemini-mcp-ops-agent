import asyncio, json, os, socket, sys
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import APIError
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

_orig = socket.getaddrinfo
socket.getaddrinfo = lambda *a, **kw: [r for r in _orig(*a, **kw) if r[0] == socket.AF_INET] or _orig(*a, **kw)
load_dotenv(override=True)

def _to_gemini_tool(mcp_tools: list) -> types.Tool:
    decls = [
        types.FunctionDeclaration(
            name=t.name,
            description=t.description or "",
            parameters_json_schema=t.inputSchema or {"type": "object", "properties": {}},
        )
        for t in mcp_tools
    ]
    return types.Tool(function_declarations=decls)
class AutonomousOpsAgent:
    def __init__(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY missing")
        self.client = genai.Client(api_key=api_key, http_options=types.HttpOptions(api_version="v1beta", timeout=45000))
        primary = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
        self.models = list(dict.fromkeys([primary, "gemini-2.5-flash", "gemini-3.1-flash-lite-preview"]))

    def _call(self, contents: list, config: types.GenerateContentConfig):
        last_err = None
        for m in self.models:
            try:
                return self.client.models.generate_content(model=m, contents=contents, config=config)
            except APIError as err:
                last_err = err
                if getattr(err, "code", None) in {404, 429, 500, 503, 504}:
                    continue
                raise
        raise RuntimeError(f"All models failed: {last_err}")
    async def run_triage(self, objective: str, max_turns: int = 6) -> dict:
        params = StdioServerParameters(command=sys.executable, args=["-m", "server.ops_mcp_server"], env=os.environ.copy())
        audit = []
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()
                pol = await session.read_resource("ops://policy/sla")
                policy_txt = "\n".join(c.text for c in pol.contents if hasattr(c, "text"))
                tools = await session.list_tools()
                cfg = types.GenerateContentConfig(
                    system_instruction=f"Follow these SLA rules strictly:\n{policy_txt}\nExecute tools and summarize actions.",
                    tools=[_to_gemini_tool(tools.tools)],
                    temperature=0.1,
                )
                contents = [objective]
                for turn in range(max_turns):
                    resp = self._call(contents, cfg)
                    cand = resp.candidates[0].content
                    contents.append(cand)
                    calls = [p.function_call for p in cand.parts if p.function_call]
                    if not calls:
                        return {"turns_used": turn + 1, "tool_executions": audit, "final_report": resp.text}
                    parts = []
                    for fc in calls:
                        args = dict(fc.args) if fc.args else {}
                        res = await session.call_tool(fc.name, arguments=args)
                        txt = "\n".join(c.text for c in res.content if hasattr(c, "text"))
                        audit.append({"turn": turn + 1, "tool": fc.name, "arguments": args, "output": json.loads(txt)})
                        parts.append(types.Part.from_function_response(name=fc.name, response={"result": txt}))
                    contents.append(types.Content(role="user", parts=parts))
        return {"turns_used": max_turns, "tool_executions": audit, "final_report": "Max turns reached"}
if __name__ == "__main__":
    out = asyncio.run(AutonomousOpsAgent().run_triage("Audit low-stock hardware, place compliant restock orders per SLA, and escalate any open HIGH-severity incidents."))
    print(json.dumps(out, indent=2))
if __name__ == "__main__":
    out = asyncio.run(AutonomousOpsAgent().run_triage("Audit low-stock hardware, place compliant restock orders per SLA, and escalate any open HIGH-severity incidents."))
    print(json.dumps(out, indent=2))
