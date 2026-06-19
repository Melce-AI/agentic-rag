"""A minimal real agent: an LLM that answers questions over the database by
calling the Sentinel MCP tools itself.

Unlike ``dev_client.py`` (which calls tools with hard-coded arguments), here the
LLM decides which tool to call and writes the SQL. The control loop is:

    user question
      -> LLM sees the available MCP tools and picks one (e.g. list_tables)
      -> we execute it via MCP and feed the result back
      -> LLM picks the next tool, eventually writes a SELECT for sql_query
      -> LLM reads the rows and produces a final natural-language answer

The LLM can be a free Hugging Face Inference model (default — just needs a
token) or a local Ollama model. Both speak OpenAI-style tool calling; the
backend classes hide the small differences so the loop stays single.

Safety is unchanged: the model can only call the exposed tools, and the SQL
guard + read-only DB role still refuse any write.

Run it (needs Postgres up):
    HF_TOKEN=hf_xxx POSTGRES_HOST=localhost \
        uv run --no-sync python -m src.agents.sql_agent "your question"
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

# TODO (rerank optimization): when the agent retrieves knowledge it goes through
# the rag_search tool, which reranks candidates with a cross-encoder
# (src/rag/reranker.py + HybridRetriever._rerank in src/rag/retriever.py).
# Planned optimization of that rerank step — e.g. tuning the candidate count /
# rerank model, batching, or letting the agent tune rerank depth per query.

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from opentelemetry import trace

from src.core.config import get_settings
from src.observability.tracing import get_tracer, traced

_tracer = get_tracer(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "sql_agent_system.md"


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _openai_tools(mcp_tools) -> list[dict]:
    """MCP tool definitions -> OpenAI/HF/Ollama tool-calling schema."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": (tool.description or "").strip(),
                "parameters": tool.inputSchema or {"type": "object", "properties": {}},
            },
        }
        for tool in mcp_tools
    ]


