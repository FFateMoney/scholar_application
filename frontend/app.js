const CONFIG = window.APP_CONFIG || {};
const state = {
  apiBaseUrl: CONFIG.apiBaseUrl || "http://127.0.0.1:8000",
  debugMode: Boolean(CONFIG.debugMode),
  pollIntervalMs: CONFIG.pollIntervalMs || 3000,
  activeTab: "idea",
  activeJobId: null,
  activeJobType: null,
  debugLogKey: "codex_stderr",
  pollTimer: null,
  currentInputSummary: "",
  currentOutputKey: null,
};

const elements = {
  backendUrl: document.getElementById("backend-url"),
  refreshHealth: document.getElementById("refresh-health"),
  healthDot: document.getElementById("health-dot"),
  healthText: document.getElementById("health-text"),
  ideaForm: document.getElementById("idea-form"),
  referenceForm: document.getElementById("reference-form"),
  tabButtons: Array.from(document.querySelectorAll(".tab-button[data-tab]")),
  tabPanels: Array.from(document.querySelectorAll(".tab-panel")),
  inputSummary: document.getElementById("input-summary"),
  outputMeta: document.getElementById("output-meta"),
  outputPreview: document.getElementById("output-preview"),
  outputShell: document.getElementById("output-shell"),
  timeline: document.getElementById("timeline"),
  jobBadge: document.getElementById("job-badge"),
  refreshJob: document.getElementById("refresh-job"),
  downloadLink: document.getElementById("download-link"),
  debugShell: document.getElementById("debug-shell"),
  debugEntry: document.getElementById("debug-entry"),
  toggleDebug: document.getElementById("toggle-debug"),
  debugOutput: document.getElementById("debug-output"),
  debugTabs: Array.from(document.querySelectorAll(".tab-button[data-debug-log]")),
};

function apiUrl(path) {
  return `${state.apiBaseUrl.replace(/\/$/, "")}${path}`;
}

