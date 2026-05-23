"""Research coordinator: specialist agents as tools, email via handoff."""

import asyncio
from typing import Any

from agents import Agent, Runner, function_tool, handoff
from agents.extensions import handoff_filters

from email_agent import email_agent
from planner_agent import WebSearchItem, WebSearchPlan, planner_agent
from search_agent import search_agent
from writer_agent import ReportData, writer_agent

RECOMMENDED_PROMPT_PREFIX = (
    "# System context\n"
    "You are part of a multi-agent system (OpenAI Agents SDK). "
    "You can use **tools** and **handoffs**. Handoffs use functions like `transfer_to_email_agent`. "
    "Do not narrate internal transfers to the end user.\n"
)

COORDINATOR_INSTRUCTIONS = (
    f"{RECOMMENDED_PROMPT_PREFIX}\n"
    "You are the Research Coordinator. Conduct one complete deep-research job.\n\n"
    "Tools (call in this order):\n"
    "1. `run_planner_tool` — pass a planning_context string with the original query and any clarifying Q&A.\n"
    "2. `run_searches_from_plan_tool` — runs all planned web searches in parallel (no arguments).\n"
    "3. `run_writer_tool` — writes the structured report from accumulated search snippets (no arguments).\n\n"
    "Then **hand off** to the email agent. Include the **full markdown report** from run_writer_tool "
    "in your handoff message so it can be emailed.\n"
    "Do not skip steps. Do not call tools out of order."
)

email_handoff = handoff(
    agent=email_agent,
    tool_description_override=(
        "Send the finalized research report by email (HTML). "
        "The handoff message must include the complete markdown report."
    ),
    input_filter=handoff_filters.remove_all_tools,
)

TOOL_LABELS = {
    "run_planner_tool": "Planning searches",
    "run_searches_from_plan_tool": "Performing web searches",
    "run_writer_tool": "Writing the report",
    email_handoff.tool_name: "Sending report via email",
}


def _planner_input(query: str, clarifications: str, planning_context: str) -> str:
    if planning_context.strip():
        return planning_context
    parts = [f"Query: {query}"]
    if clarifications:
        parts.append(clarifications)
        parts.append(
            "Use the clarifying Q&A above to narrow the search plan. "
            "Each search should help answer the refined intent, not generic background."
        )
    return "\n\n".join(parts)


def _search_input(query: str, clarifications: str, item: WebSearchItem) -> str:
    parts = [f"Original query: {query}"]
    if clarifications:
        parts.append(clarifications)
    parts.append(f"Search term: {item.query}\nReason for searching: {item.reason}")
    return "\n\n".join(parts)


def _writer_input(query: str, clarifications: str, search_results: list[str]) -> str:
    parts = [f"Original query: {query}"]
    if clarifications:
        parts.append(clarifications)
        parts.append(
            "Honor the user's clarifications above when structuring and emphasizing the report."
        )
    parts.append(f"Summarized search results: {search_results}")
    return "\n\n".join(parts)


async def _search_one(query: str, clarifications: str, item: WebSearchItem) -> str | None:
    try:
        result = await Runner.run(search_agent, _search_input(query, clarifications, item))
        return str(result.final_output)
    except Exception:
        return None


def build_coordinator_agent(ctx: dict[str, Any]) -> Agent:
    """Build a coordinator whose tools read/write shared research context."""

    @function_tool
    async def run_planner_tool(planning_context: str) -> str:
        """Create a web search plan from the research brief (query plus clarifications)."""
        input_text = _planner_input(ctx["query"], ctx["clarifications"], planning_context)
        result = await Runner.run(planner_agent, input_text)
        plan = result.final_output_as(WebSearchPlan)
        ctx["last_plan"] = plan
        return plan.model_dump_json()

    @function_tool
    async def run_searches_from_plan_tool() -> str:
        """Execute every search in the last plan in parallel."""
        plan: WebSearchPlan | None = ctx.get("last_plan")
        if not plan or not plan.searches:
            return "Error: no search plan found. Call run_planner_tool first."

        query = ctx["query"]
        clarifications = ctx["clarifications"]

        async def one(item: WebSearchItem) -> str:
            out = await _search_one(query, clarifications, item)
            if out is not None:
                ctx["search_results"].append(f"---\nTerm: {item.query}\n{out}")
                return f"OK: {item.query}"
            return f"Failed: {item.query}"

        outcomes = await asyncio.gather(*[one(s) for s in plan.searches])
        return "\n".join(outcomes)

    @function_tool
    async def run_writer_tool() -> str:
        """Synthesize accumulated search snippets into the final markdown report."""
        bundle = ctx["search_results"]
        if not bundle:
            return "Error: no search results yet. Call run_searches_from_plan_tool first."

        input_text = _writer_input(ctx["query"], ctx["clarifications"], bundle)
        result = await Runner.run(writer_agent, input_text)
        report = result.final_output_as(ReportData)
        ctx["last_report"] = report
        return report.markdown_report

    return Agent(
        name="ResearchCoordinator",
        instructions=COORDINATOR_INSTRUCTIONS,
        model="gpt-4o-mini",
        tools=[run_planner_tool, run_searches_from_plan_tool, run_writer_tool],
        handoffs=[email_handoff],
    )


def build_research_brief(query: str, clarifications: str) -> str:
    """User message for the coordinator agent."""
    parts = [f"Original query:\n{query}"]
    if clarifications:
        parts.append(clarifications)
        parts.append("Incorporate these clarifications throughout the research.")
    parts.append(
        "Run the full pipeline: run_planner_tool (pass a rich planning_context), "
        "run_searches_from_plan_tool, run_writer_tool, then hand off to the email agent "
        "with the complete markdown report."
    )
    return "\n\n".join(parts)
