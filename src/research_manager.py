from agents import Runner, trace, gen_trace_id
from clarifier_agent import clarifier_agent, ClarifyingQuestions
from coordinator_agent import (
    TOOL_LABELS,
    build_coordinator_agent,
    build_research_brief,
)


def format_clarifications(questions: list[str], answers: list[str]) -> str:
    """Format Q&A pairs for planner, search, and writer prompts."""
    if not questions:
        return ""
    lines = []
    for q, a in zip(questions, answers):
        answer = (a or "").strip() or "(no answer provided)"
        lines.append(f"Q: {q}\nA: {answer}")
    return "Clarifying Q&A:\n" + "\n".join(lines)


class ResearchManager:

    async def run_clarify(self, query: str) -> ClarifyingQuestions:
        """Generate 3 clarifying questions for the user's query."""
        print("Generating clarifying questions...")
        result = await Runner.run(
            clarifier_agent,
            f"Query: {query}",
        )
        return result.final_output_as(ClarifyingQuestions)

    async def run(
        self,
        query: str,
        questions: list[str] | None = None,
        answers: list[str] | None = None,
    ):
        """Run deep research via the coordinator agent (tools + email handoff)."""
        trace_id = gen_trace_id()
        clarifications = ""
        if questions and answers is not None:
            clarifications = format_clarifications(questions, answers)

        ctx: dict = {
            "query": query,
            "clarifications": clarifications,
            "last_plan": None,
            "search_results": [],
            "last_report": None,
        }

        coordinator = build_coordinator_agent(ctx)
        brief = build_research_brief(query, clarifications)

        with trace("Research trace", trace_id=trace_id):
            trace_line = (
                f"View trace: https://platform.openai.com/traces/trace?trace_id={trace_id}"
            )
            print(trace_line)
            yield trace_line
            if clarifications:
                yield "Using your clarifications to focus the research..."
            yield "Starting research (coordinator agent)..."

            stream = Runner.run_streamed(coordinator, brief, max_turns=40)

            async for event in stream.stream_events():
                if event.type != "run_item_stream_event":
                    continue
                if event.item.type != "tool_call_item":
                    continue
                tool_name = getattr(event.item.raw_item, "name", None) or ""
                label = TOOL_LABELS.get(tool_name, tool_name.replace("_", " ").strip())
                if label:
                    print(label)
                    yield label

            report = ctx.get("last_report")
            if report is None:
                yield "Research finished but no report was produced. Check the trace for details."
                return

            yield "Research complete."
            yield report.markdown_report
