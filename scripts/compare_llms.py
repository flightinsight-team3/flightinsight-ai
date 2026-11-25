"""Ask the same questions with each chat model and write a comparison table (markdown).

    python scripts/compare_llms.py                      # gemini + ollama, default models
    python scripts/compare_llms.py --models gemini:gemini-3.6-flash ollama:qwen2.5:7b
    python scripts/compare_llms.py --out data/llm_comparison.md

For each question it records the time, the tools called with their arguments, and the answer,
so tool choice and grounding can be checked by hand. Uses real Cosmos data and LLM quota.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# (question, tools a good answer needs)
QUESTIONS = [
    ("How on time was ATL to ORD in January 2024?", {"get_route_delay_stats"}),
    ("Which airline had the lowest average arrival delay from DFW to LAX in January 2024?",
     {"get_route_delay_stats"}),
    ("Are there safety reports about crews feeling rushed because of delays?",
     {"search_safety_reports"}),
    ("Find reports about de-icing or snow problems for B737 aircraft.", {"search_safety_reports"}),
    ("How delayed was ORD to ATL in January 2024, and do pilots report delay pressure?",
     {"get_route_delay_stats", "search_safety_reports"}),
    ("What was the on-time rate from ATL to ORD in July 2024?", {"get_route_delay_stats"}),
]  # fmt: skip


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    from app.agent.agent import ask, build_agent
    from app.agent.llm import default_model
    from app.settings import load_dotenv

    load_dotenv()
    runs = []
    for spec in args.models:
        provider, _, model = spec.partition(":")
        model = model or default_model(provider)
        agent = build_agent(provider, model)
        for question, needed in QUESTIONS[: args.limit]:
            print(f"[{provider}/{model}] {question}", flush=True)
            try:
                answer = ask(agent, question)
                used = [f"{c.name}({compact(c.args)})" for c in answer.tool_calls]
                ok = needed <= {c.name for c in answer.tool_calls}
                runs.append(
                    (f"{provider}/{model}", question, answer.seconds, ok, used, answer.text)
                )
            except Exception as e:
                runs.append((f"{provider}/{model}", question, 0.0, False, [], f"ERROR {e}"))
            print(f"  {runs[-1][2]:.1f}s, right tools: {runs[-1][3]}", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report(runs), encoding="utf-8")
    print(f"wrote {args.out}")


def compact(call_args: dict) -> str:
    return ", ".join(f"{k}={v!r}" for k, v in call_args.items() if v is not None)


def report(runs: list[tuple]) -> str:
    lines = ["# LLM comparison", "", "| Model | Question | Seconds | Right tools | Tool calls |"]
    lines.append("|---|---|---|---|---|")
    for model, question, seconds, ok, used, _ in runs:
        calls = "<br>".join(used).replace("|", "\\|") or "none"
        lines.append(
            f"| {model} | {question} | {seconds:.1f} | {'yes' if ok else 'no'} | {calls} |"
        )
    models = sorted({r[0] for r in runs})
    lines += ["", "| Model | Right tools | Mean seconds |", "|---|---|---|"]
    for model in models:
        mine = [r for r in runs if r[0] == model]
        mean = sum(r[2] for r in mine) / len(mine)
        lines.append(f"| {model} | {sum(r[3] for r in mine)}/{len(mine)} | {mean:.1f} |")
    lines += ["", "## Answers", ""]
    for model, question, _, _, _, text in runs:
        lines += [f"### {model}: {question}", "", text, ""]
    return "\n".join(lines)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--models", nargs="+", default=["gemini", "ollama"],
                        help="provider or provider:model")  # fmt: skip
    parser.add_argument("--limit", type=int, default=len(QUESTIONS), help="first N questions")
    parser.add_argument("--out", type=Path, default=Path("data/llm_comparison.md"))
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
