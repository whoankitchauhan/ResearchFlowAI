"use strict";

const form = document.querySelector("#research-form");
const topicInput = document.querySelector("#topic");
const submitButton = document.querySelector("#submit-button");
const runPanel = document.querySelector("#run-panel");
const runTitle = document.querySelector("#run-title");
const runStatus = document.querySelector("#run-status");
const progressTrack = document.querySelector(".progress-track");
const progressBar = document.querySelector("#progress-bar");
const progressValue = document.querySelector("#progress-value");
const stageCaption = document.querySelector("#stage-caption");
const errorMessage = document.querySelector("#error-message");
const results = document.querySelector("#results");
const resultContent = document.querySelector("#result-content");
const documentLabel = document.querySelector("#document-label");
const actionFeedback = document.querySelector("#action-feedback");
const serviceDot = document.querySelector("#service-dot");
const serviceLabel = document.querySelector("#service-label");

const stageNames = {
  queued: "Waiting for an available researcher",
  search: "Searching for relevant, recent sources",
  reading: "Reading a source in greater depth",
  writing: "Synthesizing the research into a report",
  reviewing: "Critically reviewing the report",
  completed: "Research run complete",
};
const outputLabels = {
  search_results: "SEARCH FINDINGS",
  scraped_content: "DEEP READING",
  report: "FINAL REPORT",
  feedback: "CRITICAL REVIEW",
};
let currentJobId = null;
let currentResult = null;
let selectedOutput = "report";
let pollTimer = null;

function setServiceState(online) {
  serviceDot.classList.toggle("online", online);
  serviceDot.classList.toggle("offline", !online);
  serviceDot.classList.remove("checking");
  serviceLabel.textContent = online ? "Research service ready" : "Research service unavailable";
}

function appendInlineMarkdown(parent, text) {
  const tokenPattern = /(\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)|\*\*([^*]+)\*\*|__([^_]+)__|`([^`]+)`|\*([^*\n]+)\*|_([^_\n]+)_)/g;
  let lastIndex = 0;
  let match;

  while ((match = tokenPattern.exec(text)) !== null) {
    parent.append(document.createTextNode(text.slice(lastIndex, match.index)));
    if (match[2] !== undefined) {
      const link = document.createElement("a");
      link.href = match[3];
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = match[2];
      parent.append(link);
    } else {
      const element = document.createElement(match[4] !== undefined || match[5] !== undefined
        ? "strong"
        : match[6] !== undefined ? "code" : "em");
      element.textContent = match[4] ?? match[5] ?? match[6] ?? match[7] ?? match[8];
      parent.append(element);
    }
    lastIndex = tokenPattern.lastIndex;
  }

  parent.append(document.createTextNode(text.slice(lastIndex)));
}

function splitTableRow(line) {
  const value = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  const cells = [];
  let cell = "";
  let escaped = false;

  for (const character of value) {
    if (character === "|" && !escaped) {
      cells.push(cell.trim());
      cell = "";
    } else {
      cell += character;
    }
    escaped = character === "\\" && !escaped;
    if (character !== "\\") escaped = false;
  }

  cells.push(cell.trim());
  return cells;
}

function isTableSeparator(line) {
  const cells = splitTableRow(line);
  return cells.length > 1 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function isBlockStart(lines, index) {
  const line = lines[index];
  return /^ {0,3}(?:#{1,6}\s|```|~~~|>|[-*+]\s|\d+[.)]\s)/.test(line)
    || /^ {0,3}(?:[-*_]\s*){3,}$/.test(line)
    || (line.includes("|") && index + 1 < lines.length && isTableSeparator(lines[index + 1]));
}

