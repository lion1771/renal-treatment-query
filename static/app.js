const state = {
  query: "",
  selectedDisease: null,
  currentIntent: "overview",
  searchTimer: null,
  sectionLabels: {},
};

const intentPrompts = {
  overview: "有哪些治疗方案？",
  classic: "经典治疗或一线处理是什么？",
  new: "有没有新药、生物制剂或靶向治疗？",
  evidence: "关键证据、RCT 或指南来源是什么？",
  safety: "哪些治疗不推荐？",
};

const statusLabels = {
  recommended: "推荐",
  conditional: "条件性推荐",
  alternative: "替代方案",
  exploratory: "探索性",
  not_recommended: "不推荐",
  rescue_only: "仅限抢救/难治",
  supportive_only: "仅支持/基础治疗",
};

const coverageLabels = {
  query_ready: "可查询",
  query_ready_with_caveats: "可查询，含提示",
  covered_by_parent_package: "由上级治疗包覆盖",
};

const els = {
  searchPane: document.querySelector(".search-pane"),
  reloadButton: document.querySelector("#reloadButton"),
  queryInput: document.querySelector("#queryInput"),
  resultCount: document.querySelector("#resultCount"),
  statusText: document.querySelector("#statusText"),
  diseaseList: document.querySelector("#diseaseList"),
  emptyState: document.querySelector("#emptyState"),
  queryResult: document.querySelector("#queryResult"),
  matchBadge: document.querySelector("#matchBadge"),
  diseaseTitle: document.querySelector("#diseaseTitle"),
  intentLine: document.querySelector("#intentLine"),
  countPanel: document.querySelector("#countPanel"),
  sectionNav: document.querySelector("#sectionNav"),
  quickGlance: document.querySelector("#quickGlance"),
  sectionsRoot: document.querySelector("#sectionsRoot"),
};

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

async function init() {
  bindEvents();
  await loadHealth();
  renderDiseaseList([]);
  updateStickyOffset();
  if (!window.matchMedia("(max-width: 820px)").matches) {
    els.queryInput.focus();
  }
}

function bindEvents() {
  window.addEventListener("resize", updateStickyOffset);
  window.visualViewport?.addEventListener("resize", updateStickyOffset);

  els.queryInput.addEventListener("input", () => {
    state.query = els.queryInput.value.trim();
    document.body.classList.remove("has-result");
    updateStickyOffset();
    window.clearTimeout(state.searchTimer);
    state.searchTimer = window.setTimeout(() => {
      runDiseaseSearch(state.query);
      if (state.query) {
        runQuery(state.query);
      } else {
        renderEmpty();
      }
    }, 140);
  });

  els.reloadButton.addEventListener("click", async () => {
    els.statusText.textContent = "重载中";
    await getJson("/api/reload");
    await loadHealth();
    await runDiseaseSearch(state.query);
    if (state.query) {
      await runQuery(state.query);
    }
    els.statusText.textContent = "";
  });

  document.querySelectorAll(".intent-button").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".intent-button").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      state.currentIntent = button.dataset.intent;
      const base = state.selectedDisease?.name_cn || state.selectedDisease?.requested_name || state.query;
      if (!base) {
        return;
      }
      const query = `${base} ${intentPrompts[state.currentIntent]}`;
      els.queryInput.value = query;
      state.query = query;
      runQuery(query);
    });
  });
}

function updateStickyOffset() {
  const height = Math.ceil(els.searchPane?.getBoundingClientRect().height || 0);
  document.documentElement.style.setProperty("--sticky-offset", `${height}px`);
}

async function loadHealth() {
  try {
    const data = await getJson("/api/health");
    state.sectionLabels = data.section_labels || {};
  } catch (error) {
    els.statusText.textContent = "索引载入失败";
    els.statusText.classList.add("danger");
  }
}

async function runDiseaseSearch(query) {
  if (!query.trim()) {
    renderDiseaseList([]);
    return;
  }
  try {
    const data = await getJson(`/api/diseases?q=${encodeURIComponent(query)}&limit=10`);
    renderDiseaseList(data.items || []);
  } catch (error) {
    els.statusText.textContent = "疾病列表载入失败";
  }
}

