# ResearchFlowAI: Technical and Interview Guide

This guide explains the repository as it is implemented, with emphasis on the
backend and the research workflow. It is intended both as a system overview and
as preparation for explaining the project in an interview.

## 1. The project in one sentence

ResearchFlowAI is a Python application that accepts a research topic, gathers
web search results, reads one selected webpage, generates an evidence-based
report, and asks a second model call to critique that report.

## 2. Important provider-name clarification

The code uses **Groq**, not **Grok**:

- **Groq** is the model-serving provider used by `langchain-groq`. The
  application creates a `ChatGroq` client and requests the model
  `openai/gpt-oss-120b`. The required environment variable is
  `GROQ_API_KEY`.
- **Grok** is not referenced or configured in this repository. There is no
  xAI/Grok client or Grok API key in the implementation.
- **Tavily** (sometimes mistyped as “Tavly”) is the external web-search
  provider. The required environment variable is `TAVILY_API_KEY`.

In short: Groq provides language-model inference; Tavily finds web pages.
Neither is the same thing as the other.

## 3. What problem it solves

ResearchFlowAI turns a topic into a repeatable research workflow rather than
returning a single unstructured model answer. It keeps the intermediate search
and reading outputs, produces a Markdown report, and provides a separate
quality review. The same Python pipeline can be run from the terminal or
submitted through the HTTP API.

It is an **AI-assisted research and synthesis tool**, not a source-verification
system. It asks the model to ground its writing in supplied material and to
preserve URLs, but the application does not independently establish that a
source is authoritative or that every generated citation is correct.

## 4. How many agents are there?

There are **four workflow stages and four model roles**, but not four
tool-using LangChain agents:

| Workflow role | Implementation | What it does |
|---|---|---|
| Web search | LangChain agent created by `create_agent` | Chooses and invokes the `web_search` tool to find sources. |
| Web reader / scraper | LangChain agent created by `create_agent` | Chooses a URL from the search findings and invokes `scrape_url`. |
| Writer | LangChain prompt/model/output-parser chain | Synthesizes supplied research into a structured report. It does not have a tool. |
| Critic | LangChain prompt/model/output-parser chain | Scores and critiques the report against supplied evidence. It does not have a tool. |

So the precise interview answer is: **two tool-using agents, two LLM chains,
and four sequential stages**. “Research agent” can be used informally for the
overall system, but there is no separate fifth research agent in the code.
Likewise, “writer agent” and “critic agent” are understandable descriptions of
their roles, but technically they are chains rather than `create_agent`
instances.

## 5. Backend architecture and request lifecycle

```text
Browser or terminal
        │
        ▼
FastAPI endpoint (web requests only)
        │ validate topic, reserve capacity, create job
        ▼
Background thread runs run_research_pipeline(topic)
        │
        ├── Search agent ──► Tavily search tool
        ├── Reader agent ──► HTTP GET + Beautiful Soup
        ├── Writer chain ──► Groq model
        └── Critic chain ──► Groq model
        │
        ▼
Four output strings returned / stored in the in-memory job
```

### Web request path

1. The browser sends `POST /api/jobs` with a `topic`.
2. Pydantic validates the request. The topic is trimmed and must contain
   between 3 and 500 characters.
3. The server acquires an in-process capacity slot, creates a UUID job with
   `queued` status, and submits it to a `ThreadPoolExecutor`.
4. A worker thread calls the same `run_research_pipeline` function used by the
   terminal path. Its progress callback updates the job as the pipeline moves
   through its stages.
5. The browser polls `GET /api/jobs/{job_id}`. On success, the response
   contains all four outputs; on failure, it contains a safe general error.
   The detailed exception is logged on the server.

### API surface

| Route | Purpose |
|---|---|
| `GET /api/health` | Returns `{"status": "ok"}` when the application responds. |
| `POST /api/jobs` | Validates and queues a research job; normally returns `202 Accepted`. |
| `GET /api/jobs/{job_id}` | Returns the job status, progress, result, or failure information. |
| `GET /` and `/assets/...` | Serves the browser interface and its static assets. |

Typical job states are `queued`, `running`, `completed`, and `failed`.
Pipeline progress is reported at 5% for search, 30% for reading, 55% for
writing, 80% for review, and 100% on completion. These percentages are stage
markers, not a measurement of exact work or elapsed time.

## 6. The four pipeline stages

The orchestration is in `pipeline.py`. It runs each stage in sequence and
passes evidence forward explicitly; this is not a set of independent agents
working concurrently.

