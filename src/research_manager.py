from agents import Runner, trace, gen_trace_id
from search_agent import search_agent
from planner_agent import planner_agent, WebSearchItem, WebSearchPlan
from writer_agent import writer_agent, ReportData
from email_agent import email_agent
from clarifier_agent import clarifier_agent, ClarifyingQuestions
import asyncio


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
        """Run the deep research process, yielding status updates and the final report."""
        trace_id = gen_trace_id()
        clarifications = ""
        if questions and answers is not None:
            clarifications = format_clarifications(questions, answers)

        with trace("Research trace", trace_id=trace_id):
            print(f"View trace: https://platform.openai.com/traces/trace?trace_id={trace_id}")
            yield f"View trace: https://platform.openai.com/traces/trace?trace_id={trace_id}"
            if clarifications:
                yield "Using your clarifications to focus the research..."
            print("Starting research...")
            search_plan = await self.plan_searches(query, clarifications)
            yield "Searches planned, starting to search..."
            search_results = await self.perform_searches(query, clarifications, search_plan)
            yield "Searches complete, writing report..."
            report = await self.write_report(query, clarifications, search_results)
            yield "Report written, sending email..."
            await self.send_email(report)
            yield "Email sent, research complete"
            yield report.markdown_report

    async def plan_searches(self, query: str, clarifications: str = "") -> WebSearchPlan:
        """Plan the searches to perform for the query."""
        print("Planning searches...")
        input_text = f"Query: {query}"
        if clarifications:
            input_text += f"\n\n{clarifications}\n\n"
            input_text += (
                "Use the clarifying Q&A above to narrow the search plan. "
                "Each search should help answer the refined intent, not generic background."
            )
        result = await Runner.run(
            planner_agent,
            input_text,
        )
        print(f"Will perform {len(result.final_output.searches)} searches")
        return result.final_output_as(WebSearchPlan)

    async def perform_searches(
        self,
        query: str,
        clarifications: str,
        search_plan: WebSearchPlan,
    ) -> list[str]:
        """Perform the searches in the plan."""
        print("Searching...")
        num_completed = 0
        tasks = [
            asyncio.create_task(self.search(query, clarifications, item))
            for item in search_plan.searches
        ]
        results = []
        for task in asyncio.as_completed(tasks):
            result = await task
            if result is not None:
                results.append(result)
            num_completed += 1
            print(f"Searching... {num_completed}/{len(tasks)} completed")
        print("Finished searching")
        return results

    async def search(
        self,
        query: str,
        clarifications: str,
        item: WebSearchItem,
    ) -> str | None:
        """Perform a search for one plan item."""
        parts = [f"Original query: {query}"]
        if clarifications:
            parts.append(clarifications)
        parts.append(f"Search term: {item.query}\nReason for searching: {item.reason}")
        input_text = "\n\n".join(parts)
        try:
            result = await Runner.run(
                search_agent,
                input_text,
            )
            return str(result.final_output)
        except Exception:
            return None

    async def write_report(
        self,
        query: str,
        clarifications: str,
        search_results: list[str],
    ) -> ReportData:
        """Write the report for the query."""
        print("Thinking about report...")
        parts = [f"Original query: {query}"]
        if clarifications:
            parts.append(clarifications)
            parts.append(
                "Honor the user's clarifications above when structuring and emphasizing the report."
            )
        parts.append(f"Summarized search results: {search_results}")
        input_text = "\n\n".join(parts)
        result = await Runner.run(
            writer_agent,
            input_text,
        )

        print("Finished writing report")
        return result.final_output_as(ReportData)

    async def send_email(self, report: ReportData) -> None:
        print("Writing email...")
        await Runner.run(
            email_agent,
            report.markdown_report,
        )
        print("Email sent")
        return report
