const API = "";

const TOPO_POSITIONS = {
  "SERVER": [40, 130],
  "EDGE-MS": [155, 130],
  "CORE-R1": [270, 130],
  "CORE-R2": [385, 130],
  "CORE-R3": [500, 130],
  "CORE-R4": [600, 55],
  "CORE-R5": [600, 130],
  "CORE-R6": [600, 205],
};

let playing = false;
let playTimer = null;
let topologyData = null;
let charts = {};

function el(id) { return document.getElementById(id); }

async function api(path, opts) {
  const res = await fetch(API + path, opts);
  return res.json();
}

function fmt(n, digits = 2) {
  if (n === null || n === undefined || Number.isNaN(n)) return "--";
  if (typeof n !== "number") return n;
  return n.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function fmtThroughput(bps) {
  if (bps === null || bps === undefined) return "--";
  if (bps > 1e6) return (bps / 1e6).toFixed(2) + " Mbps";
  if (bps > 1e3) return (bps / 1e3).toFixed(2) + " kbps";
  return fmt(bps, 1) + " bps";
}

// ---------------------------------------------------------------- topology

async function loadTopology() {
  topologyData = await api("/api/topology");
  renderTopology(null, null);
}

function findPathEdges(edges, from, to) {
  if (!from || !to || from === to) return new Set();
  const adj = new Map();
  for (const e of edges) {
    if (!adj.has(e.source)) adj.set(e.source, []);
    if (!adj.has(e.target)) adj.set(e.target, []);
    adj.get(e.source).push(e.target);
    adj.get(e.target).push(e.source);
  }
  const prev = new Map([[from, null]]);
  const queue = [from];
  while (queue.length) {
    const node = queue.shift();
    if (node === to) break;
    for (const nb of adj.get(node) || []) {
      if (!prev.has(nb)) { prev.set(nb, node); queue.push(nb); }
    }
  }
  const pathNodes = [];
  let cur = to;
  while (cur !== undefined && cur !== null) { pathNodes.push(cur); cur = prev.get(cur); }
  const pathEdgeKeys = new Set();
  for (let i = 0; i < pathNodes.length - 1; i++) {
    const a = pathNodes[i], b = pathNodes[i + 1];
    pathEdgeKeys.add(a + "|" + b);
    pathEdgeKeys.add(b + "|" + a);
  }
  return pathEdgeKeys;
}

function renderTopology(currentDevice, rootCauseDevice) {
  if (!topologyData) return;
  const svg = el("topology-svg");
  const parts = [];
  const affectedEdgeKeys = findPathEdges(topologyData.edges, currentDevice, rootCauseDevice);

  for (const edge of topologyData.edges) {
    const [x1, y1] = TOPO_POSITIONS[edge.source] || [0, 0];
    const [x2, y2] = TOPO_POSITIONS[edge.target] || [0, 0];
    const affected = affectedEdgeKeys.has(edge.source + "|" + edge.target);
    parts.push(`<line class="topo-edge${affected ? " affected" : ""}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" />`);
  }

  for (const node of topologyData.nodes) {
    const [x, y] = TOPO_POSITIONS[node.id] || [0, 0];
    let fill = "#263048";
    let stroke = "#3a4666";
    if (node.id === rootCauseDevice) { fill = "#ef4444"; stroke = "#ef4444"; }
    else if (node.id === currentDevice) { fill = "#6366f1"; stroke = "#6366f1"; }
    parts.push(`
      <g class="topo-node">
        <circle cx="${x}" cy="${y}" r="22" fill="${fill}" stroke="${stroke}" />
        <text x="${x}" y="${y + 38}" text-anchor="middle">${node.id}</text>
      </g>
    `);
  }
  svg.innerHTML = parts.join("");
}

// ------------------------------------------------------------------ charts

function makeChart(ctx, label, color) {
  return new Chart(ctx, {
    type: "line",
    data: { labels: [], datasets: [{ label, data: [], borderColor: color, backgroundColor: color + "33", tension: 0.25, pointRadius: 0 }] },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      scales: {
        x: { ticks: { color: "#93a0bb", maxTicksLimit: 6 }, grid: { color: "#263048" } },
        y: { ticks: { color: "#93a0bb" }, grid: { color: "#263048" }, beginAtZero: true },
      },
      plugins: { legend: { labels: { color: "#e7ecf5" } } },
    },
  });
}

function initCharts() {
  charts.loss = makeChart(el("chart-loss"), "Packet Loss (%)", "#ef4444");
  charts.latency = makeChart(el("chart-latency"), "Latency (ms)", "#eab308");
  charts.throughput = makeChart(el("chart-throughput"), "Throughput (bps)", "#3b82f6");
  charts.prob = makeChart(el("chart-prob"), "Fault Probability", "#6366f1");
}

function updateCharts(history) {
  const labels = history.map(h => new Date(h.timestamp * 1000).toLocaleTimeString());
  const set = (chart, values) => {
    chart.data.labels = labels;
    chart.data.datasets[0].data = values;
    chart.update("none");
  };
  set(charts.loss, history.map(h => h.icmp_loss));
  set(charts.latency, history.map(h => h.icmp_response_time));
  set(charts.throughput, history.map(h => h.throughput_bps));
  set(charts.prob, history.map(h => h.fault_probability));
}

