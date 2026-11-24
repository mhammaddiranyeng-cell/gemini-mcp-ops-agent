import asyncio
import json
import os
import socket
import sys
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import APIError
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

_orig_getaddrinfo = socket.getaddrinfo


def _ipv4_only_getaddrinfo(*args, **kwargs):
    responses = _orig_getaddrinfo(*args, **kwargs)
    ipv4 = [r for r in responses if r[0] == socket.AF_INET]
    return ipv4 if ipv4 else responses


socket.getaddrinfo = _ipv4_only_getaddrinfo
load_dotenv(override=True)


def _mcp_schema_to_gemini_tool(mcp_tools: list) -> types.Tool:
    declarations: list[types.FunctionDeclaration] = []
    for tool in mcp_tools:
        schema = tool.inputSchema or {"type": "object", "properties": {}}
        declarations.append(
            types.FunctionDeclaration(
                name=tool.name,
                description=tool.description or "",
                parameters_json_schema=schema,
            )
        )
    return types.Tool(function_declarations=declarations)


class AutonomousOpsAgent:
    def __init__(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is missing in .env")
        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(api_version="v1beta", timeout=45000),
        )
        primary = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
        self.models = list(
            dict.fromkeys([primary, "gemini-2.5-flash", "gemini-3.1-flash-lite-preview"])
        )

    def _generate_with_failover(
        self, contents: list, config: types.GenerateContentConfig
    ) -> types.GenerateContentResponse:
        last_err: Exception | None = None
        for model_name in self.models:
            try:
                return self.client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )
            except APIError as err:
                last_err = err
                if getattr(err, "code", None) in {404, 429, 500, 503, 504}:
                    continue
                raise
        raise RuntimeError(f"All Gemini models failed: {last_err}")

    async def run_triage(self, objective: str, max_turns: int = 6) -> dict:
        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "server.ops_mcp_server"],
            env=os.environ.copy(),
        )

        audit_log: list[dict] = []

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                policy_res = await session.read_resource("ops://policy/sla")
                policy_text = "\n".join(
                    c.text for c in policy_res.contents if hasattr(c, "text")
                )

                tools_response = await session.list_tools()
                gemini_tool = _mcp_schema_to_gemini_tool(tools_response.tools)

                system_prompt = (
                    "You are an autonomous Site Reliability & Supply Chain Operations Agent.\n"
                    "Follow these mandatory SLA & procurement policies strictly:\n"
                    f"{policy_text}\n\n"
                    "Inspect current state using your MCP tools, execute required actions, "
                    "and return a concise executive summary of every action taken."
                )

                config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    tools=[gemini_tool],
                    temperature=0.1,
                )

                contents: list = [objective]

                for turn in range(max_turns):
                    response = self._generate_with_failover(contents=contents, config=config)
                    candidate_content = response.candidates[0].content
                    contents.append(candidate_content)

                    function_calls = [
                        part.function_call
                        for part in candidate_content.parts
                        if part.function_call is not None
                    ]

                    if not function_calls:
                        return {
                            "turns_used": turn + 1,
                            "tool_executions": audit_log,
                            "final_report": response.text,
                        }

                    tool_response_parts: list[types.Part] = []
                    for fc in function_calls:
                        args = dict(fc.args) if fc.args else {}
                        mcp_result = await session.call_tool(fc.name, arguments=args)
                        result_text = "\n".join(
                            c.text for c in mcp_result.content if hasattr(c, "text")
                        )
                        audit_log.append(
                            {
                                "turn": turn + 1,
                                "tool": fc.name,
                                "arguments": args,
                                "output": json.loads(result_text),
                            }
                        )
                        tool_response_parts.append(
                            types.Part.from_function_response(
                                name=fc.name,
                                response={"result": result_text},
                            )
                        )

                    contents.append(types.Content(role="user", parts=tool_response_parts))

        return {
            "turns_used": max_turns,
            "tool_executions": audit_log,
            "final_report": "Max reasoning turns reached.",
        }


if __name__ == "__main__":
    agent = AutonomousOpsAgent()
    report = asyncio.run(
        agent.run_triage(
            "Run a full operational audit: check low-stock hardware, submit compliant restock "
            "orders per SLA policy, and triage any open high-severity incidents."
        )
    )
    print(json.dumps(report, indent=2))
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