function renderMarkdown(markdown) {
  const lines = String(markdown).replace(/\r\n?/g, "\n").split("\n");
  resultContent.replaceChildren();
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    const fence = line.match(/^ {0,3}(```|~~~)(.*)$/);
    if (fence) {
      const codeLines = [];
      index += 1;
      while (index < lines.length && !new RegExp(`^ {0,3}${fence[1]}`).test(lines[index])) {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      const pre = document.createElement("pre");
      const code = document.createElement("code");
      code.textContent = codeLines.join("\n");
      pre.append(code);
      resultContent.append(pre);
      continue;
    }

    const heading = line.match(/^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$/);
    if (heading) {
      const element = document.createElement(`h${heading[1].length}`);
      appendInlineMarkdown(element, heading[2]);
      resultContent.append(element);
      index += 1;
      continue;
    }

    if (line.includes("|") && index + 1 < lines.length && isTableSeparator(lines[index + 1])) {
      const headers = splitTableRow(line);
      const wrapper = document.createElement("div");
      wrapper.className = "result-table-wrap";
      const table = document.createElement("table");
      const thead = document.createElement("thead");
      const headerRow = document.createElement("tr");
      headers.forEach((value) => {
        const cell = document.createElement("th");
        appendInlineMarkdown(cell, value);
        headerRow.append(cell);
      });
      thead.append(headerRow);
      table.append(thead);
      const tbody = document.createElement("tbody");
      index += 2;
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
        const values = splitTableRow(lines[index]);
        if (values.length > headers.length) {
          values.splice(headers.length - 1, values.length - headers.length + 1,
            values.slice(headers.length - 1).join(" | "));
        }
        const row = document.createElement("tr");
        headers.forEach((_, column) => {
          const cell = document.createElement("td");
          appendInlineMarkdown(cell, values[column] || "");
          row.append(cell);
        });
        tbody.append(row);
        index += 1;
      }
      table.append(tbody);
      wrapper.append(table);
      resultContent.append(wrapper);
      continue;
    }

    const listMatch = line.match(/^ {0,3}([-*+]|\d+[.)])\s+(.+)$/);
    if (listMatch) {
      const ordered = /^\d/.test(listMatch[1]);
      const list = document.createElement(ordered ? "ol" : "ul");
      while (index < lines.length) {
        const itemMatch = lines[index].match(/^ {0,3}([-*+]|\d+[.)])\s+(.+)$/);
        if (!itemMatch || /^\d/.test(itemMatch[1]) !== ordered) break;
        const item = document.createElement("li");
        appendInlineMarkdown(item, itemMatch[2]);
        list.append(item);
        index += 1;
      }
      resultContent.append(list);
      continue;
    }

    if (/^ {0,3}>/.test(line)) {
      const quote = document.createElement("blockquote");
      while (index < lines.length && /^ {0,3}>/.test(lines[index])) {
        const paragraph = document.createElement("p");
        appendInlineMarkdown(paragraph, lines[index].replace(/^ {0,3}> ?/, ""));
        quote.append(paragraph);
        index += 1;
      }
      resultContent.append(quote);
      continue;
    }

    if (/^ {0,3}(?:[-*_]\s*){3,}$/.test(line)) {
      resultContent.append(document.createElement("hr"));
      index += 1;
      continue;
    }

    const paragraph = document.createElement("p");
    const paragraphLines = [line.trim()];
    index += 1;
    while (index < lines.length && lines[index].trim() && !isBlockStart(lines, index)) {
      paragraphLines.push(lines[index].trim());
      index += 1;
    }
    appendInlineMarkdown(paragraph, paragraphLines.join(" "));
    resultContent.append(paragraph);
  }
}

async function checkService() {
  try {
    const response = await fetch("/api/health");
    if (!response.ok) throw new Error("Service check failed");
    setServiceState(true);
  } catch {
    setServiceState(false);
  }
}

function renderProgress(job) {
  runPanel.hidden = false;
  const progress = Math.max(0, Math.min(100, job.progress || 0));
  progressBar.style.width = `${progress}%`;
  progressValue.textContent = `${progress}%`;
  progressTrack.setAttribute("aria-valuenow", String(progress));
  stageCaption.textContent = stageNames[job.stage] || "Research in progress";
  runTitle.textContent = job.topic;
  runStatus.className = `run-status${job.status === "failed" ? " failed" : ""}${job.status === "completed" ? " completed" : ""}`;
  runStatus.innerHTML = `<span class="status-pulse"></span>${job.status === "failed" ? "Needs attention" : job.status === "completed" ? "Complete" : job.status === "queued" ? "Queued" : "In progress"}`;

  const stageOrder = ["search", "reading", "writing", "reviewing"];
  const currentIndex = stageOrder.indexOf(job.stage);
  document.querySelectorAll(".stage-list li").forEach((item) => {
    const index = stageOrder.indexOf(item.dataset.stage);
    item.classList.toggle("active", job.status !== "failed" && index === currentIndex);
    item.classList.toggle("done", job.status === "completed" || (currentIndex >= 0 && index < currentIndex));
  });

  if (job.status === "failed") {
    errorMessage.textContent = job.error || "Research could not be completed. Please try again.";
    errorMessage.hidden = false;
    submitButton.disabled = false;
    submitButton.querySelector("span").textContent = "Try again";
  }
}

function showOutput(key) {
  if (!currentResult || !(key in currentResult)) return;
  selectedOutput = key;
  renderMarkdown(currentResult[key] || "No content was returned for this stage.");
  documentLabel.textContent = outputLabels[key] || key.toUpperCase();
  actionFeedback.textContent = "";
  document.querySelectorAll(".result-tab").forEach((tab) => {
    const selected = tab.dataset.result === key;
    tab.classList.toggle("selected", selected);
    tab.setAttribute("aria-pressed", String(selected));
  });
}

function showResults(job) {
  currentResult = job.result;
  results.hidden = false;
  showOutput("report");
  submitButton.disabled = false;
  submitButton.querySelector("span").textContent = "Start another run";
}

function stopPolling() {
  if (pollTimer !== null) {
    window.clearTimeout(pollTimer);
    pollTimer = null;
  }
}

async function pollJob(jobId) {
  if (jobId !== currentJobId) return;
  try {
    const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`);
    const job = await response.json();
    if (!response.ok) throw new Error(job.detail || "Could not retrieve this research run.");
    renderProgress(job);
    if (job.status === "completed") {
      stopPolling();
      sessionStorage.removeItem("researchflowai-active-job");
      showResults(job);
      return;
    }
    if (job.status === "failed") {
      stopPolling();
      sessionStorage.removeItem("researchflowai-active-job");
      return;
    }
  } catch (error) {
    stopPolling();
    sessionStorage.removeItem("researchflowai-active-job");
    errorMessage.textContent = error.message || "Unable to reconnect to the research run.";
    errorMessage.hidden = false;
    runPanel.hidden = false;
    runStatus.className = "run-status failed";
    runStatus.innerHTML = '<span class="status-pulse"></span>Connection lost';
    submitButton.disabled = false;
    submitButton.querySelector("span").textContent = "Try again";
    return;
  }
  pollTimer = window.setTimeout(() => pollJob(jobId), 1400);
}

