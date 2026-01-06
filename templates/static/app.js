let pollTimer = null;
let charts = {};

const el = (id) => document.getElementById(id);

function setProgress(pct, step) {
  el("progressText").textContent = `${pct}%`;
  el("progressFill").style.width = `${pct}%`;
  el("stepText").textContent = step || "…";
}

function chips(status, step) {
  const c = el("chips");
  c.innerHTML = "";
  const mk = (txt) => {
    const s = document.createElement("span");
    s.className = "badge ok";
    s.textContent = txt;
    return s;
  };
  const mk2 = (txt) => {
    const s = document.createElement("span");
    s.className = "badge bad";
    s.textContent = txt;
    return s;
  };
  if (status === "done") c.appendChild(mk("DONE"));
  else if (status === "running") c.appendChild(mk("RUNNING"));
  else if (status === "error") c.appendChild(mk2("ERROR"));
  if (step) c.appendChild(mk(step));
}

function renderSources(items=[]) {
  const list = el("sourceList");
  list.innerHTML = "";
  let ok = 0, bad = 0;
  items.forEach(it => {
    const div = document.createElement("div");
    div.className = "sourceItem";

    const top = document.createElement("div");
    top.className = "sourceTop";

    const url = document.createElement("div");
    url.className = "sourceUrl";
    url.textContent = it.url;

    const badge = document.createElement("div");
    badge.className = "badge " + (it.ok ? "ok" : "bad");
    badge.textContent = it.ok ? "OK" : "BLOCKED/ERROR";

    top.appendChild(url);
    top.appendChild(badge);

    const prev = document.createElement("div");
    prev.className = "sourcePreview";
    prev.textContent = it.preview || "";

    div.appendChild(top);
    div.appendChild(prev);
    list.appendChild(div);

    if (it.ok) ok++; else bad++;
  });

  el("okCount").textContent = ok;
  el("badCount").textContent = bad;
}

function kpiCards(masters, overallRate) {
  const grid = el("kpiGrid");
  grid.innerHTML = "";

  const order = [
    "Core Sentiment",
    "Positivity",
    "Negativity",
    "Intensity & Risk",
    "Topics & Aspects",
    "Volume & Coverage",
    "Predictive Analysis"
  ];

  order.forEach(name => {
    const data = masters[name] || {};
    const card = document.createElement("div");
    card.className = "kpiCard";
    card.innerHTML = `
      <div class="kpiStripe"></div>
      <div class="kpiName">${name}</div>
      <div class="kpiValue">${name === "Core Sentiment" ? overallRate : pickValue(data)}</div>
      <div class="kpiTag">Click to open details</div>
    `;
    card.addEventListener("click", () => openModal(name, data, overallRate));
    grid.appendChild(card);
  });
}

function pickValue(obj) {
  const keys = Object.keys(obj || {});
  if (!keys.length) return "—";
  const k = keys[0];
  const v = obj[k];
  if (typeof v === "number") return String(v);
  if (typeof v === "string") return v;
  if (Array.isArray(v)) return `${v.length} items`;
  return "View";
}

function openModal(title, data, overallRate) {
  el("modalTitle").textContent = title;
  el("modalSub").textContent = "Master KPI details & sub-KPIs";

  const body = el("modalBody");
  body.innerHTML = "";

  if (title === "Predictive Analysis") {
    body.innerHTML = `
      <div class="kv"><div class="k">Overall Sentiment Rate</div><div class="v">${overallRate}</div></div>
      <div style="margin-top:10px;display:flex;gap:10px;flex-wrap:wrap">
        <button class="btn primary" id="btnPredict">Generate Top 5 Actions</button>
        <div class="hint">Actions are sorted: most urgent → least urgent.</div>
      </div>
      <div id="predOut" style="margin-top:12px"></div>
    `;

    setTimeout(() => {
      const b = document.getElementById("btnPredict");
      b.addEventListener("click", async () => {
        b.disabled = true;
        b.textContent = "Generating…";
        const res = await fetch("/api/predictive", { method: "POST", headers: {"Content-Type":"application/json"}, body: "{}" });
        const j = await res.json();
        const out = document.getElementById("predOut");
        if (!j.ok) {
          out.innerHTML = `<div class="badge bad">Error: ${j.error || "Failed"}</div>`;
        } else {
          out.innerHTML = `<ul class="list">${
            (j.actions || []).map(a => `
              <li>
                <div style="font-weight:900">${a.rank}. ${a.title} <span class="badge ok" style="margin-left:8px">${a.urgency}</span></div>
                <div style="margin-top:6px;color:rgba(234,240,255,.85)">${a.why}</div>
                <div style="margin-top:8px;display:flex;gap:10px;flex-wrap:wrap">
                  <span class="badge ok">Uplift: +${a.expected_uplift_points} pts</span>
                  <span class="badge ok">Horizon: ${a.time_horizon}</span>
                </div>
                <div style="margin-top:8px;color:rgba(234,240,255,.8)">
                  KPIs impacted: ${(a.kpis_impacted || []).join(", ")}
                </div>
              </li>
            `).join("")
          }</ul>`;
        }
        b.disabled = false;
        b.textContent = "Generate Top 5 Actions";
      });
    }, 0);
  } else {
    // Render KV rows
    Object.entries(data || {}).forEach(([k, v]) => {
      const row = document.createElement("div");
      row.className = "kv";
      const kk = document.createElement("div");
      kk.className = "k";
      kk.textContent = k;

      const vv = document.createElement("div");
      vv.className = "v";
      vv.textContent = (typeof v === "object") ? JSON.stringify(v, null, 2) : String(v);

      row.appendChild(kk);
      row.appendChild(vv);
      body.appendChild(row);
    });
  }

  el("modal").classList.add("show");
}