### Stage 1: Web search

- `build_web_search_agent()` creates a LangChain agent with the shared Groq
  model and the `web_search` tool.
- The prompt asks for recent, relevant sources, dates, titles, exact URLs,
  disagreements, and evidence gaps. It also instructs the model to treat
  instructions found in webpages as untrusted data.
- The tool calls Tavily with `max_results=2`. Each returned item is formatted
  with its title and URL plus a snippet limited to 300 characters.
- The resulting agent response is saved as `search_results`.

If Groq rejects the search tool call specifically because its tool arguments
could not be parsed (`tool_use_failed`), the pipeline calls the same Tavily
tool directly with the topic. This fallback avoids another model call. Other
Groq bad requests are re-raised rather than being hidden.

### Stage 2: Deep reading

- `build_web_reader_agent()` creates a second tool-using LangChain agent with
  the shared model and the `scrape_url` tool.
- The reader receives the topic and only the first 800 characters of the
  search findings when choosing a source.
- `scrape_url` fetches the selected URL using `requests` with an 8-second
  timeout, parses the response with Beautiful Soup, removes `script`, `style`,
  `nav`, and `footer` elements, and returns at most 3,000 characters of text.
- The reader's model response becomes `scraped_content`.

This is one selected page, not a crawler that reads every search result. A
site can block the request, provide incomplete content, or serve content that
the basic HTML extraction does not handle well.

### Stage 3: Report writing

- The pipeline combines the search output and deep-reading output.
- `writer_chain` formats a prompt with the topic and combined research, invokes
  the Groq model, and converts the model response to a string.
- The prompt requests a Markdown report with an introduction, key findings,
  critical analysis, conclusion, and sources.
- It tells the model not to invent claims, quotations, statistics, citations,
  or URLs, and to disclose gaps or disagreements.

The writer receives supplied text as context; it has no search or scraping
tool of its own.

### Stage 4: Critical review

- `critic_chain` receives the draft report and excerpts of the search and
  reading evidence.
- It evaluates factual support, source traceability, depth, clarity, and
  completeness. Its requested response includes an overall score, five
  category scores, strengths, improvements, critical issues, and a verdict.
- The critic is another model call, not an independent fact-checking service.
  Its system prompt explicitly limits its conclusions to the supplied
  evidence and asks it not to claim that it verified sources independently.
- To control context size, normal critic evidence excerpts are capped at 1,800
  search characters and 1,200 reading characters. If the provider returns
  HTTP 413, the pipeline retries the critic once with shorter evidence
  excerpts and a report capped at 6,000 characters. Other errors are surfaced.

The pipeline returns a dictionary with these four keys:

```text
search_results
scraped_content
report
feedback
```

## 7. Groq, Tavily, and the supporting technologies

### Groq

`agents.py` defines a cached `_get_llm()` factory that creates
`ChatGroq(model="openai/gpt-oss-120b", temperature=0)`. The model is shared by
the search agent, reader agent, writer chain, and critic chain. `temperature=0`
requests lower-variance model output; it does not make the output guaranteed
correct or perfectly deterministic.

The code applies output token limits by stage:

| Model stage | Maximum output tokens |
|---|---:|
| Search agent | 1,400 |
| Reader agent | 1,000 |
| Writer | 3,000 |
| Critic | 700 |

The model factory is cached and provider use is lazy: importing the app and
checking its health does not itself need to make a model request. A real
research run needs valid provider credentials.

### Tavily

Tavily provides web search through `TavilyClient`. The application requires
`TAVILY_API_KEY` and requests at most two search results per tool call. Tavily
returns search material; it does not generate the final report or act as the
LLM.

### Other backend libraries

- **FastAPI** defines the HTTP API and serves the static frontend.
- **Uvicorn** runs the FastAPI application as an ASGI server.
- **Pydantic** validates request and response data.
- **LangChain** provides the tool-using agent and prompt/model/parser
  composition. `StrOutputParser` produces plain-text report and review output.
- **Requests** retrieves a selected webpage.
- **Beautiful Soup** extracts readable text from HTML.
- **python-dotenv** loads local settings from `.env`.
- **Rich** formats pipeline output in the terminal.
- **`ThreadPoolExecutor`, locks, and a bounded semaphore** provide the
  lightweight in-process job execution and coordination.

## 8. State, capacity, and operational behavior

- The executor has **two worker threads**, so at most two jobs execute at the
  same time.
- A bounded semaphore allows at most **eight accepted or running jobs** at a
  time, including jobs waiting for a worker.
