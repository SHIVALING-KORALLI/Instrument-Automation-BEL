// gui/static/script.js (index.js)
"use strict";

const statusEl = document.getElementById("status");
const psuIdEl = document.getElementById("psu_idn");
const psu2IdEl = document.getElementById("psu2_idn");   // new
const genIdEl = document.getElementById("gen_idn");
const saIdEl = document.getElementById("sa_idn");
let lastReportPath = null;
let statusInterval = null;

// ---------- SSE log handling (replace/merge) ----------
function startLogStream() {
  try {
    const es = new EventSource("/api/logs");
    es.onmessage = (ev) => {
      try {
        const obj = JSON.parse(ev.data);
        appendLog(obj);
      } catch (e) {
        appendLog({ts: new Date().toISOString(), msg: ev.data});
      }
    };
    es.onerror = (e) => {
      appendLog({ts: new Date().toISOString(), level: "warn", msg: "Log stream disconnected."});
      es.close();
      // reconnect after short delay
      setTimeout(startLogStream, 1000);
    };
  } catch (e) {
    appendLog({ts: new Date().toISOString(), level: "error", msg: "SSE not supported."});
  }
}

function appendLog(obj) {
  const ts = obj.ts || new Date().toISOString();
  const type = obj.type ? `[${obj.type}] ` : "";
  const msg = obj.message || obj.msg || "";

  const line = `[${ts}] ${type}${msg || JSON.stringify(obj)}`;
  statusEl.textContent += "\n" + line;
  statusEl.scrollTop = statusEl.scrollHeight;

  // handle automation progress structure (sent as {type: 'automation_progress', data: {...}})
  if (obj.type === "automation_progress" && obj.data) {
    updateAutomationStatus(obj.data);
  } else if (obj.type === "automation_start") {
    document.getElementById("automation_status").textContent = "Starting...";
    document.getElementById("automation_metrics").textContent = obj.message || "Initializing...";
  } else if (obj.type === "automation_complete") {
    document.getElementById("automation_status").textContent = "Completed";
    document.getElementById("automation_metrics").innerHTML =
      `<span style="color: #4CAF50;">✓ ${obj.message || 'Done'}</span>`;
    if (obj.report) {
      lastReportPath = obj.report;
    }
  } else if (obj.type === "automation_error") {
    document.getElementById("automation_status").textContent = "Error";
    document.getElementById("automation_metrics").innerHTML =
      `<span style="color: #f44336;">✗ ${obj.message || 'Error'}</span>`;
  }
}

// ---------- Show automation progress and metrics ----------
function updateAutomationStatus(data) {
  const statusDiv = document.getElementById("automation_status");
  const metricsDiv = document.getElementById("automation_metrics");

  if (!data) return;

  if (data.status === "running") {
    const done = data.current || 0;
    const total = data.total || 1;
    const percentage = Math.round((done / total) * 100);
    const board = data.board_no ? `Board ${data.board_no}` : "";
    const channel = data.channel_no ? `Ch ${data.channel_no}` : "";
    const spotHex = data.hex || "";
    const freq = data.freq_mhz ? `${(data.freq_mhz/1000).toFixed(3)} GHz` : (data.freq_hz ? `${data.freq_hz/1e9} GHz` : "");
    statusDiv.textContent = `Running: ${board} | ${channel} | Spot ${spotHex} | ${freq}`;

    metricsDiv.innerHTML = `
      <div style="margin-bottom:6px;">
        <strong>${done} / ${total}</strong>
      </div>
      <div style="background: #172033; border-radius: 4px; height: 14px; overflow: hidden;">
        <div style="background: linear-gradient(90deg,#4CAF50,#8BC34A); width:${percentage}%; height:100%;"></div>
      </div>
      <div style="margin-top:6px; font-size:0.9em; color:#94a3b8;">
        ${data.message || ''}
      </div>
    `;
  } else if (data.status === "completed") {
    statusDiv.textContent = `Completed: Board ${data.board_no} Ch ${data.channel_no}`;
    metricsDiv.innerHTML = `<div style="color:#4CAF50;font-weight:bold;">✓ ${data.message || 'Complete'}</div>`;
  } else if (data.status === "error") {
    statusDiv.textContent = `Error`;
    metricsDiv.innerHTML = `<div style="color:#f44336;">✗ ${data.message || 'Error'}</div>`;
  }
}

