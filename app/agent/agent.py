"""FlightInsight agent: an LLM that answers with two tools, route delay statistics and ASRS
safety report search.

    agent = build_agent("gemini")          # or "ollama"
    answer = ask(agent, "How on time is ATL to ORD, and do pilots report delay pressure?")
    answer.text, answer.tool_calls, answer.seconds
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool, tool

from app.tools.route_stats import get_route_delay_stats
from app.tools.safety_search import search_safety_reports

NARRATIVE_CHARS = 1200  # per report sent to the LLM; full narratives can be ~12,000 chars
RECURSION_LIMIT = 12  # LangGraph steps per question (each tool round trip is 2)

SYSTEM_PROMPT = """\
You are FlightInsight AI. You answer questions about US flight delays and aviation safety
using two tools. Data currently loaded:
- get_route_delay_stats: BTS on-time statistics per route and month. Only January 2024
  (month 202401) is loaded, for flights between the 30 busiest US airports.
- search_safety_reports: NASA ASRS voluntary safety reports, January to March 2024
  (202401-202403). Most reports have their airport removed for privacy, so the airport_code
  filter matches few reports. If a filtered search returns fewer than 3 reports, search again
  without airport_code and say that the results are not specific to that airport.

Rules:
- Use the tools for every number and every report you mention. Never invent statistics.
- Cite safety reports by their ACN, for example "ACN 2087654".
- Show rates as percentages and delays in minutes.
- If the tools return no data, say what data is loaded instead of guessing.
- ASRS reports are voluntary and not a statistical sample: describe themes and examples,
  do not claim that they explain or cause the delay numbers.
- Reply in the same language as the user's latest question (English if unsure), even when
  the reports or tool results are in another language. Be concise.
"""


@dataclass
class ToolCall:
    name: str
    args: dict
    output: str = ""


@dataclass
class Answer:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    seconds: float = 0.0
    model: str = ""  # model that wrote the answer (may be a fallback)
    messages: list[BaseMessage] = field(default_factory=list)  # whole conversation so far


def build_tools(
    search: Callable[..., list[dict]] = search_safety_reports,
    route_stats: Callable[..., list[dict]] = get_route_delay_stats,
) -> list[BaseTool]:
    """The agent's tools. Errors are returned as text so the LLM can fix its arguments."""

    @tool("search_safety_reports", parse_docstring=True)
    def search_tool(
        query: str,
        top_k: int = 5,
        month_key: int | None = None,
        start_month: int | None = None,
        end_month: int | None = None,
        airport_code: str | None = None,
        aircraft_family: str | None = None,
    ) -> str:
        """Semantic search over NASA ASRS safety reports written by pilots, controllers and crew.

        Args:
            query: What to look for, as a full sentence, e.g. "crew felt rushed because of delays".
            top_k: Number of reports to return, 1 to 20.
            month_key: Only this month, yyyymm, e.g. 202403.
            start_month: First month of a range, yyyymm.
            end_month: Last month of a range, yyyymm.
            airport_code: 3-letter airport code, e.g. ORD. Most reports have no airport.
            aircraft_family: B737, A320, CRJ, ERJ, DHC8 or MD80.
        """
        filters = {
            "month_key": month_key,
            "start_month": start_month,
            "end_month": end_month,
            "airport_code": airport_code,
            "aircraft_family": aircraft_family,
        }
        return run(lambda: [shorten(r) for r in search(query, filters, top_k)])

    @tool("get_route_delay_stats", parse_docstring=True)
    def route_tool(origin: str, dest: str, start_month: int, end_month: int | None = None) -> str:
        """On-time statistics for one route, one result per month, overall and per airline.

        Args:
            origin: Departure airport, 3-letter code, e.g. ATL.
            dest: Arrival airport, 3-letter code, e.g. ORD.
            start_month: First month, yyyymm, e.g. 202401.
            end_month: Last month, yyyymm. Defaults to start_month.
        """
        return run(lambda: route_stats(origin, dest, start_month, end_month))

    return [search_tool, route_tool]


def run(call: Callable[[], list[dict]]) -> str:
    try:
        results = call()
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:  # Cosmos or Ollama unreachable: tell the user instead of crashing
        return f"Error: the data service failed ({type(e).__name__}: {e})"
    if not results:
        return "No results."
    return json.dumps(results, ensure_ascii=False, default=str)


def shorten(report: dict) -> dict:
    report = dict(report)
    narrative = report.get("narrative") or ""
    if len(narrative) > NARRATIVE_CHARS:
        report["narrative"] = narrative[:NARRATIVE_CHARS] + " [...]"
    if isinstance(report.get("similarity"), float):
        report["similarity"] = round(report["similarity"], 3)
    return report


def build_agent(provider: str = "gemini", model: str | None = None, *, llm=None, tools=None):
    """A LangGraph agent. Pass llm/tools to use your own (tests use fakes).

    For Gemini, lighter models take over when the main one fails (see llm.fallback_llms);
    Answer.model says which one answered."""
    from langchain.agents import create_agent
    from langchain.agents.middleware import ModelFallbackMiddleware

    middleware = []
    if llm is None:
        from app.agent.llm import fallback_llms, make_llm

        llm = make_llm(provider, model)
        if fallbacks := fallback_llms(provider, model):
            middleware.append(ModelFallbackMiddleware(*fallbacks))
    return create_agent(
        llm, tools or build_tools(), system_prompt=SYSTEM_PROMPT, middleware=middleware
    )


def ask(agent, question: str, history: Sequence[BaseMessage] = ()) -> Answer:
    """Ask one question, with earlier messages of the conversation as context."""
    from langgraph.errors import GraphRecursionError

    start = time.perf_counter()
    messages = [*history, HumanMessage(question)]
    try:
        result = agent.invoke({"messages": messages}, {"recursion_limit": RECURSION_LIMIT})
    except GraphRecursionError:
        text = "Stopped: the model kept calling tools without answering. Try rephrasing."
        return Answer(text, seconds=time.perf_counter() - start, messages=messages)

    new = result["messages"][len(messages) :]
    calls: dict[str, ToolCall] = {}
    for message in new:
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                calls[call["id"] or str(len(calls))] = ToolCall(call["name"], call["args"])
        elif isinstance(message, ToolMessage) and message.tool_call_id in calls:
            calls[message.tool_call_id].output = str(message.content)
    final = next((m for m in reversed(new) if isinstance(m, AIMessage)), None)
    return Answer(
        text=final.text if final else "",
        tool_calls=list(calls.values()),
        seconds=time.perf_counter() - start,
        model=final.response_metadata.get("model_name", "") if final else "",
        messages=list(result["messages"]),
    )