- The server keeps at most **100 job records**. Completed and failed records
  older than **24 hours** are pruned; if the history is full, older terminal
  records can be evicted to make room.
- Jobs are held in a Python dictionary protected by a lock. There is **no
  database, durable queue, or cross-process job store**. Restarting the process
  loses the job history and any in-flight work.
- Because this state is process-local, multiple Uvicorn workers do not share
  the same jobs. The documented setup assumes a single worker.

These choices are reasonable for a local or demonstration application. A
production service would normally move job state and execution to durable,
shared infrastructure and would need to plan for retries, cancellation,
observability, and provider limits.

## 9. Configuration and running the backend

The application expects these values in a root `.env` file:

```dotenv
GROQ_API_KEY=your-groq-api-key
TAVILY_API_KEY=your-tavily-api-key
```

Do not put real keys in source code or commit them. `.env` is listed in
`.gitignore`.

To run the web application from the project root:

```powershell
python -m uvicorn app:app --reload
```

The API documentation is available at `/docs`; the health route is
`/api/health`. The original terminal entry point is:

```powershell
python pipeline.py
```

Both entry points call the same pipeline, so there is not a separate web
research implementation.

## 10. Repository map

| Path | Responsibility |
|---|---|
| `app.py` | FastAPI app, request validation, in-memory job lifecycle, thread pool, limits, and static-file routes. |
| `pipeline.py` | Sequential orchestration, progress callbacks, evidence handoff, fallbacks, and terminal entry point. |
| `agents.py` | Shared Groq model setup, search and reader agents, writer prompt chain, and critic prompt chain. |
| `tools.py` | Tavily search and webpage retrieval/text extraction tools. |
| `web/` | Plain HTML, CSS, and JavaScript client; no separate frontend build system. |
| `tests/test_api.py` | API validation, health/static routes, job success/failure, and missing-job behavior. |
| `tests/test_pipeline.py` | Pipeline stage behavior, progress, critic retry, and search-tool fallback. |
| `tests/test_agents.py` | Writer/critic chain calls and lazy model setup. |
| `requirements.txt` | Python runtime dependencies. |
| `README.md` and `START.md` | Setup, API, usage, and operating guidance. |

## 11. Design strengths and limitations to explain honestly

### Strengths

- The pipeline has clear responsibilities and a predictable stage order.
- Search results, deeper reading, the report, and critique are returned
  separately, which makes the output easier to inspect.
- The web and terminal entry points share one workflow implementation.
- External calls are isolated behind tools and model chains, making the
  pipeline straightforward to test with mocks.
- Topic validation, capacity limits, synchronized in-memory state, logged
  server errors, and a safe public failure message provide a basic operational
  boundary.
- Prompts emphasize source traceability, evidence gaps, and not treating
  retrieved webpage instructions as trusted commands.

### Limitations

- This is a linear, single-pass workflow. The critic does not automatically
  send the report back to the writer for revision.
- The system reads one selected page, and the search tool asks for at most two
  results. Evidence breadth is therefore limited.
- The model's citations and assessment are generated text; they are not
  mechanically verified against source passages.
- The critic sees bounded excerpts, so it may not see evidence omitted from
  those excerpts.
- A simple HTTP fetch and HTML text extraction can fail on JavaScript-heavy,
  blocked, or unusual sites.
- Job state is in memory and is lost on restart. The app has no authentication
  or authorization, and the README cautions against exposing it to an
  untrusted network.
- Automated tests mock provider calls; they do not prove live Groq/Tavily
  connectivity or quality.

### Is this RAG?

It is RAG-like in the broad sense that it retrieves external web information
and supplies it to a language model. More precisely, the repository implements
a live search-and-read pipeline. It does **not** implement a conventional
embedding/vector-database retrieval system: there is no embedding model,
vector store, persistent document index, or semantic chunk retrieval.

## 12. Top 20 interview questions and answers

### 1. What is ResearchFlowAI?

It is an AI-assisted research application. A user supplies a topic, and the
backend searches the web, reads a selected source, synthesizes the evidence
into a structured Markdown report, and asks a separate model call to critique
the report. It exposes the same pipeline through a terminal entry point and a
FastAPI web API.

### 2. What problem does the project solve?

It organizes several common research tasks into one repeatable workflow. The
search and reading stages gather context, the writer turns that context into a
report, and the critic highlights quality issues. Keeping the intermediate
outputs visible helps a user compare the report with the material provided to
the model. It assists research; it does not replace checking primary sources.

### 3. How many agents does it have?

