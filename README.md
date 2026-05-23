# Deep Research

A multi-agent research assistant built with the [OpenAI Agents SDK](https://github.com/openai/openai-agents-python). You enter a topic in a Gradio UI; the app plans web searches, runs them in parallel, writes a markdown report, and emails it via SendGrid.

## How it works

```
deep_research.py (UI)
       │
       ▼
research_manager.py
       │
       ├── planner_agent   → plans ~5 search queries
       ├── search_agent    → web search + short summaries (parallel)
       ├── writer_agent    → long markdown report
       └── email_agent     → HTML email via SendGrid
```

| File | Role |
|------|------|
| `src/deep_research.py` | Gradio app entry point |
| `src/research_manager.py` | Orchestrates plan → search → write → email |
| `src/planner_agent.py` | Structured search plan (`WebSearchPlan`) |
| `src/search_agent.py` | `WebSearchTool` summaries per query |
| `src/writer_agent.py` | Final report (`ReportData`) |
| `src/email_agent.py` | Sends report as HTML email |

## Prerequisites

- [uv](https://docs.astral.sh/uv/) for environment and dependencies
- Python **3.12** (see `.python-version`)
- API keys in a `.env` file at the project root (gitignored)

## Setup

```bash
cd deep_research
uv sync
```

Create `.env` with at least:

```env
OPENAI_API_KEY=your_key_here
SENDGRID_API_KEY=your_key_here
```

Update the sender and recipient addresses in `src/email_agent.py` if needed.

Optional dev dependencies (e.g. Jupyter kernel):

```bash
uv sync --group dev
```

## Run

```bash
uv run src/deep_research.py
```

This opens the Gradio UI in your browser. Enter a research topic and click **Run** (or press Enter). Progress updates stream into the report area; the final output is the markdown report.

Traces are logged to the [OpenAI Traces](https://platform.openai.com/traces) dashboard during a run.

## Project layout

```
deep_research/
├── pyproject.toml      # dependencies (managed by uv)
├── uv.lock             # locked versions
├── requirements.txt    # pip-compile export (optional)
├── .python-version     # 3.12
├── .env                # secrets (not committed)
└── src/
    ├── deep_research.py
    ├── research_manager.py
    ├── planner_agent.py
    ├── search_agent.py
    ├── writer_agent.py
    └── email_agent.py
```