async function runQuery(query) {
  els.statusText.textContent = "查询中";
  try {
    const data = await getJson(`/api/query?q=${encodeURIComponent(query)}`);
    renderQueryResult(data);
    els.statusText.textContent = "";
  } catch (error) {
    els.statusText.textContent = "查询失败";
  }
}

function renderDiseaseList(items) {
  els.resultCount.textContent = items.length ? "已匹配病种" : "输入后匹配病种";
  els.diseaseList.innerHTML = "";
  for (const item of items) {
    const li = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = `disease-button${state.selectedDisease?.disease_key === item.disease_key ? " active" : ""}`;
    button.dataset.key = item.disease_key;
    button.innerHTML = `
      <span class="disease-name">${escapeHtml(item.name_cn || item.requested_name || item.disease_key)}</span>
    `;
    button.addEventListener("click", () => selectDisease(item));
    li.appendChild(button);
    els.diseaseList.appendChild(li);
  }
}

function selectDisease(item) {
  state.selectedDisease = item;
  document.querySelectorAll(".disease-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.key === item.disease_key);
  });
  const query = `${item.name_cn || item.requested_name || item.disease_key} ${intentPrompts[state.currentIntent]}`;
  els.queryInput.value = query;
  state.query = query;
  runQuery(query);
}

function renderEmpty() {
  document.body.classList.remove("has-result");
  els.emptyState.hidden = false;
  els.queryResult.hidden = true;
  els.quickGlance.hidden = true;
}

function renderQueryResult(payload) {
  const result = payload.result || {};
  const route = payload.route || {};
  const modules = payload.modules || result.modules || [];
  const matched = route.matched ?? Boolean(result.matches && result.matches.length);
  if (!matched) {
    document.body.classList.remove("has-result");
    els.emptyState.hidden = false;
    els.queryResult.hidden = true;
    els.emptyState.querySelector("h2").textContent = "未匹配到治疗包";
    const warning = (payload.warnings || [])[0]?.message;
    els.emptyState.querySelector("p").textContent = warning || "请换用疾病全名、英文缩写或常用别名。";
    return;
  }

  const match = (route.matches || result.matches || [])[0] || {};
  const selected = payload.disease || payload.selected_disease;
  state.selectedDisease = selected || state.selectedDisease;
  document.body.classList.add("has-result");
  els.emptyState.hidden = true;
  els.queryResult.hidden = false;

  els.matchBadge.textContent = coverageLabels[match.coverage_status] || "可查询";
  els.diseaseTitle.textContent = selected?.name_cn || match.requested_name || match.registry_id;
  const queryContext = payload.query_context || result;
  const intent = (queryContext.detected_intent_labels || []).join("、") || "治疗总览";
  els.intentLine.textContent = intent;
  renderCounts(selected);
  renderSections(modules);
  window.requestAnimationFrame(updateStickyOffset);
}

function renderCounts(selected) {
  const counts = selected?.clinical_counts || {};
  const items = [
    ["证据来源", counts.evidence_studies],
    ["指南建议", counts.guideline_recommendations],
    ["医保标注", counts.payer_status],
  ].filter(([, value]) => Number(value) > 0);
  els.countPanel.innerHTML = items
    .map(([label, value]) => `<span class="count-item"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></span>`)
    .join("");
}

function renderSections(modules) {
  els.sectionNav.innerHTML = "";
  els.quickGlance.innerHTML = "";
  els.quickGlance.hidden = true;
  els.sectionsRoot.innerHTML = "";
  const allSections = [];
  for (const module of modules) {
    if (!module.sections || !module.sections.length) {
      const empty = document.createElement("div");
      empty.className = "empty-section";
      empty.textContent = "当前问题没有匹配到单独治疗方案；请切换总览或查看其他治疗层。";
      els.sectionsRoot.appendChild(empty);
      continue;
    }
    for (const section of module.sections) {
      allSections.push(section);
    }
  }

  renderQuickGlance(allSections);

  for (const section of allSections) {
    const chip = document.createElement("a");
    chip.className = "section-chip";
    chip.href = `#section-${section.query_section}`;
    chip.textContent = section.label_cn || sectionLabel(section.query_section);
    els.sectionNav.appendChild(chip);
  }

  for (const section of allSections) {
    const block = document.createElement("section");
    block.className = "section-block";
    block.id = `section-${section.query_section}`;
    block.innerHTML = `
      <div class="section-heading">
        <h3>${escapeHtml(section.label_cn || sectionLabel(section.query_section))}</h3>
      </div>
      <div class="cards-grid"></div>
    `;
    const grid = block.querySelector(".cards-grid");
    for (const card of section.cards) {
      grid.appendChild(renderCard(card));
    }
    els.sectionsRoot.appendChild(block);
  }
}