There are two actual tool-using LangChain agents: the web search agent and the
web reader agent. The writer and critic are separate LangChain prompt/model/
output-parser chains, not agents created with `create_agent`. Therefore, I
describe it as four workflow stages, with two tool-using agents and two
specialized LLM chains.

### 4. What is the difference between the search agent and reader agent?

The search agent has access to `web_search`, which queries Tavily and returns
up to two source results with short snippets. The reader agent has access to
`scrape_url`; it chooses a relevant URL from the search findings and requests
the page for a limited text extraction. Search discovers candidate sources;
reading inspects one selected source in more detail.

### 5. Where is the Grok API used? What does Grok do?

There is no Grok or xAI integration in this codebase. The project uses **Groq**
through `langchain-groq`, with the model identifier
`openai/gpt-oss-120b`. The shared Groq model powers both tool-using agents and
the writer and critic chains. The credential is `GROQ_API_KEY`. Grok and Groq
are different names and products.

### 6. What does Tavily do?

Tavily is the web-search service, configured with `TAVILY_API_KEY`. The
`web_search` tool sends a query to Tavily, asks for up to two results, and
formats each result's title, URL, and a snippet limited to 300 characters.
Tavily finds source material; Groq supplies the language model that reasons
over and writes from that material.

### 7. Walk me through one research run.

The pipeline first asks the search agent to search the topic. It passes a
short excerpt of those findings to the reader agent, which selects a URL and
extracts up to 3,000 characters of page text. The pipeline combines the
search and reading outputs and gives them, with the topic, to the writer
chain. Finally, the critic chain compares the report to bounded excerpts of
the supplied evidence. The function returns search findings, reading output,
report, and review.

### 8. How is the web backend structured?

FastAPI defines the application and API. `POST /api/jobs` validates a topic,
creates a UUID-backed job, and submits the pipeline to a background
`ThreadPoolExecutor`. The client polls `GET /api/jobs/{job_id}` to read state
and results. `GET /api/health` is a lightweight health route. The same
pipeline can also run directly from `pipeline.py`.

### 9. Why run research as a background job?

Web search and model calls involve network latency and can take longer than a
normal request/response. Returning `202 Accepted` quickly lets the client poll
for status instead of keeping the initial HTTP request open for the entire
workflow. In this implementation, background execution is process-local and
uses Python threads rather than a distributed task queue.

### 10. How does job concurrency work?

The executor has two worker threads, so at most two jobs run simultaneously.
A bounded semaphore caps accepted or running work at eight, including jobs
waiting for a worker. A lock protects the in-memory job dictionary while
requests and worker callbacks read or update it. This is a simple single
process design, not a distributed queue.

### 11. Where are jobs persisted?

They are not persisted to a database. Job records live in a Python dictionary
in the application process. Completed or failed records older than 24 hours
can be pruned, and the dictionary is capped at 100 records. A process restart
clears all records, so production deployment would need durable shared storage
if job recovery or multi-worker operation were required.

### 12. How are inputs validated and errors handled?

Pydantic checks that the topic is between 3 and 500 characters; a validator
trims whitespace and rejects values that are too short after trimming. The
API can return `422` for invalid input, `429` when the work capacity is full,
`503` when it cannot accept/store a job, and `404` for an unknown job ID.
Worker exceptions are logged on the server while the client receives a
general error message rather than raw exception details.

### 13. How does the web scraping tool work?

`scrape_url` makes a `requests.get` call with an eight-second timeout and a
browser-like user agent, checks for an HTTP error, and parses the response with
Beautiful Soup. It removes script, style, navigation, and footer elements,
then returns at most 3,000 characters of text. It is a small extraction
utility, not a full browser or robust crawler.

### 14. How do you reduce unsupported claims and fabricated citations?

The search, reader, writer, and critic prompts repeatedly direct the model to
use supplied evidence, retain source titles and URLs, disclose gaps, and avoid
inventing facts or sources. The writer is told to cite supported claims with
numbered references. These measures improve discipline, but prompt rules are
not proof: citations still need to be checked against the original pages.

### 15. Does the critic fact-check the report independently?

No. It receives the report and excerpts from the research already gathered by
the same pipeline. It assesses whether the report appears supported by that
material and whether citations are traceable in the supplied context. It does
not independently revisit every URL or verify claims against an external
ground-truth database. Its score is an AI-generated review.

### 16. What happens if a model request is too large or a tool call is malformed?