// ---------- Run Automation (send JSON with new inputs) ----------
async function runAutomation() {
  document.getElementById("automation_status").textContent = "Starting...";
  document.getElementById("automation_metrics").textContent = "Preparing automation sequence...";

  // read inputs
  const board_no = parseInt(document.getElementById("dtrc_board").value || "1", 10);
  const channel_no = parseInt(document.getElementById("dtrc_channel").value || "1", 10);
  const pulse = (document.getElementById("dtrc_pulse").value || "").trim();
  const prt = (document.getElementById("dtrc_prt").value || "").trim();

  const body = {
    board_no: board_no,
    channel_no: channel_no,
    pulse_width: pulse,
    prt: prt
  };

  try {
    const res = await fetch("/api/run", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body)
    });
    const j = await res.json();

    if (j.status === "ok") {
      appendLog({ts: new Date().toISOString(), type: "automation_result", msg: `Automation finished. Report: ${j.report}`});
      // lastReportPath updated via SSE automation_complete event too
      lastReportPath = j.report || lastReportPath;
    } else {
      appendLog({ts: new Date().toISOString(), type: "automation_error", msg: j.message || "Automation failed"});
    }
  } catch (e) {
    appendLog({ts: new Date().toISOString(), type: "automation_error", msg: e.toString()});
  }
}

/* async function downloadLatestReport() {
  if (!lastReportPath) {
    appendLog({ts: new Date().toISOString(), msg: "No report available yet."});
    return;
  }
  window.open("/" + lastReportPath, "_blank");
} */

async function downloadLatestReport() {
  window.open("/reports/latest", "_blank");
}


function clearLog() {
  statusEl.textContent = "Ready...";
}

// ----------------- Discovery & Attach -----------------
async function doDiscover() {
  const res = await fetch("/api/discover");
  const j = await res.json();
  appendLog(j);
  if (j.status === "ok") {
    const ul = document.getElementById("resources_list");
    ul.innerHTML = "";
    (j.resources || []).forEach(r => {
      const li = document.createElement("li");
      li.textContent = r;
      li.onclick = () => {
        document.getElementById("resource_input").value = r;
      };
      ul.appendChild(li);
    });
  }
}

async function attachManual(name) {
  const resource = document.getElementById("resource_input").value;
  if (!resource) { appendLog({ts: new Date().toISOString(), msg: "Paste a resource string first."}); return; }
  const res = await fetch("/api/attach", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({name, resource})
  });
  const j = await res.json();
  appendLog(j);
  if (j.status === "ok") {
    if (name === "psu") psuIdEl.textContent = j.idn;
    if (name === "gen") genIdEl.textContent = j.idn;
    if (name === "sa") saIdEl.textContent = j.idn;
  }
}

async function attachAuto(name) {
  const res = await fetch("/api/attach", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({name, resource: "auto"})
  });
  const j = await res.json();
  appendLog(j);
  if (j.status === "ok") {
    if (name === "psu") psuIdEl.textContent = j.idn;
    if (name === "psu2") psu2IdEl.textContent = j.idn;  // new
    if (name === "gen") genIdEl.textContent = j.idn;
    if (name === "sa") saIdEl.textContent = j.idn;
  }
}

// ----------------- PSU -----------------
async function setPSU(name = "psu") {
  let v = parseFloat(document.getElementById(`${name}_voltage`).value || 0);
  let c = parseFloat(document.getElementById(`${name}_current`).value || 0);

  // --- Safety limits (adjust as per your PSU ratings) ---
  const MAX_VOLTAGE = 13.0;

  if (v > MAX_VOLTAGE) {
    alert(`⚠ Voltage limited to ${MAX_VOLTAGE} V for safety.`);
    v = MAX_VOLTAGE;
    document.getElementById(`${name}_voltage`).value = v;
  }
  if (v < 0) v = 0;

  const res = await fetch("/api/psu/set", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({name, voltage: v, current: c})
  });
  appendLog(await res.json());
  refreshStatus();
}

