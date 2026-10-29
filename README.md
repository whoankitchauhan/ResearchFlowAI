# ResearchFlowAI

**From a focused question to a sourced, critically reviewed research report.**

ResearchFlowAI is an AI-assisted research application with two ways to work: a
simple terminal workflow and a polished browser interface. Both use the same
research pipeline: search the web, investigate a source in more depth, write a
structured report, and critically review the result.

For an interview-focused backend walkthrough, agent-count clarification, and
20 project questions with answers, see [interview.md](./interview.md).

> ResearchFlowAI helps organize and synthesize information. It does not
> independently verify every source or replace expert judgment. Check important
> claims and citations against the original sources.

## Contents

- [What ResearchFlowAI does](#what-researchflowai-does)
- [How a research run works](#how-a-research-run-works)
- [Project structure](#project-structure)
- [Requirements and API keys](#requirements-and-api-keys)
- [Install](#install)
- [Start the web application](#start-the-web-application)
- [Use the terminal application](#use-the-terminal-application)
- [HTTP API](#http-api)
- [Research results](#research-results)
- [Run the tests](#run-the-tests)
- [Configuration and operating notes](#configuration-and-operating-notes)
- [Troubleshooting](#troubleshooting)
- [Technology](#technology)

## What ResearchFlowAI does

Give ResearchFlowAI a research question or topic. It then coordinates four
stages and returns the output from each one:

1. **Web research** — searches for recent, relevant findings and preserves
   source information.
2. **Deep reading** — selects a URL from the search findings and extracts
   readable page content for closer investigation.
3. **Report writing** — synthesizes the gathered research into a Markdown
   report, with a structured introduction, findings, analysis, conclusion, and
   source list.
4. **Critical review** — evaluates evidence support, traceability, analysis,
   clarity, and completeness, and identifies areas to improve.

The browser interface displays progress, lets you switch between the four
outputs, and can copy or download the selected output. The terminal workflow
continues to be available.

## How a research run works

```text
Your question
     │
     ▼
1. Web search ──► search findings and source URLs
     │
     ▼
2. Deep reading ─► extracted content from a selected source
     │
     ▼
3. Report writing ► structured Markdown research report
     │
     ▼
4. Critical review ► score, strengths, issues, and suggested improvements
```

The search and reader agents use a Groq-hosted language model and the
corresponding LangChain tools. Web search is provided by Tavily. Page reading
uses HTTP requests and Beautiful Soup to extract text. The writer and critic
are separate prompt chains using the same model.

ResearchFlowAI asks the agents to avoid unsupported claims, preserve source
URLs, identify limitations, and treat instructions found in retrieved pages
as untrusted content. These are workflow instructions, not a guarantee that
generated content is error-free.

## Project structure

| File or folder | Purpose |
| --- | --- |
| `app.py` | FastAPI application, request validation, asynchronous research-job handling, and static frontend hosting. |
| `pipeline.py` | Shared four-stage workflow; used by both the web application and terminal entry point. |
| `agents.py` | Search and reader agents, plus report-writing and critical-review chains. |
| `tools.py` | Tavily web search and webpage text extraction tools. |
| `web/index.html` | ResearchFlowAI browser interface markup. |
| `web/styles.css` | Responsive interface styling. |
| `web/app.js` | API integration, progress polling, result navigation, copy, and download behavior. |
| `tests/` | Automated tests for the API, workflow, and lazy model initialization. |
| `requirements.txt` | Python dependencies. |
| `.env` | Your local API credentials; create this file yourself and never commit it. |

## Requirements and API keys

- Python **3.10 or newer**
- A [Groq API key](https://console.groq.com/keys)
- A [Tavily API key](https://app.tavily.com/)

Create a `.env` file in the project root with your own credentials:

```dotenv
GROQ_API_KEY=your-groq-api-key
TAVILY_API_KEY=your-tavily-api-key
```

Keep the values private. Do not paste real keys into source files, documentation,
screenshots, issue reports, or commits. The `.env` file is ignored by Git.
ResearchFlowAI initializes provider clients only when a research run needs
them, so the web server and health endpoint can start without the keys; a real
run needs both providers configured.

## Install

Run these commands from the ResearchFlowAI project directory.

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks virtual-environment activation, either use a permitted
execution policy or call the virtual-environment Python directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### macOS or Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Start the web application

With the environment activated and `.env` configured, run:

```bash
python -m uvicorn app:app --reload
```

Then open <http://127.0.0.1:8000>.

| Address | What it does |
| --- | --- |
| <http://127.0.0.1:8000> | ResearchFlowAI web interface |
| <http://127.0.0.1:8000/docs> | Interactive Swagger API documentation |
| <http://127.0.0.1:8000/redoc> | ReDoc API documentation |
| <http://127.0.0.1:8000/api/health> | Lightweight service health check |

Stop the development server with **Ctrl+C**.

The `--reload` option is for local development. For a different local port:

```bash
python -m uvicorn app:app --host 127.0.0.1 --port 8080
```

## Use the terminal application

The original interactive workflow remains available from the project root:

```bash
python pipeline.py
```

Enter a research topic when prompted. ResearchFlowAI prints the search
findings, deeper reading, report, and critical review to the terminal. The same
`run_research_pipeline` function powers the web application; the web interface
adds progress reporting without replacing the underlying workflow.

## HTTP API

The API accepts topics containing **3–500 characters** after trimming
whitespace. Start a run with `POST /api/jobs`; poll the returned job ID with
`GET /api/jobs/{job_id}` until the status is `completed` or `failed`.

### Start a research run

```http
POST /api/jobs
Content-Type: application/json
```

```json
{
  "topic": "How are cities adapting their power grids for extreme heat?"
}
```

Example response (`202 Accepted`):

```json
{
  "id": "d5f56d2f-9140-4236-bd98-37c98dc5d117",
  "topic": "How are cities adapting their power grids for extreme heat?",
  "status": "queued",
  "stage": "queued",
  "progress": 0,
  "created_at": "2026-10-26T00:00:00+00:00",
  "updated_at": "2026-10-26T00:00:00+00:00",
  "result": null,
  "error": null
}
```

### Check a research run

```http
GET /api/jobs/d5f56d2f-9140-4236-bd98-37c98dc5d117
```

While a job is running, the response reports its current `status`, `stage`, and
`progress`. When it completes, `result` contains all four outputs:

```json
{
  "search_results": "Search findings and source information...",
  "scraped_content": "The reader agent's deeper source summary...",
  "report": "# 1. Introduction\n...",
  "feedback": "Score: 8/10\n..."
}
```

### Statuses and errors

| HTTP status | Meaning |
| --- | --- |
| `202` | Job accepted and queued. |
| `200` | Job status or health response returned successfully. |
| `404` | The job ID does not exist or has expired. |
| `422` | The request is invalid, such as a missing or out-of-range topic. |
| `429` | Research capacity is full; wait and try again. |
| `503` | The service cannot accept or store another job right now. |

Job statuses are `queued`, `running`, `completed`, and `failed`. Progress
stages are `search`, `reading`, `writing`, and `reviewing`; a completed run
reports `completed` at 100 percent. On failure, the API returns a safe,
general error message; detailed exception information is kept in the server
log rather than sent to the browser.

## Research results

The final report is Markdown and is intended to organize the gathered evidence
into these sections:

1. Introduction
2. Key findings
3. Critical analysis
4. Conclusion
5. Sources

The critic returns an overall score, a breakdown across five quality
dimensions, strengths, areas to improve, critical issues, and a one-line
verdict. The web interface also exposes the original search and deep-reading
stage outputs so you can compare the report with the research supplied to it.

## Run the tests

From the project root:

```bash
python -m unittest discover -s tests -v
```

The automated tests mock external provider calls. They validate API behavior,
input checks, job success and failure handling, frontend serving, the four
pipeline outputs, and lazy model initialization. They do **not** make live
Groq or Tavily requests; configure valid API keys and run the app to verify
those external integrations in your environment.

## Configuration and operating notes

- **Job execution:** Research jobs run in background threads within the
  application process. Up to two jobs execute at once, with a maximum of eight
  accepted or running jobs at a time.
- **Job history:** Job data is stored in memory, not a database. It is lost
  when the server restarts. Completed and failed jobs are eligible for cleanup
  after 24 hours; the service stores at most 100 job records.
- **Multiple server workers:** In-memory jobs are not shared across processes.
  Run a single Uvicorn worker unless job storage and execution are moved to a
  shared production backend.
- **Provider usage:** Each complete research run uses external Groq and Tavily
  services. Their availability, rate limits, terms, and costs apply.
- **Token limits:** ResearchFlowAI caps generated tokens for each model stage
  and limits the evidence excerpts sent to the critic. If Groq rejects the
  critic request with HTTP 413, only that review is retried once with shorter
  excerpts. If Groq rejects malformed search-tool JSON, ResearchFlowAI runs
  the same Tavily search directly without another model call. Other failures
  are surfaced normally.
- **Network access:** Search and page reading require outbound internet
  connectivity. A source may be unavailable, block scraping, or return
  incomplete content.
- **Frontend:** The UI is plain HTML, CSS, and JavaScript served by FastAPI.
  There is no separate Node.js build or frontend server to install.

## Troubleshooting

### “GROQ_API_KEY” or “TAVILY_API_KEY” is missing

Check that `.env` is in the repository root, uses the exact variable names
shown above, and contains valid keys. Restart the application after changing
the file. Never include quotation marks unless they are part of your key.

### The research run fails although the server starts

The server can start without provider credentials; actual research cannot.
Check both keys, confirm outbound connectivity, and review the Uvicorn console
for the server-side exception. Provider outages, invalid keys, quotas, and
source-site restrictions can also interrupt a run.

### A job ID returns `404`

Job records are in-memory and expire from history. Verify the ID, and remember
that restarting the server clears all active and completed jobs.

### The interface is unavailable

Confirm Uvicorn is still running and open the exact local address printed by
the server. The health endpoint at `/api/health` should return:

```json
{"status":"ok"}
```

## Security

By default, Uvicorn binds to localhost. The API currently has no user
authentication, authorization, or durable job isolation. Do not expose
ResearchFlowAI directly to the public internet or an untrusted network. A
production deployment needs an appropriate authentication layer, HTTPS,
request and resource limits, secure secret management, and a shared durable
job store. Treat generated research as unverified until important statements
have been checked against primary sources.

## Technology

- **Python** — application and research workflow
- **FastAPI** and **Uvicorn** — HTTP API and local ASGI server
- **LangChain** and **LangGraph** — agent tooling and orchestration
- **Groq** — language model provider via `langchain-groq`
- **Tavily** — web search
- **Requests** and **Beautiful Soup** — webpage retrieval and text extraction
- **Pydantic** — request and response validation
- **HTML, CSS, and JavaScript** — responsive browser interface
