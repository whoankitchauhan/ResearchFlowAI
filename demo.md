# A Real ResearchFlowAI Run, Explained Simply

This walkthrough is based on the real console output shared for this run. The
topic was:

> **How are cities adapting their power grids for extreme heat?**

It explains what the log shows, what the code does, and what cannot be known
from this log alone.

## The short version

- The pipeline started **one research job** and invoked the search agent once.
- The search agent's final **SEARCH RESULTS** summary listed **six sources**.
- The code asks Tavily for **up to two results per `web_search` tool call**.
  The pasted log does not show the raw tool calls, so it does not prove exactly
  how many Tavily searches the agent made.
- The reader's final **SCRAPED CONTENT** summary focused on **one article**:
  the Niskanen Center article about transmission infrastructure and extreme
  heat.
- The report writer then received **both** the search summary and the deep
  reading summary.

## Step by step

### 1. The question entered the research pipeline

The console shows this topic:

> How are cities adapting their power grids for extreme heat?

The web application starts one job for that question. The many `GET /api/jobs/...`
lines in the log are the page checking the job's progress; they are **not**
additional web searches.

### 2. The search agent was asked to research it

The pipeline sent the topic to the search agent and asked it to prefer recent,
reliable sources and return findings with dates, titles, and URLs.

The **SEARCH RESULTS** printed in the log listed these six sources:

1. **Niskanen Center** — “How transmission infrastructure can mitigate
   blackouts during extreme heat”
   - https://www.niskanencenter.org/how-transmission-infrastructure-can-mitigate-blackouts-during-extreme-heat
2. **Uplight** — “3 Ways to Boost Grid Resilience During Heat Waves”
   - https://uplight.com/blog/3-ways-to-boost-grid-resilience-during-heat-waves
3. **Con Edison** — “Climate Change Vulnerability Study – Summary”
4. **Arizona Office of Resilience** — “Extreme Heat Preparedness Plan”
   - https://resilient.az.gov/sites/default/files/2024-07/extreme-heat-preparedness-plan-2024-03-1.pdf
5. **Peer-reviewed article** — “Compound Climate and Infrastructure Events:
   How Electrical Grid Failure Alters Heat-Wave Risk”
   - https://pmc.ncbi.nlm.nih.gov/articles/PMC9882910
6. **Global Heat Health Information Network (GHIN)** — “Heat Action Plans &
   Case Studies”
   - https://heathealth.info/heat-action-plans-and-case-studies

Those are the six sources shown in the search agent's final summary. This is
not the same thing as a record of every result Tavily returned or every search
request made.

### 3. What “how many searches?” means here

There are two different counts:

- **Search-agent runs:** The pipeline invokes the search agent once for this
  job.
- **Tavily searches:** Inside that agent run, the model can call the
  `web_search` tool. Each such call asks Tavily for **up to two results**.

The log shows six sources in the agent's final summary, but it does not show
the tool-call trace. Therefore, we cannot say from this log whether the agent
made exactly three Tavily calls, more than three, or how the six entries map
to individual tool responses. **If** all six were separate results returned
by Tavily, at least three calls would be needed at two results per call. That
is a conditional calculation, not a confirmed call count.

### 4. The reader got only part of the search summary

Before calling the reader, the pipeline passes it:

1. The same research question.
2. The **first 800 characters** of the search agent's final summary.

It does not pass all six full source descriptions to the reader. In this run,
the Niskanen Center URL appears near the start of the search summary, so that
URL was available in the text the reader received.

### 5. The reader focused on the Niskanen Center article

The reader prompt says to use `scrape_url` on the **most relevant URL** in the
search evidence. The run's **SCRAPED CONTENT** section is an evidence summary
for this one article:

> “How transmission infrastructure can mitigate blackouts during extreme
> heat” — Niskanen Center, 3 August 2023

URL:
https://www.niskanencenter.org/how-transmission-infrastructure-can-mitigate-blackouts-during-extreme-heat

The summary discusses heat-related grid stress, transmission upgrades, and
limits in the available evidence. In simple terms, search gave the project a
broader overview; the reader then examined one relevant source in greater
depth.

The code invokes the reader agent once and instructs it to use the most
relevant URL. It does not impose a hard technical limit on how many times the
reader may call its scrape tool. For this run, the visible reader summary is
about one source; the pasted log does not show raw scrape-tool calls.

### 6. A note about the “Jina AI” statement in the reader output

The reader's summary says the page returned **403 Forbidden** to a direct
request and that the content was retrieved through a **Jina AI** summarizer.
That is what the reader's printed summary claims.

However, the `scrape_url` implementation currently in the project makes a
direct HTTP request to the supplied URL. It does not contain code for a Jina
proxy. The pasted output does not include raw tool-call results that could
verify that Jina was actually used. So treat the Jina detail as **a claim in
the model's summary, not a confirmed action by the current scraper code**.

The current scraper is configured to request the URL with an 8-second timeout,
remove script, style, navigation, and footer elements, and return at most the
first 3,000 characters of extracted page text. If a request fails, the tool
returns an error message.

### 7. The report writer received both sets of information

The pipeline combines the two outputs in this shape:

```text
SEARCH RESULTS:
[the search agent's summary, listing six sources]

DETAILED SCRAPED CONTENT:
[the reader agent's Niskanen Center summary]
```

So the report was **not based only on the Niskanen article**. The writer was
given the wider six-source search summary as well as the deeper-reading
summary. It then produced a report about grid adaptations, findings, evidence
gaps, and references.

The six entries and their descriptions are what the search agent printed.
They should not automatically be treated as independently verified facts:
the log does not include the raw Tavily responses, and the reader's own output
also notes that some evidence was not captured.

## The process in one picture

```text
Question:
"How are cities adapting their power grids for extreme heat?"
                         ↓
One search-agent run
                         ↓
Final search summary lists six sources
(Tavily is configured for up to two results per tool call;
the exact number of tool calls is not recorded here)
                         ↓
Reader receives question + first 800 characters of that summary
                         ↓
Reader summary focuses on the Niskanen Center article
                         ↓
Writer receives both summaries and creates the report
```

## What we can and cannot conclude from this run

| Question | What the evidence says |
|---|---|
| What was researched? | “How are cities adapting their power grids for extreme heat?” |
| How many sources appeared in search findings? | Six source entries appeared in the search agent's final summary. |
| How many Tavily calls were made? | Not recorded in the pasted log. Each call is configured for up to two results. |
| What did the reader focus on? | Its printed summary is about the Niskanen Center article. |
| Did the writer only use that one article? | No. The pipeline passed both the search summary and the reader summary to the writer. |
| Was Jina AI definitely used by the scraper? | The reader summary says so, but current `scrape_url` code does not implement Jina, and the raw tool trace is absent. |

## Where the behavior comes from

- [`pipeline.py`](./pipeline.py) starts the search and reader agents, passes
  the first 800 characters of search findings to the reader, and combines both
  outputs for the writer.
- [`tools.py`](./tools.py) sets Tavily's maximum to two results per search
  call and implements direct URL extraction.
- [`agents.py`](./agents.py) gives the search and reader agents access to
  their respective tools.
