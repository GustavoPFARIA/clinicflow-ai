# MCP server

Source: [`app/mcp_server.py`](../app/mcp_server.py) · Tests: [`tests/test_mcp_server.py`](../tests/test_mcp_server.py)

ClinicFlow exposes its tools through the **[Model Context Protocol](https://modelcontextprotocol.io)**, the open standard for connecting AI applications to tools and data. Any MCP client (Claude Desktop, Claude Code, IDE agents or your own LLM app) can use the clinic's knowledge base, scheduling, payments and lab results **without any custom integration code**.

## What it exposes

The same 9 tools the WhatsApp agent uses, running the **exact same implementation**:

`search_knowledge_base` · `list_available_slots` · `book_appointment` · `get_my_appointments` · `reschedule_appointment` · `cancel_appointment` · `create_payment_link` · `get_exam_results` · `escalate_to_human`

Each tool returns structured JSON (MCP `structuredContent`). Recoverable problems, such as a taken slot or an unknown appointment, come back as MCP tool errors with a clear message.

## Security model

The server is bound to **one patient**, chosen by whoever launches it through `CLINICFLOW_MCP_PHONE`. It is never chosen by the model. That is the same rule the WhatsApp agent follows ([ADR-0002](adr/0002-tool-authorization-in-code.md)): an MCP client asking to cancel another patient's appointment gets `not found`, and a test proves it.

## Run it

**Step 1.** Start the app once so the database is created and seeded:

```bash
uvicorn app.main:app
```

**Step 2.** Run the MCP server over stdio for a demo patient:

```bash
CLINICFLOW_MCP_PHONE=+5562991110001 python -m app.mcp_server
```

→ The server waits for an MCP client on stdin/stdout.

## Connect Claude Desktop

Add this to `claude_desktop_config.json` (Settings → Developer → Edit Config), adjusting the paths:

```json
{
  "mcpServers": {
    "clinicflow": {
      "command": "C:/path/to/clinicflow-ai/.venv/Scripts/python.exe",
      "args": ["-m", "app.mcp_server"],
      "cwd": "C:/path/to/clinicflow-ai",
      "env": {
        "CLINICFLOW_MCP_PHONE": "+5562991110001",
        "DATABASE_URL": "sqlite:///C:/path/to/clinicflow-ai/clinicflow.db"
      }
    }
  }
}
```

On macOS/Linux, use `.venv/bin/python`.

→ Restart Claude Desktop. The **clinicflow** tools appear in the tools menu. Try: *"What does the clinic's insurance policy say, and do I have any appointments?"*

## Connect Claude Code

```bash
claude mcp add clinicflow --env CLINICFLOW_MCP_PHONE=+5562991110001 -- python -m app.mcp_server
```

Run it from the repository root, with the virtual environment active.

## Use it from Python

```python
import anyio
from mcp import Client, StdioServerParameters

async def main():
    server = StdioServerParameters(
        command="python", args=["-m", "app.mcp_server"],
        env={"CLINICFLOW_MCP_PHONE": "+5562991110001"},
    )
    async with Client(server) as client:
        result = await client.call_tool("search_knowledge_base", {"query": "Do you accept Unimed?"})
        print(result.structured_content["results"][0]["citation"])   # clinic#Health insurance

anyio.run(main)
```