async function psuOutput(name = "psu", state = "on") {
  const res = await fetch("/api/psu/output", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({name, state})
  });
  appendLog(await res.json());
  refreshStatus();

  if (state === "on") {
    // start polling every 2 seconds
    if (!statusInterval) {
      statusInterval = setInterval(refreshStatus, 2000);
    }
  } else {
    // stop polling
    if (statusInterval) {
      clearInterval(statusInterval);
      statusInterval = null;
    }
  }
}

// ----------------- Generator -----------------
async function setGen() {
  const f = parseFloat(document.getElementById("gen_freq").value || 0);
  const p = parseFloat(document.getElementById("gen_power").value || 0);
  const res = await fetch("/api/gen/set", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({frequency: f*1000000, power: p})
  });
  appendLog(await res.json());
  refreshStatus();
}
async function genRF(state) {
  const res = await fetch("/api/gen/rf", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({state})
  });
  appendLog(await res.json());
  refreshStatus();
}

// ----------------- Analyzer -----------------
async function setSA() {
  const c = parseFloat(document.getElementById("sa_center").value || 0);
  const s = parseFloat(document.getElementById("sa_span").value || 0);
  const r = parseFloat(document.getElementById("sa_rbw").value || 0);
  const res = await fetch("/api/sa/set", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({center: c*1000000, span: s*1000000, rbw: r*1000})
  });
  appendLog(await res.json());
  refreshStatus();
}

async function readMarker() {
  const res = await fetch("/api/sa/marker");
  const j = await res.json();
  appendLog(j);  // still keep in log for debugging
  if (j.status === "ok") {
    const msg = `Marker: ${j.freq_hz} Hz, ${j.power_dbm} dBm`;
    appendLog({ts: new Date().toISOString(), msg: msg});
    document.getElementById("sa_marker_value").textContent =
      `${(j.freq_hz/1e6).toFixed(3)} MHz, ${j.power_dbm.toFixed(2)} dBm`;
  } else {
    document.getElementById("sa_marker_value").textContent = "—";
  }
}

async function getScreenshot() {
  const res = await fetch("/api/sa/screenshot");
  const j = await res.json();
  appendLog(j);
  if (j.status === "ok") {
    const url = "/" + j.file;
    document.getElementById("sa_screen").src = url;
    document.getElementById("sa_screen").style.display = "block";
  }
}

// ----------------- Analyzer trace & screenshot -----------------
async function getTrace() {
  appendLog({ts: new Date().toISOString(), msg: "Requesting trace..."});
  const res = await fetch("/api/sa/trace");
  const j = await res.json();
  appendLog(j);
  if (j.status === "ok") {
    if (j.format === "list") {
      // create CSV and trigger download
      const csv = j.data.join("\n");
      const blob = new Blob([csv], {type: "text/csv"});
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "trace.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      appendLog({ts: new Date().toISOString(), msg: "Trace downloaded (trace.csv)."});
    } else if (j.format === "base64") {
      appendLog({ts: new Date().toISOString(), msg: "Trace returned as base64; see log for details."});
    }
  } else {
    appendLog({ts: new Date().toISOString(), level: "error", msg: j.message || "Trace fetch failed"});
  }
}

// Analyzer amplitude / reference level control
async function saAmp(action, step = 10.0) {
  const res = await fetch("/api/sa/amp", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({action, step})
  });
  if (!res.ok) {
    appendLog({ts: new Date().toISOString(), level: "error", msg: "HTTP error " + res.status});
    return;
  }
  const j = await res.json();
  appendLog(j);
  if (j.status === "ok") {
    refreshStatus();
  }
}

async function saTraceClear() {
  appendLog({ts: new Date().toISOString(), msg: "Clearing trace..."});
  const res = await fetch("/api/sa/trace_clear", {method: "POST"});
  const j = await res.json();
  appendLog(j);
}

async function saTraceMax() {
  appendLog({ts: new Date().toISOString(), msg: "Setting trace to Max Hold..."});
  const res = await fetch("/api/sa/trace_max", {method: "POST"});
  const j = await res.json();
  appendLog(j);
}