async function startJob(topic) {
  stopPolling();
  currentResult = null;
  currentJobId = null;
  selectedOutput = "report";
  results.hidden = true;
  errorMessage.hidden = true;
  runPanel.hidden = false;
  progressBar.style.width = "0%";
  progressValue.textContent = "0%";
  progressTrack.setAttribute("aria-valuenow", "0");
  stageCaption.textContent = "Sending your research question";
  runTitle.textContent = topic;
  runStatus.className = "run-status";
  runStatus.innerHTML = '<span class="status-pulse"></span>Starting';
  document.querySelectorAll(".stage-list li").forEach((item) => item.classList.remove("active", "done"));
  submitButton.disabled = true;
  submitButton.querySelector("span").textContent = "Starting research…";

  try {
    const response = await fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic }),
    });
    const job = await response.json();
    if (!response.ok) {
      const detail = Array.isArray(job.detail)
        ? job.detail.map((issue) => issue.msg).join(" ")
        : job.detail;
      throw new Error(detail || "Could not start the research run.");
    }
    currentJobId = job.id;
    sessionStorage.setItem("researchflowai-active-job", job.id);
    renderProgress(job);
    pollJob(job.id);
  } catch (error) {
    runPanel.hidden = false;
    errorMessage.textContent = error.message || "Unable to start research. Check the service connection and try again.";
    errorMessage.hidden = false;
    runStatus.className = "run-status failed";
    runStatus.innerHTML = '<span class="status-pulse"></span>Could not start';
    submitButton.disabled = false;
    submitButton.querySelector("span").textContent = "Try again";
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  startJob(topicInput.value.trim());
});

topicInput.addEventListener("input", () => {
  document.querySelector("#char-count").textContent = `${topicInput.value.length} / 500`;
});

document.querySelectorAll(".suggestion").forEach((button) => {
  button.addEventListener("click", () => {
    topicInput.value = button.dataset.topic;
    topicInput.dispatchEvent(new Event("input"));
    topicInput.focus();
  });
});

document.querySelectorAll(".result-tab").forEach((button) => {
  button.addEventListener("click", () => showOutput(button.dataset.result));
});

document.querySelector("#copy-button").addEventListener("click", async () => {
  if (!currentResult || !currentResult[selectedOutput]) return;
  try {
    await navigator.clipboard.writeText(currentResult[selectedOutput]);
    actionFeedback.textContent = "Copied";
  } catch {
    actionFeedback.textContent = "Clipboard unavailable";
  }
});

document.querySelector("#download-button").addEventListener("click", () => {
  if (!currentResult || !currentResult[selectedOutput]) return;
  const blob = new Blob([currentResult[selectedOutput]], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `ResearchFlowAI-${selectedOutput}.md`;
  link.click();
  URL.revokeObjectURL(url);
});

checkService();
window.setInterval(checkService, 30000);

const savedJobId = sessionStorage.getItem("researchflowai-active-job");
if (savedJobId) {
  currentJobId = savedJobId;
  runPanel.hidden = false;
  submitButton.disabled = true;
  submitButton.querySelector("span").textContent = "Research in progress…";
  pollJob(savedJobId);
}
