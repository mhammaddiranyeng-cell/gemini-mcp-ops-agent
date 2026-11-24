# Custom MCP Server & Gemini Autonomous Ops Agent

Autonomous operations agent built with the **Model Context Protocol (`mcp`)** SDK and **Google Gemini 3 Flash (`google-genai`)**. Connects to a `stdio` FastMCP server, reads SLA resources, discovers tool schemas dynamically, and enforces a `$1,000` spend guardrail.

## Quickstart

    git clone https://github.com/mhammaddiranyeng-cell/gemini-mcp-ops-agent.git
    cd gemini-mcp-ops-agent
    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env
    python -m agent.ops_agent