// ------------------------------------------------------------------ render

function statusClass(status) {
  return "status-" + (status || "normal").toLowerCase();
}

function render(data) {
  if (!data) return;

  const banner = el("status-banner");
  banner.className = "status-banner " + statusClass(data.status);
  el("status-text").textContent = (data.status || "NORMAL").replace("_", " ");
  const prog = data.progress || {};
  el("status-meta").textContent = data.timestamp
    ? `${data.device || ""} @ ${new Date(data.timestamp * 1000).toLocaleString()}  (${prog.pointer || 0}/${prog.total || 0})`
    : "";

  const m = data.metrics || {};
  el("m-loss").textContent = m.icmp_loss !== undefined ? fmt(m.icmp_loss, 1) + " %" : "--";
  el("m-latency").textContent = m.icmp_response_time !== undefined ? fmt(m.icmp_response_time, 2) + " ms" : "--";
  el("m-throughput").textContent = m.throughput_bps !== undefined ? fmtThroughput(m.throughput_bps) : "--";
  el("m-discards").textContent = m.discards_total !== undefined ? fmt(m.discards_total, 0) : "--";
  el("m-errors").textContent = m.errors_total !== undefined ? fmt(m.errors_total, 0) : "--";
  el("m-operstatus").textContent = m.oper_status_up_frac !== undefined ? fmt(m.oper_status_up_frac * 100, 0) + "% up" : "--";

  const pred = data.prediction || {};
  const prob = pred.fault_probability || 0;
  const threshold = pred.threshold !== undefined ? pred.threshold : 0.5;
  el("prob-fill").style.width = (prob * 100).toFixed(1) + "%";
  el("threshold-marker").style.left = (threshold * 100).toFixed(1) + "%";
  el("prob-value").textContent = (prob * 100).toFixed(1) + "%";
  el("threshold-value").textContent = "threshold: " + (threshold * 100).toFixed(0) + "%";
  el("pred-result").textContent = pred.prediction || "--";
  el("pred-truth").textContent = data.ground_truth_class || "--";
  el("pred-truth-target").textContent = data.ground_truth_class_at_target || "--";

  const rca = data.rca;
  el("rca-empty").classList.toggle("hidden", !!rca);
  el("rca-body").classList.toggle("hidden", !rca);
  let rootCauseDevice = null;
  if (rca) {
    el("rca-device").textContent = rca.affected_device;
    el("rca-interface").textContent = rca.affected_interface || "--";
    el("rca-faulttype").textContent = rca.probable_fault_type;
    el("rca-rootcause").textContent = rca.root_cause;
    el("rca-confidence").textContent = rca.confidence;
    el("rca-method").textContent = rca.rca_method || "rules";
    el("rca-tag").textContent = (rca.rca_method || "").startsWith("ml") ? "ML classifier + rule evidence" : "rule-based, no ML";
    el("rca-probs").textContent = (rca.fault_type_probabilities || [])
      .map(p => `${p.fault_type} ${(p.probability * 100).toFixed(0)}%`).join(", ") || "--";
    el("rca-evidence").innerHTML = (rca.evidence || []).map(e => `<li>${e}</li>`).join("");
    rootCauseDevice = rca.root_cause_device || rca.affected_device;
  }

  renderTopology(data.device, rootCauseDevice);

  if (data.history && data.history.length) {
    updateCharts(data.history);
  }

  if (data.finished) {
    setPlaying(false);
  }
}

// ---------------------------------------------------------------- controls

async function doTick() {
  const data = await api("/api/tick", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ steps: 1 }),
  });
  render(data);
}

function setPlaying(value) {
  playing = value;
  el("btn-play").textContent = playing ? "Pause" : "Play";
  if (playTimer) { clearInterval(playTimer); playTimer = null; }
  if (playing) {
    playTimer = setInterval(doTick, 1000);
  }
}

async function doReset(device) {
  setPlaying(false);
  const data = await api("/api/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(device ? { device } : {}),
  });
  charts.loss.data.labels = []; charts.loss.data.datasets[0].data = [];
  charts.latency.data.labels = []; charts.latency.data.datasets[0].data = [];
  charts.throughput.data.labels = []; charts.throughput.data.datasets[0].data = [];
  charts.prob.data.labels = []; charts.prob.data.datasets[0].data = [];
  Object.values(charts).forEach(c => c.update("none"));
  render(data);
}

async function init() {
  initCharts();
  await loadTopology();

  const health = await api("/api/health");
  if (!health.ready) {
    el("status-text").textContent = "BACKEND NOT READY";
    el("status-meta").textContent = health.error || "Model not trained yet.";
    return;
  }

  const devicesResp = await api("/api/devices");
  const select = el("device-select");
  select.innerHTML = devicesResp.devices.map(d => `<option value="${d}">${d}</option>`).join("");
  select.value = devicesResp.current_device;

  const initialState = await api("/api/state");
  render(initialState);

  el("btn-step").addEventListener("click", doTick);
  el("btn-play").addEventListener("click", () => setPlaying(!playing));
  el("btn-reset").addEventListener("click", () => doReset(select.value));
  select.addEventListener("change", () => doReset(select.value));
}

init();
