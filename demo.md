# How ResearchFlowAI Finds and Reads Sources

This example follows the code for the question **“What is agentic AI?”** It
explains what the project is configured to do, without inventing search results
or promising a fixed number of websites.

## The short answer

- **Search:** Each call to the Tavily search tool asks for **up to 2 results**.
  The code does not promise exactly 2, 3, or 5 websites overall. The search
  agent controls its tool use, and the code does not set a fixed number of
  search-tool calls.
- **Reading:** The reader is told to use the **most relevant URL** from the
  search evidence. It is not instructed to read every result. However, the code
  does not enforce a strict maximum of one scrape-tool call, either.
- **Writing:** The report writer receives both the search findings and the
  reader's extracted content. It can therefore use information from the search
  findings as well as the deeper reading; it does not receive only the scraped
  page.

## Step by step

### 1. You enter a question

For example:

> What is agentic AI?

The pipeline sends this topic to the web-search agent.

### 2. The search agent looks for sources

The search agent has access to a tool called `web_search`. That tool sends the
question to Tavily and sets `max_results=2` for **each tool call**. For every
returned result, the tool provides a title, URL, and a snippet limited to 300
characters.

This is a limit per search call, not a guarantee of how many websites will
appear in the complete run. The agent may decide how to use its search tool;
the pipeline does not specify a fixed total result count. If the agent's tool
call fails in one specific way, the pipeline directly calls the same search
tool once as a fallback; that call also asks Tavily for up to 2 results.

The code also does not promise that every result returned by Tavily will appear
unchanged in the search agent's final response. The search agent returns its
response, and that response is saved as the search findings.

### 3. The reader gets a shortened copy of those findings

The reading agent receives:

1. The original question.
2. The **first 800 characters** of the saved search findings.

That means the reader does not necessarily see every search finding. If a URL
is beyond those first 800 characters, it is not included in the search-evidence
text the reader uses to choose a page.

### 4. The reader chooses a page to inspect

The reading prompt tells the agent:

> Use `scrape_url` on the most relevant URL above.

So the intended behavior is to select a relevant URL, rather than read all
search results. The model makes that choice from the evidence it receives; the
program does not contain a separate rule such as “always choose the first
URL.”

There is an important distinction: the pipeline invokes the reader agent once,
but it does not set a strict one-URL or one-tool-call limit inside that agent.
The instruction asks for the most relevant URL (singular), but the exact number
of `scrape_url` calls is not hard-coded by the pipeline. Therefore, the code
supports saying that the reader is **intended** to read one selected page; it
does not support promising that it can never request another page.

### 5. The scraper extracts text from a URL

For each URL the reader asks it to scrape, `scrape_url`:

- Fetches the page with an 8-second request timeout.
- Removes script, style, navigation, and footer elements.
- Extracts readable text from the remaining HTML.
- Returns at most the first 3,000 characters of that extracted text.

This is a basic page-text extraction, not a full browser. Pages can block the
request or have content that this extraction does not capture.

### 6. The writer uses both kinds of evidence

The pipeline combines the saved search findings and the reader's scraped
content, then gives both to the report writer:

```text
SEARCH RESULTS:
[search agent's findings]

DETAILED SCRAPED CONTENT:
[reader agent's response]
```

In everyday terms, search provides the **wider but brief overview**; deep
reading provides **more text from a page chosen for closer inspection**. The
final writer can use both. It is not limited to facts from only the selected
page.

## Process at a glance

```text
Your question
    ↓
Search agent → Tavily (up to 2 results per search-tool call)
    ↓
Search findings (the agent's response)
    ↓
Reader sees the first 800 characters of those findings
    ↓
Reader is instructed to choose the most relevant URL
    ↓
Scraper returns up to 3,000 characters of extracted page text per call
    ↓
Writer receives search findings + scraped reading
    ↓
Final report
```

## Bottom line

ResearchFlowAI does **not** have a rule saying “search exactly five websites”
or “read all search results.” Search requests up to two results per Tavily
tool call. The reader is directed to inspect the most relevant URL, which
suggests one page, but the pipeline does not strictly enforce exactly one
scrape call. The final report writer receives both the search findings and
the deeper-reading output.

## Where this behavior is defined

- [`tools.py`](./tools.py): Tavily result limit and page-text extraction.
- [`agents.py`](./agents.py): tools available to the search and reading agents.
- [`pipeline.py`](./pipeline.py): information passed between the workflow
  stages, including the 800-character reader context.