function closeModal() {
  el("modal").classList.remove("show");
}

el("modalClose").addEventListener("click", closeModal);
el("modal").addEventListener("click", (e) => {
  if (e.target.id === "modal") closeModal();
});

function initCharts() {
  charts.sent = echarts.init(el("chartSentDist"));
  charts.gauge = echarts.init(el("chartRateGauge"));

  charts.sent.setOption({
    title: { text: "Sentiment Distribution", left: "center", textStyle:{color:"#eaf0ff"} },
    tooltip: { trigger: "item" },
    series: [{
      type: "pie",
      radius: ["50%","75%"],
      avoidLabelOverlap: true,
      label: { color:"#eaf0ff" },
      data: [
        { value: 0, name: "Positive" },
        { value: 0, name: "Negative" },
        { value: 0, name: "Neutral" }
      ]
    }]
  });

  charts.gauge.setOption({
    title: { text: "Overall Sentiment Rate", left: "center", textStyle:{color:"#eaf0ff"} },
    series: [{
      type: "gauge",
      min: 0,
      max: 100,
      progress: { show: true, width: 12 },
      axisLine: { lineStyle: { width: 12 } },
      detail: { valueAnimation: true, formatter: "{value}%", color:"#eaf0ff" },
      data: [{ value: 0 }]
    }]
  });

  window.addEventListener("resize", () => {
    Object.values(charts).forEach(c => c.resize());
  });
}

function updateCharts(series, rate) {
  const sd = series?.sentiment_distribution || {pos:0,neg:0,neu:0};
  charts.sent.setOption({
    series: [{
      data: [
        { value: sd.pos, name: "Positive" },
        { value: sd.neg, name: "Negative" },
        { value: sd.neu, name: "Neutral" }
      ]
    }]
  });
  charts.gauge.setOption({
    series: [{ data: [{ value: rate || 0 }] }]
  });
}

async function run() {
  const company = el("company").value.trim();
  const hints = el("hints").value.trim();
  const maxLinks = parseInt(el("maxLinks").value || "12", 10);

  if (!company) return alert("Enter company name.");

  el("btnRun").disabled = true;
  setProgress(1, "Starting…");

  const res = await fetch("/api/run", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ company, hints, max_links: maxLinks })
  });

  const j = await res.json();
  if (!j.ok) {
    el("btnRun").disabled = false;
    return alert(j.error || "Failed to start.");
  }

  // poll status
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    const r = await fetch("/api/status");
    const s = await r.json();

    chips(s.status, s.step);
    setProgress(s.progress || 0, s.step || "");

    el("linksCount").textContent = (s.urls || []).length;

    if (Array.isArray(s.items)) {
      renderSources(s.items);
    }

    if (s.dashboard) {
      const d = s.dashboard;
      el("sentimentRate").textContent = d.overall_sentiment_rate ?? "—";
      kpiCards(d.masters || {}, d.overall_sentiment_rate ?? 0);
      updateCharts(d.series || {}, d.overall_sentiment_rate ?? 0);
    }

    if (s.status === "done" || s.status === "error") {
      clearInterval(pollTimer);
      pollTimer = null;
      el("btnRun").disabled = false;
      if (s.status === "error") alert(s.error || "Error occurred.");
    }
  }, 900);
}

el("btnRun").addEventListener("click", run);

async function exportDashboardZip() {
  const zip = new JSZip();

  // Capture charts panel + KPI panel + sources
  const targets = [
    { id: "chartsPanel", name: "charts.png" },
    { id: "kpiGrid", name: "kpis.png" },
    { id: "sourceList", name: "sources.png" }
  ];

  for (const t of targets) {
    const node = document.getElementById(t.id);
    if (!node) continue;
    const canvas = await html2canvas(node, { backgroundColor: null, scale: 2 });
    const blob = await new Promise(resolve => canvas.toBlob(resolve, "image/png"));
    zip.file(t.name, blob);
  }

  const blob = await zip.generateAsync({ type: "blob" });
  saveAs(blob, "dashboard_export.zip");
}

el("btnExport").addEventListener("click", exportDashboardZip);

initCharts();