// ----------------- Open/Close All + refresh status -----------------
async function openAll() {
  const res = await fetch("/api/close_all", { method: "POST" }); // close to reset
  appendLog(await res.json());
  // Then attempt auto attach all (safer path)
  await attachAuto("psu");
  await attachAuto("psu2");  // new
  await attachAuto("gen");
  await attachAuto("sa");
  await loadInstruments(); // 🔥 ensures GUI reflects IDNs
  refreshStatus();
}

async function closeAll() {
  const res = await fetch("/api/close_all", { method: "POST" });
  appendLog(await res.json());
  psuIdEl.textContent = "(not attached)";
  psu2IdEl.textContent = "(not attached)";
  genIdEl.textContent = "(not attached)";
  saIdEl.textContent = "(not attached)";
  refreshStatus();
}

async function refreshStatus() {
  const res = await fetch("/api/status");
  const j = await res.json();
  appendLog(j);
  if (j.status === "ok") {
    const s = j.data;
    if (s.psu) {
      document.getElementById("psu_info").textContent = `Voltage: ${s.psu.voltage} V | Current: ${s.psu.current} A`;
    }
    if (s.psu2) {
      document.getElementById("psu2_info").textContent = `Voltage: ${s.psu2.voltage} V | Current: ${s.psu2.current} A`;
    }
    if (s.gen) {
      document.getElementById("gen_info").textContent = `Freq: ${s.gen.frequency} Hz | Power: ${s.gen.power} dBm | RF: ${s.gen.rf}`;
    }
    if (s.sa) {
      // do nothing else
    }
  }
}

async function loadInstruments() {
  try {
    const res = await fetch("/api/instruments");
    const j = await res.json();
    if (j.status === "error") {
      appendLog(j);
      return;
    }
    if (j.psu) document.getElementById("psu_idn").textContent = j.psu;
    if (j.psu2) document.getElementById("psu2_idn").textContent = j.psu2;
    if (j.gen) document.getElementById("gen_idn").textContent = j.gen;
    if (j.sa) document.getElementById("sa_idn").textContent = j.sa;
    appendLog({ ts: new Date().toISOString(), msg: "Instruments synced." });
  } catch (e) {
    appendLog({ ts: new Date().toISOString(), level: "error", msg: "Failed to load instruments: " + e });
  }
}

// Initialize UI
/* document.addEventListener("DOMContentLoaded", () => {
  startLogStream();
  // show default tab content (not hidden)
  document.querySelectorAll(".tabcontent")?.forEach((el) => (el.style.display = "block"));
}); */

document.addEventListener("DOMContentLoaded", () => {
  startLogStream();
  loadInstruments();   // 🔥 new line to sync current attachments
  refreshStatus();     // optional but keeps status info current
});


async function setAll() {
  // PSU
  await setPSU("psu");
  // PSU2
  await setPSU("psu2");
  // Generator
  await setGen();
  // Analyzer
  await setSA();

  appendLog({ts: new Date().toISOString(), msg: "Set All completed."});
  refreshStatus();
}

// Protect index.html
if (window.location.pathname.endsWith("index.html")) {
  if (sessionStorage.getItem("loggedIn") !== "true") {
    window.location.replace("/static/login.html");
  }
}

// Logout button logic
document.addEventListener("DOMContentLoaded", () => {
  const logoutBtn = document.getElementById("btn-logout");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", () => {
      sessionStorage.removeItem("loggedIn");  // clear login
      window.location.replace("/static/login.html"); // go back to login
    });
  }
});

async function programFPGA() {
  appendLog({ts: new Date().toISOString(), msg: "Programming FPGA..."});
  try {
    const res = await fetch("/api/fpga/program", {method: "POST"});
    const j = await res.json();
    appendLog(j);
    document.getElementById("fpga_status").textContent = "Status: " + j.message;

    if (j.status === "ok") {
      // Reset progress bar
      const bar = document.getElementById("fpga_progress");
      bar.value = 0;

      // Start polling FPGA status
      pollFpgaStatus();
    }
  } catch (e) {
    appendLog({ts: new Date().toISOString(), level: "error", msg: e.toString()});
  }
}