def _parse_args(raw) -> dict:
    """Tool-call arguments arrive as a dict or a JSON string depending on backend."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        return json.loads(raw)
    return {}


class HuggingFaceBackend:
    """Free serverless Hugging Face Inference API (OpenAI-style tool calling)."""

    def __init__(self, settings) -> None:
        from huggingface_hub import AsyncInferenceClient

        token = settings.hf_token.get_secret_value() if settings.hf_token else None
        self._client = AsyncInferenceClient(model=settings.hf_model, token=token)
        self._model = settings.hf_model

    @property
    def model_name(self) -> str:
        return self._model

    async def chat(
        self, messages: list[dict], tools: list[dict]
    ) -> tuple[dict, list[dict]]:
        response = await self._client.chat_completion(
            messages=messages,
            tools=tools,
            tool_choice="auto",
            max_tokens=1024,
            temperature=0.0,
        )
        message = response.choices[0].message
        calls = []
        tool_calls_payload = []
        for tc in message.tool_calls or []:
            args = _parse_args(tc.function.arguments)
            calls.append({"id": tc.id, "name": tc.function.name, "args": args})
            # The router requires `arguments` to be a JSON string; the model
            # sometimes returns null for no-arg calls, which it then rejects (422).
            tool_calls_payload.append(
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": json.dumps(args, ensure_ascii=False),
                    },
                }
            )
        assistant = {
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": tool_calls_payload,
        }
        return assistant, calls

    @staticmethod
    def tool_message(call: dict, content: str) -> dict:
        return {"role": "tool", "tool_call_id": call["id"], "content": content}


class OllamaBackend:
    """Local Ollama model (also OpenAI-style tool calling)."""

    def __init__(self, settings) -> None:
        from ollama import AsyncClient

        self._client = AsyncClient(host=settings.ollama_host)
        self._model = settings.ollama_model

    @property
    def model_name(self) -> str:
        return self._model

    async def chat(
        self, messages: list[dict], tools: list[dict]
    ) -> tuple[dict, list[dict]]:
        response = await self._client.chat(
            model=self._model, messages=messages, tools=tools
        )
        message = response.message
        calls = [
            {
                "id": None,
                "name": tc.function.name,
                "args": _parse_args(tc.function.arguments),
            }
            for tc in (message.tool_calls or [])
        ]
        assistant = {
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": message.tool_calls or [],
        }
        return assistant, calls

    @staticmethod
    def tool_message(call: dict, content: str) -> dict:
        return {"role": "tool", "name": call["name"], "content": content}


def _make_backend(settings):
    if settings.llm_provider == "ollama":
        return OllamaBackend(settings)
    return HuggingFaceBackend(settings)


@traced("agent.run", span_kind="AGENT")
async def run_agent(question: str) -> dict:
    """Answer one question by letting the LLM drive the MCP tools.

    Returns a dict with the final ``answer`` and the ``steps`` the agent took
    (which tool it called, with what arguments, and the result) so callers — the
    CLI or the /agent/ask endpoint — can show the reasoning trail.

    The whole run is an OpenInference AGENT span; each LLM call is an LLM span
    and each tool call a TOOL span, so Phoenix renders the full reasoning tree.
    """
    settings = get_settings()
    backend = _make_backend(settings)

    log.info("Agent starting (model=%s): %s", backend.model_name, question[:120])

    agent_span = trace.get_current_span()
    agent_span.set_attribute("input.value", question)
    agent_span.set_attribute("llm.model_name", backend.model_name)

    # The agent is an MCP client: it launches the server as a subprocess and
    # talks to it over stdio. env is forwarded so POSTGRES_HOST reaches the
    # server (MCP sanitizes the env otherwise).
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.mcp_server.server"],
        env=dict(os.environ),
    )

    steps: list[dict] = []

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = _openai_tools((await session.list_tools()).tools)

            messages: list[dict] = [
                {"role": "system", "content": _load_system_prompt()},
                {"role": "user", "content": question},
            ]

            for _ in range(settings.agent_max_steps):
                with _tracer.start_as_current_span("llm.chat") as llm_span:
                    llm_span.set_attribute("openinference.span.kind", "LLM")
                    llm_span.set_attribute("llm.model_name", backend.model_name)
                    assistant, calls = await backend.chat(messages, tools)
                    llm_span.set_attribute("output.value", assistant["content"] or "")
                    llm_span.set_attribute("llm.tool_call_count", len(calls))
                messages.append(assistant)

                # No tool call => the model is done and `content` is the answer.
                if not calls:
                    answer = assistant["content"] or "(no answer)"
                    agent_span.set_attribute("output.value", answer)
                    log.info(
                        "Agent done in %d step(s): %s",
                        len(steps),
                        answer[:120],
                    )
                    return {"answer": answer, "steps": steps}

                for call in calls:
                    log.info(
                        "Tool call: %s(%s)",
                        call["name"],
                        json.dumps(call["args"], ensure_ascii=False)[:120],
                    )
                    with _tracer.start_as_current_span(
                        f"tool.{call['name']}"
                    ) as tool_span:
                        tool_span.set_attribute("openinference.span.kind", "TOOL")
                        tool_span.set_attribute("tool.name", call["name"])
                        tool_span.set_attribute(
                            "input.value", json.dumps(call["args"], ensure_ascii=False)
                        )
                        result = await session.call_tool(call["name"], call["args"])
                        # A tool result can be several content parts (e.g.
                        # list_tables returns one per table) — join them all.
                        text = "\n".join(
                            part.text
                            for part in (result.content or [])
                            if hasattr(part, "text")
                        )
                        tool_span.set_attribute("output.value", text[:1000])

                    steps.append(
                        {"tool": call["name"], "args": call["args"], "result": text}
                    )
                    messages.append(backend.tool_message(call, text))

            agent_span.set_attribute("output.value", "(max steps)")
            log.warning(
                "Agent stopped: reached max steps (%d)", settings.agent_max_steps
            )
            return {"answer": "(agent stopped: reached max steps)", "steps": steps}


def main() -> None:
    question = " ".join(sys.argv[1:]).strip() or "En çok ciro yapan 3 ürün hangisi?"
    print(f"Soru: {question}\n--- ajan çalışıyor ---")
    result = asyncio.run(run_agent(question))
    for step in result["steps"]:
        print(f"  -> {step['tool']}({json.dumps(step['args'], ensure_ascii=False)})")
    print(f"\n=== Cevap ===\n{result['answer']}")


if __name__ == "__main__":
    main()