If the search agent fails with Groq's specific `tool_use_failed` error, the
pipeline makes the existing Tavily search call directly using the topic. It
does not hide other bad requests. If the critic gets an HTTP 413 response, the
pipeline retries that review once with shorter report and research excerpts.
Other errors propagate to the web job handler, which logs the exception and
marks the job failed.

### 17. Is this a RAG application?

It is reasonable to call it retrieval-augmented in a broad, informal sense:
the application retrieves current web content and places that content in
model prompts. Technically, it is a live web-search-and-read pipeline, not a
standard vector-search RAG architecture. It has no embeddings, vector database,
document index, or semantic chunk retrieval.

### 18. How is the code tested?

The project uses Python's `unittest` framework. API tests cover health and
static-file routes, topic validation, job completion/failure, and unknown job
IDs. Pipeline tests mock agents and chains to check stage outputs, progress,
the critic's 413 retry, and the search fallback. Agent tests verify lazy
provider initialization and token limits. The tests mock external services,
so they do not make real Groq or Tavily calls.

### 19. What are the main limitations or production gaps?

The workflow reads a small number of sources and only one page in depth. Its
citations and critique are not independently validated. The job store is
in-memory, jobs are not shared across multiple server processes, and there is
no authentication or authorization. A production version would need durable
job handling, access controls, secure deployment, stronger observability and
retry policies, and a strategy for verifying evidence and citations.

### 20. What would you improve next?

I would first improve evidence traceability: preserve source metadata and
passage-level references through each stage, then validate that report
citations map to retrieved passages. Next, I would expand and diversify source
retrieval, add reliable scraping with explicit source failure reporting, and
allow a review-and-revision loop with bounded retries. For deployment, I
would replace the in-memory job dictionary and thread pool with durable shared
job infrastructure, add authentication and request controls, and measure
provider latency, errors, and cost. I would test each addition with mocked
providers and selected live integration checks.

## 13. Two-to-three-minute interview summary

> ResearchFlowAI is a Python-based research assistant that takes a topic and
> turns it into a sourced, critically reviewed report. The backend is the main
> part of the project. Its core is a sequential four-stage pipeline that can
> be run from the terminal or submitted through a FastAPI endpoint.
>
> In the first stage, a LangChain web-search agent uses Tavily to find up to
> two candidate sources and preserve their titles, URLs, and short snippets.
> In the second stage, a separate reader agent selects one of those URLs and
> uses Requests and Beautiful Soup to extract a limited amount of readable
> page text. The third stage combines the search and reading evidence and
> passes it to a writer chain, which produces a structured Markdown report.
> The fourth stage is a critic chain: it reviews the report against excerpts
> of the supplied evidence and returns scores, strengths, gaps, and suggested
> improvements.
>
> There are two actual tool-using agents—the search and reader—and two
> specialized model chains for writing and critique. All four use the shared
> Groq model client configured in the project. One naming detail I would make
> clear is that this repository uses Groq, not Grok or the xAI API. Tavily
> handles web search; it does not write the report.
>
> For the web path, FastAPI validates a topic, creates a UUID job, and runs
> the pipeline in a background thread. The API reports progress and the client
> polls for the four outputs. The implementation is intentionally lightweight:
> it has two worker threads, permits up to eight accepted or running jobs,
> and stores job state in memory rather than a database.
>
> The main design strength is the clear separation between search, reading,
> writing, and review, with intermediate evidence exposed for inspection. The
> main limitations are that it reads only a small number of sources, does not
> independently verify citations, and loses job state on restart. I would
> improve evidence traceability and source verification first, then move job
> handling to durable shared infrastructure before treating it as a
> production service.

## 14. Quick facts to memorize

- **Language:** Python.
- **HTTP framework/server:** FastAPI and Uvicorn.
- **Model provider/model:** Groq through `langchain-groq`,
  `openai/gpt-oss-120b`.
- **Search provider:** Tavily; `max_results=2`.
- **Page extraction:** Requests plus Beautiful Soup; 8-second request timeout,
  maximum 3,000 extracted characters.
- **Stages:** Search → deep reading → report writing → critical review.
- **Agent count:** Two tool-using agents; writer and critic are chains.
- **Web job execution:** Two worker threads, up to eight accepted/running jobs.
- **Job storage:** In-memory only; maximum 100 records, terminal records older
  than 24 hours eligible for pruning.
- **Persistence:** No database.
- **Tests:** `python -m unittest discover -s tests -v`; provider calls are
  mocked.
- **Credential names:** `GROQ_API_KEY` and `TAVILY_API_KEY`.