async function pollFpgaStatus() {
  const bar = document.getElementById("fpga_progress");
  let progress = 0;

  const interval = setInterval(async () => {
    const res = await fetch("/api/fpga/status");
    const j = await res.json();
    document.getElementById("fpga_status").textContent = "Status: " + j.status;

    if (j.status === "programming") {
      // Simulate progress increase
      if (progress < 95) {  // leave headroom for final jump
        progress += 5;
        bar.value = progress;
      }
      bar.style.accentColor = "blue";
    }

    if (j.status === "done") {
      bar.value = 100;
      bar.style.accentColor = "green";
      clearInterval(interval);
    } else if (j.status === "error") {
      bar.value = 100;
      bar.style.accentColor = "red"; // mark failure
      clearInterval(interval);
    } else if (j.status === "idle") {
      bar.value = 0;
      clearInterval(interval);
    }
  }, 600); // poll every 600ms
}

// ----------------- RS-422 -----------------
async function sendRS422() {
  const port = document.getElementById("rs422_port").value.trim();
  const packet = document.getElementById("rs422_packet").value.trim();

  if (!port || !packet) {
    alert("Please enter both COM port and packet.");
    return;
  }

  appendLog({ts: new Date().toISOString(), msg: `Sending RS-422 packet to ${port}: ${packet}`});
  try {
    const res = await fetch("/api/rs422/send", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({port, packet})
    });
    const j = await res.json();
    appendLog(j);
    if (j.status === "ok") {
      document.getElementById("rs422_response").textContent =
        `Sent: ${j.sent}\nReceived: ${j.received || "NO RESPONSE"}`;
    } else {
      document.getElementById("rs422_response").textContent = "Error: " + (j.message || "Unknown");
    }
  } catch (e) {
    appendLog({ts: new Date().toISOString(), level: "error", msg: e.toString()});
  }
}

// ----------------- 10G UDP -----------------
const BASE_PAYLOAD =
  "00 ab ab 06 00 00 07 00 00 ab ac 00 ab ab 06 00 00 01 00 00 ab " +
  "00 ab ab 06 00 00 01 00 00 ab 00 ab ab 06 00 00 01 00 00";

function buildPayload() {
  const bytes = BASE_PAYLOAD.trim().split(/\s+/).map(b => b.toUpperCase());

  const spotHex = document.getElementById("dtrc_spot").value.trim().split(/\s+/);
  const pulseHex = document.getElementById("dtrc_pulse").value.trim().split(/\s+/);
  const prtHex = document.getElementById("dtrc_prt").value.trim().split(/\s+/);

  bytes[9]  = spotHex[0];
  bytes[10] = pulseHex[0];
  bytes[11] = pulseHex[1];
  bytes[12] = prtHex[0];
  bytes[13] = prtHex[1];
  bytes[14] = prtHex[2];
  bytes[15] = prtHex[3];

  return bytes.join(" ");
}

async function sendUDP() {
  const src = document.getElementById("udp_src").value.trim();
  const dst = document.getElementById("udp_dst").value.trim();

  if (!src.includes(":")) return alert("Enter source as ip:port");
  if (!dst.includes(":")) return alert("Enter destination as ip:port");

  const [src_ip, srcPortStr] = src.split(":");
  const src_port = parseInt(srcPortStr, 10);
  const [dst_ip, dstPortStr] = dst.split(":");
  const dst_port = parseInt(dstPortStr, 10);

  const payloadHex = buildPayload();

  try {
    const res = await fetch("/api/udp/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        src_ip,
        src_port,
        dst_ip,
        dst_port,
        payload: payloadHex
      })
    });
    const j = await res.json();
    if (j.status === "ok") {
      document.getElementById("udp_response").textContent =
        `Sent ${j.sent_bytes} bytes\nSource: ${j.src}\nDestination: ${j.dst}\nPayload: ${j.payload}\nReceived: ${j.received}`;
    } else {
      document.getElementById("udp_response").textContent = "Error: " + j.message;
    }
  } catch (e) {
    document.getElementById("udp_response").textContent = "Error: " + e.message;
  }
}