function renderQuickGlance(sections) {
  const priority = [
    "supportive_foundation",
    "classic_regimens",
    "new_targeted_regimens",
    "special_scenarios",
    "not_recommended",
    "exploratory_regimens",
  ];
  const ordered = [...sections].sort((a, b) => {
    const left = priority.indexOf(a.query_section);
    const right = priority.indexOf(b.query_section);
    return (left === -1 ? 99 : left) - (right === -1 ? 99 : right);
  });
  const items = ordered
    .map((section) => {
      const card = (section.cards || [])[0];
      if (!card) {
        return null;
      }
      const label = section.label_cn || sectionLabel(section.query_section);
      const title = cleanText(card.regimen_name || card.regimen_id);
      const line = cleanText(card.evidence_summary || card.clinical_scenario || card.duration_summary || card.safety_summary);
      return { section, label, title, line };
    })
    .filter(Boolean)
    .slice(0, 5);

  if (!items.length) {
    return;
  }

  els.quickGlance.hidden = false;
  els.quickGlance.innerHTML = `
    <div class="quick-glance-head">
      <span>速览</span>
      <strong>${escapeHtml(items.length)} 条主线</strong>
    </div>
    <div class="quick-glance-list">
      ${items
        .map(
          (item) => `
            <a class="quick-glance-item" href="#section-${escapeHtml(item.section.query_section)}">
              <span>${escapeHtml(item.label)}</span>
              <strong>${escapeHtml(item.title)}</strong>
              ${item.line ? `<small>${escapeHtml(item.line)}</small>` : ""}
            </a>
          `
        )
        .join("")}
    </div>
  `;
}

function renderCard(card) {
  const article = document.createElement("article");
  article.className = "treatment-card";
  const status = card.recommendation_status || "";
  const statusClass = status === "not_recommended" ? " danger" : ["exploratory", "rescue_only"].includes(status) ? " warning" : "";
  const primaryRows = [
    ["剂量", card.dose_summary],
    ["疗程", card.duration_summary],
    ["证据", card.evidence_summary],
  ];
  if (status === "not_recommended") {
    primaryRows.push(["安全", card.safety_summary]);
  }
  const secondaryRows = [
    ["机制", card.mechanism_summary],
    ["指南", card.guideline_summary],
    ["安全", status === "not_recommended" ? "" : card.safety_summary],
    ["医保", card.local_status_summary],
  ];
  const secondaryFacts = factRows(secondaryRows);
  article.innerHTML = `
    <div class="card-head">
      <h4>${escapeHtml(card.regimen_name || card.regimen_id)}</h4>
      <span class="status-pill${statusClass}">${escapeHtml(statusLabels[status] || status || "方案")}</span>
    </div>
    ${card.clinical_scenario ? `<div class="scenario">${escapeHtml(card.clinical_scenario)}</div>` : ""}
    <dl class="fact-list fact-list-primary">
      ${factRows(primaryRows)}
    </dl>
    ${
      secondaryFacts
        ? `<details class="card-details">
            <summary>机制、指南与安全</summary>
            <dl class="fact-list fact-list-secondary">${secondaryFacts}</dl>
          </details>`
        : ""
    }
  `;

  const drilldown = buildDrilldown(card);
  if (drilldown) {
    article.appendChild(drilldown);
  }
  return article;
}

