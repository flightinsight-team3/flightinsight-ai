"""Agent wiring with fake tools and a scripted fake chat model. No network, no LLM."""

import json

import pytest

pytest.importorskip("langchain")  # requirements-app.txt; not installed in CI

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402

from app.agent import agent as agent_module  # noqa: E402
from app.agent.agent import NARRATIVE_CHARS, ask, build_agent, build_tools  # noqa: E402


class ScriptedModel(GenericFakeChatModel):
    """Replies with the scripted messages in order; tool binding is a no-op."""

    def bind_tools(self, tools, **kwargs):
        return self


def tools_with(search=None, route_stats=None):
    calls = []

    def fake_search(query, filters, top_k):
        calls.append(("search", query, filters, top_k))
        return search if search is not None else []

    def fake_route(origin, dest, start, end):
        calls.append(("route", origin, dest, start, end))
        if route_stats is ValueError:
            raise ValueError("origin must be a 3-letter IATA airport code")
        return route_stats or []

    return {t.name: t for t in build_tools(fake_search, fake_route)}, calls


def test_tool_names_match_the_python_tools():
    tools, _ = tools_with()
    assert set(tools) == {"search_safety_reports", "get_route_delay_stats"}


def test_search_tool_passes_filters_and_shortens_narratives():
    long_report = {"id": "1", "narrative": "x" * (NARRATIVE_CHARS + 50), "similarity": 0.912345}
    tools, calls = tools_with(search=[long_report])

    out = json.loads(
        tools["search_safety_reports"].invoke({"query": "rushed", "month_key": 202403})
    )

    assert calls[0][1:] == ("rushed", {"month_key": 202403, "start_month": None,
                                       "end_month": None, "airport_code": None,
                                       "aircraft_family": None}, 5)  # fmt: skip
    assert out[0]["narrative"].endswith(" [...]")
    assert len(out[0]["narrative"]) == NARRATIVE_CHARS + len(" [...]")
    assert out[0]["similarity"] == 0.912


def test_tool_errors_are_returned_as_text():
    tools, _ = tools_with(route_stats=ValueError)
    out = tools["get_route_delay_stats"].invoke({"origin": "x", "dest": "ORD", "start_month": 1})
    assert out.startswith("Error: origin must be")


def test_empty_result_says_no_results():
    tools, _ = tools_with()
    assert tools["search_safety_reports"].invoke({"query": "q"}) == "No results."


def test_ask_runs_tool_then_answers():
    stats = [{"id": "ATL-ORD-202401", "totals": {"on_time_rate": 0.7724}}]
    tools, calls = tools_with(route_stats=stats)
    call = {"name": "get_route_delay_stats", "id": "c1",
            "args": {"origin": "ATL", "dest": "ORD", "start_month": 202401}}  # fmt: skip
    llm = ScriptedModel(
        messages=iter([AIMessage("", tool_calls=[call]), AIMessage("77.2% on time.")])
    )
    agent = build_agent(llm=llm, tools=list(tools.values()))

    answer = ask(agent, "How on time is ATL to ORD?")

    assert answer.text == "77.2% on time."
    assert calls == [("route", "ATL", "ORD", 202401, None)]
    assert [c.name for c in answer.tool_calls] == ["get_route_delay_stats"]
    assert json.loads(answer.tool_calls[0].output) == stats
    assert answer.messages[0].content == "How on time is ATL to ORD?"

    follow_up = ScriptedModel(messages=iter([AIMessage("Delta was best.")]))
    agent = build_agent(llm=follow_up, tools=list(tools.values()))
    again = ask(agent, "Which airline was best?", answer.messages)
    assert again.text == "Delta was best." and again.tool_calls == []
    assert len(again.messages) == len(answer.messages) + 2


def test_endless_tool_loop_is_stopped(monkeypatch):
    monkeypatch.setattr(agent_module, "RECURSION_LIMIT", 4)
    tools, _ = tools_with()
    loop = ({"name": "search_safety_reports", "id": f"c{i}", "args": {"query": "q"}}
            for i in range(100))  # fmt: skip
    llm = ScriptedModel(messages=(AIMessage("", tool_calls=[call]) for call in loop))

    answer = ask(build_agent(llm=llm, tools=list(tools.values())), "q")
    assert answer.text.startswith("Stopped")