async function request(path, options = {}) {
  const response = await fetch(apiUrl(path), options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response;
}

function setHealthStatus(kind, text) {
  elements.healthDot.classList.remove("online", "offline");
  if (kind) {
    elements.healthDot.classList.add(kind);
  }
  elements.healthText.textContent = text;
}

async function refreshHealth() {
  state.apiBaseUrl = elements.backendUrl.value.trim() || state.apiBaseUrl;
  try {
    const response = await request("/health");
    const payload = await response.json();
    setHealthStatus("online", `Backend ${payload.status}`);
  } catch (error) {
    setHealthStatus("offline", "Backend unreachable");
  }
}

function selectTab(tabName) {
  state.activeTab = tabName;
  for (const button of elements.tabButtons) {
    button.classList.toggle("active", button.dataset.tab === tabName);
  }
  for (const panel of elements.tabPanels) {
    panel.classList.toggle("active", panel.dataset.panel === tabName);
  }
}

function renderInputSummary(text) {
  state.currentInputSummary = text;
  elements.inputSummary.classList.remove("empty-state");
  elements.inputSummary.textContent = text;
}

function escapeHtml(text) {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderMarkdown(markdown) {
  const escaped = escapeHtml(markdown);
  const html = escaped
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    .replace(/^> (.+)$/gm, "<blockquote>$1</blockquote>")
    .replace(/```([\s\S]*?)```/g, "<pre><code>$1</code></pre>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/^- (.+)$/gm, "<li>$1</li>")
    .replace(/(<li>.*<\/li>)/gs, "<ul>$1</ul>")
    .replace(/\n{2,}/g, "</p><p>");
  return `<div class="rendered-markdown"><p>${html}</p></div>`;
}

function updateDownloadLink(artifactKey, filenameLabel) {
  state.currentOutputKey = artifactKey;
  if (!artifactKey) {
    elements.downloadLink.classList.add("disabled-link");
    elements.downloadLink.href = "#";
    elements.downloadLink.textContent = "Download";
    return;
  }
  elements.downloadLink.classList.remove("disabled-link");
  elements.downloadLink.href = apiUrl(`/jobs/${state.activeJobId}/files/${artifactKey}`);
  elements.downloadLink.textContent = filenameLabel || "Download";
}

function renderPlainOutput(text) {
  elements.outputShell.classList.remove("rendered");
  elements.outputPreview.classList.remove("empty-state");
  elements.outputPreview.textContent = text;
}

function renderRichOutput(markdown) {
  elements.outputShell.classList.add("rendered");
  elements.outputPreview.classList.remove("empty-state");
  elements.outputPreview.innerHTML = renderMarkdown(markdown);
}

async function loadOutputPreview(job) {
  const isIdea = job.job_type === "idea_report";
  const preferredKeys = isIdea
    ? ["reviewed_final_idea_report", "final_idea_report", "feasibility_report"]
    : ["references_bib"];
  const artifact = preferredKeys
    .map((key) => job.artifacts.find((item) => item.key === key))
    .find(Boolean);

  if (!artifact) {
    elements.outputMeta.textContent = "Primary output is not available yet.";
    renderPlainOutput("No output yet.");
    updateDownloadLink(null);
    return;
  }

  const label = artifact.key === "references_bib" ? "Download BibTeX" : "Download Markdown";
  updateDownloadLink(artifact.key, label);
  elements.outputMeta.textContent = `Loaded ${artifact.relative_path}`;

  try {
    const response = await request(`/jobs/${job.job_id}/files/${artifact.key}`);
    const text = await response.text();
    if (isIdea) {
      renderRichOutput(text);
    } else {
      renderPlainOutput(text);
    }
  } catch (error) {
    renderPlainOutput(String(error.message || error));
  }
}

function formatArtifacts(artifacts) {
  if (!artifacts.length) {
    return "No artifacts yet.";
  }
  return artifacts.map((item) => `${item.key} -> ${item.relative_path}`).join("\n");
}

function phaseDefinitions(jobType) {
  if (jobType === "reference_bib") {
    return [
      {
        key: "prepare",
        label: "解析输入",
        summary: "保存源文件、提取文本并生成检索查询。",
        stages: ["starting", "save_input", "extract_text", "codex_generate_queries"],
      },
      {
        key: "search",
        label: "爬取论文",
        summary: "检索论文并进行预筛、纠偏和短名单构建。",
        stages: [
          "citation_search",
          "citation_search_retry",
          "citation_prescreen",
          "citation_correct",
          "citation_shortlist",
        ],
      },
      {
        key: "deliver",
        label: "导出 BibTeX",
        summary: "汇总结果并写出最终的参考文献文件。",
        stages: ["write_bib", "completed"],
      },
    ];
  }

  return [
    {
      key: "plan",
      label: "规划 Idea",
      summary: "由 Codex 生成研究想法、claims 和检索 queries。",
      stages: ["starting", "codex_generate_inputs"],
    },
    {
      key: "search",
      label: "爬取论文",
      summary: "循环检索论文，直到失败队列清空，再完成预筛与 shortlist。",
      stages: [
        "citation_search",
        "citation_search_retry",
        "citation_prescreen",
        "citation_correct",
        "citation_shortlist",
      ],
    },
    {
      key: "synthesize",
      label: "整合报告",
      summary: "评估证据，先成稿，再由独立 reviewer 视角的 Codex 做二次修订。",
      stages: [
        "idea_assess",
        "report_render",
        "codex_generate_final_report",
        "codex_review_final_report",
        "completed",
      ],
    },
  ];
}

function phaseIndexForStage(phases, stage) {
  const index = phases.findIndex((phase) => phase.stages.includes(stage));
  return index >= 0 ? index : 0;
}

function phaseState(job, phases, index) {
  if (job.status === "failed") {
    const failedIndex = phaseIndexForStage(phases, job.stage);
    if (index < failedIndex) {
      return "completed";
    }
    if (index === failedIndex) {
      return "failed";
    }
    return "pending";
  }

  if (job.status === "succeeded") {
    return "completed";
  }

  const activeIndex = phaseIndexForStage(phases, job.stage);
  if (index < activeIndex) {
    return "completed";
  }
  if (index === activeIndex) {
    return "active";
  }
  return "pending";
}

function renderPhaseProgress(job) {
  const phases = phaseDefinitions(job.job_type);
  return phases
    .map((phase, index) => {
      const status = phaseState(job, phases, index);
      const currentStep = phase.stages.includes(job.stage) ? job.stage : phase.stages[0];
      const statusLabel =
        status === "completed"
          ? "Completed"
          : status === "active"
            ? "In Progress"
            : status === "failed"
              ? "Failed"
              : "Pending";

      return `
        <div class="phase-card ${status}">
          <div class="phase-header">
            <div class="phase-title-wrap">
              <div class="phase-index">0${index + 1}</div>
              <div>
                <div class="phase-title">${phase.label}</div>
                <div class="phase-summary">${phase.summary}</div>
              </div>
            </div>
            <div class="phase-status">${statusLabel}</div>
          </div>
          <div class="phase-step">
            ${status === "active" || status === "failed" ? `Current step: ${currentStep}` : `Stage group: ${phase.stages.join(", ")}`}
          </div>
        </div>
      `;
    })
    .join("");
}

function renderTimeline(job) {
  elements.timeline.classList.remove("empty-state");
  elements.timeline.innerHTML = `
    <div class="timeline-phases">
      ${renderPhaseProgress(job)}
    </div>
    <div class="timeline-item">
      <div class="timeline-stage">current stage</div>
      <div class="timeline-message">${job.stage}</div>
    </div>
    <div class="timeline-item">
      <div class="timeline-stage">backend message</div>
      <div class="timeline-message">${job.message || "No message"}</div>
    </div>
    <div class="timeline-item">
      <div class="timeline-stage">job status</div>
      <div class="timeline-message">${job.status}</div>
    </div>
    <div class="timeline-item">
      <div class="timeline-stage">updated</div>
      <div class="timeline-message">${job.updated_at}</div>
    </div>
    <div class="timeline-item">
      <div class="timeline-stage">artifacts</div>
      <div class="timeline-message"><pre class="output-preview">${formatArtifacts(job.artifacts)}</pre></div>
    </div>
  `;
}

function updateBadge(status) {
  elements.jobBadge.className = `job-badge ${status || "idle"}`;
  elements.jobBadge.textContent = status ? status.toUpperCase() : "No Active Job";
}

async function refreshDebugLog() {
  if (!state.debugMode || !state.activeJobId) {
    return;
  }
  try {
    const response = await request(
      `/jobs/${state.activeJobId}/logs/${state.debugLogKey}?tail=120`
    );
    const text = await response.text();
    elements.debugOutput.classList.toggle("empty-state", !text.trim());
    elements.debugOutput.textContent = text || "No log content yet.";
  } catch (error) {
    elements.debugOutput.textContent = String(error.message || error);
  }
}

async function refreshJob() {
  if (!state.activeJobId) {
    return;
  }
  try {
    const response = await request(`/jobs/${state.activeJobId}`);
    const job = await response.json();
    updateBadge(job.status);
    renderTimeline(job);
    await refreshDebugLog();

    if (job.status === "succeeded") {
      await loadOutputPreview(job);
      stopPolling();
    } else if (job.status === "failed") {
      elements.outputMeta.textContent = "Job failed.";
      renderPlainOutput(job.error || "Unknown failure.");
      updateDownloadLink(null);
      stopPolling();
    } else {
      const phaseLabel =
        phaseDefinitions(job.job_type)[phaseIndexForStage(phaseDefinitions(job.job_type), job.stage)]
          ?.label || "处理中";
      elements.outputMeta.textContent = `${phaseLabel} · ${job.message || job.stage}`;
    }
  } catch (error) {
    renderPlainOutput(String(error.message || error));
    stopPolling();
  }
}

function stopPolling() {
  if (state.pollTimer) {
    window.clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

function startPolling() {
  stopPolling();
  state.pollTimer = window.setInterval(refreshJob, state.pollIntervalMs);
}

async function submitIdeaForm(event) {
  event.preventDefault();
  const form = new FormData(elements.ideaForm);
  const payload = {
    brief: String(form.get("brief") || ""),
    language: String(form.get("language") || "zh"),
  };

  renderInputSummary(
    [
      "Idea Report",
      "",
      `Brief: ${payload.brief}`,
      `Language: ${payload.language}`,
    ].join("\n")
  );
  renderPlainOutput("Job submitted. Waiting for backend response...");
  elements.outputMeta.textContent = "Creating job...";
  updateDownloadLink(null);

  try {
    const response = await request("/jobs/idea-report", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    const job = await response.json();
    state.activeJobId = job.job_id;
    state.activeJobType = job.job_type;
    updateBadge(job.status);
    renderTimeline({
      ...job,
      artifacts: [],
      message: "Job created.",
      updated_at: new Date().toISOString(),
    });
    if (state.debugMode) {
      elements.debugEntry.classList.remove("hidden");
    }
    await refreshJob();
    startPolling();
  } catch (error) {
    renderPlainOutput(String(error.message || error));
    elements.outputMeta.textContent = "Job submission failed.";
  }
}

async function submitReferenceForm(event) {
  event.preventDefault();
  const formData = new FormData(elements.referenceForm);
  const file = formData.get("file");
  const language = String(formData.get("language") || "zh");

  if (!(file instanceof File) || !file.size) {
    renderPlainOutput("Please choose a .pdf, .tex, or .txt file.");
    return;
  }

  renderInputSummary(
    [
      "Reference Bib",
      "",
      `File: ${file.name}`,
      `Size: ${file.size} bytes`,
      `Language: ${language}`,
    ].join("\n")
  );
  renderPlainOutput("Job submitted. Waiting for backend response...");
  elements.outputMeta.textContent = "Uploading file...";
  updateDownloadLink(null);

  try {
    const response = await request("/jobs/reference-bib", {
      method: "POST",
      body: formData,
    });
    const job = await response.json();
    state.activeJobId = job.job_id;
    state.activeJobType = job.job_type;
    updateBadge(job.status);
    renderTimeline({
      ...job,
      artifacts: [],
      message: "Job created.",
      updated_at: new Date().toISOString(),
    });
    if (state.debugMode) {
      elements.debugEntry.classList.remove("hidden");
    }
    await refreshJob();
    startPolling();
  } catch (error) {
    renderPlainOutput(String(error.message || error));
    elements.outputMeta.textContent = "Upload failed.";
  }
}

function toggleDebugShell(forceOpen) {
  const shouldOpen =
    typeof forceOpen === "boolean" ? forceOpen : elements.debugShell.classList.contains("hidden");
  elements.debugShell.classList.toggle("hidden", !shouldOpen);
  elements.debugEntry.classList.toggle("hidden", shouldOpen || !state.debugMode);
}

function bindEvents() {
  elements.backendUrl.value = state.apiBaseUrl;
  elements.refreshHealth.addEventListener("click", refreshHealth);
  elements.ideaForm.addEventListener("submit", submitIdeaForm);
  elements.referenceForm.addEventListener("submit", submitReferenceForm);
  elements.refreshJob.addEventListener("click", refreshJob);

  for (const button of elements.tabButtons) {
    button.addEventListener("click", () => selectTab(button.dataset.tab));
  }

  for (const button of elements.debugTabs) {
    button.addEventListener("click", async () => {
      state.debugLogKey = button.dataset.debugLog;
      for (const peer of elements.debugTabs) {
        peer.classList.toggle("active", peer === button);
      }
      await refreshDebugLog();
    });
  }

  elements.debugEntry.addEventListener("click", () => toggleDebugShell(true));
  elements.toggleDebug.addEventListener("click", () => toggleDebugShell(false));
}

function initializeDebugMode() {
  if (!state.debugMode) {
    elements.debugShell.classList.add("hidden");
    elements.debugEntry.classList.add("hidden");
    return;
  }
  elements.debugEntry.classList.remove("hidden");
}

async function init() {
  bindEvents();
  initializeDebugMode();
  await refreshHealth();
  selectTab(state.activeTab);
}

init();