function buildDrilldown(card) {
  const evidence = card.evidence_drilldown || [];
  const guidelines = card.guideline_drilldown || [];
  const sources = card.source_drilldown || [];
  if (!evidence.length && !guidelines.length && !sources.length) {
    return null;
  }
  const details = document.createElement("details");
  details.className = "drilldown";
  details.innerHTML = `<summary>证据与来源</summary><div class="drilldown-list"></div>`;
  const list = details.querySelector(".drilldown-list");

  for (const item of evidence) {
    const div = document.createElement("div");
    div.className = "drilldown-item";
    const pmid = cleanText(item.pmid);
    const studyName = cleanText(item.study_name || item.study_id || "研究");
    const design = cleanText(item.design);
    const structuredSummary = item.structured_summary_cn || {};
    const resultSummary = cleanText(item.result_summary);
    const treatmentImpact = cleanText(item.treatment_impact);
    const digestRows = [
      ["研究问题", structuredSummary.research_question],
      ["设计", structuredSummary.design],
      ["人群", structuredSummary.population],
      ["干预/对照", structuredSummary.intervention_comparator],
      ["终点", structuredSummary.endpoint],
      ["结果", structuredSummary.results],
      ["安全", structuredSummary.safety],
      ["治疗影响", structuredSummary.treatment_impact],
    ]
      .map(([label, value]) => [label, cleanText(value)])
      .filter(([, value]) => value)
      .map(([label, value]) => ({ label, value }));
    const essentialLabels = new Set(["设计", "结果", "安全", "治疗影响"]);
    const essentialRows = digestRows
      .filter((row) => essentialLabels.has(row.label))
      .map(digestRow)
      .join("");
    const fullRows = digestRows
      .filter((row) => !essentialLabels.has(row.label))
      .map(digestRow)
      .join("");
    div.innerHTML = `
      <strong>${escapeHtml(studyName)}</strong>
      ${design ? ` · ${escapeHtml(design)}` : ""}
      ${pmid ? ` · PMID ${escapeHtml(pmid)}` : ""}
      ${
        essentialRows
          ? `<div class="evidence-digest">${essentialRows}</div>${
              fullRows
                ? `<details class="digest-more"><summary>完整研究摘要</summary><div class="evidence-digest evidence-digest-full">${fullRows}</div></details>`
                : ""
            }`
          : resultSummary
            ? `<br>${escapeHtml(resultSummary)}`
            : ""
      }
      ${treatmentImpact && !cleanText(structuredSummary.treatment_impact) ? `<br><span>${escapeHtml(treatmentImpact)}</span>` : ""}
    `;
    list.appendChild(div);
  }

  for (const item of guidelines) {
    const div = document.createElement("div");
    div.className = "drilldown-item";
    const organization = cleanText([item.organization, item.year].filter(Boolean).join(" ") || item.guideline_id || "指南");
    const grade = cleanText(item.grade);
    const recommendationText = cleanText(item.recommendation_text);
    div.innerHTML = `
      <strong>${escapeHtml(organization)}</strong>
      ${grade ? ` · ${escapeHtml(grade)}` : ""}
      ${recommendationText ? `<br>${escapeHtml(recommendationText)}` : ""}
    `;
    list.appendChild(div);
  }

  if (!evidence.length && !guidelines.length) {
    for (const item of sources.slice(0, 3)) {
      const div = document.createElement("div");
      div.className = "drilldown-item";
      div.textContent = cleanText(item.title || item.source_id || "来源");
      list.appendChild(div);
    }
  }

  return details;
}

function factRow(label, value) {
  const text = cleanText(value);
  if (!text) {
    return "";
  }
  return `<div class="fact-row"><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(text)}</dd></div>`;
}

function factRows(rows) {
  return rows.map(([label, value]) => factRow(label, value)).join("");
}

function digestRow(row) {
  return `<div class="evidence-digest-row"><span>${escapeHtml(row.label)}</span><p>${escapeHtml(row.value)}</p></div>`;
}

function sectionLabel(section) {
  return state.sectionLabels[section] || section;
}

function cleanText(value) {
  if (value === null || value === undefined) {
    return "";
  }
  const text = String(value).trim();
  if (!text || ["not_applicable", "not_available", "pending_lookup", "unknown"].includes(text)) {
    return "";
  }
  return text
    .replace(/\bnot_applicable\b|\bnot_available\b|\bpending_lookup\b/g, "")
    .replace(/《肾脏病学》第\s*4\s*版/g, "《肾脏病学》第四版")
    .replace(/治疗卡/g, "治疗方案")
    .replace(/卡片/g, "方案")
    .replace(/(《肾脏病学》第四版[^，。；;]*)\s*(?:已完成|完成)?(?:本地)?\s*(?:合并稿|清洗稿)?/g, "$1")
    .replace(/\s+([,.;:，。；：])/g, "$1")
    .replace(/([（(])\s+/g, "$1")
    .replace(/\s+([）)])/g, "$1")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

init();
