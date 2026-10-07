const scenarios = document.querySelector("#scenarios");
const form = document.querySelector("#run");
const buckets = document.querySelector("#buckets");
const total = document.querySelector("#total");
const status = document.querySelector("#status");
const capacity = document.querySelector("#capacity");
const request = document.querySelector("#request");
const extra = document.querySelector("#extra");

async function loadMeta() {
  const response = await fetch("/api/meta");
  const meta = await response.json();
  capacity.textContent = meta.capacity_note;
  scenarios.replaceChildren();
  for (const item of meta.scenarios) {
    const label = document.createElement("label");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.name = "scenario";
    box.value = item.id;
    box.checked = true;
    label.title = item.description;
    label.append(box, ` ${item.id} ${item.title}`);
    scenarios.append(label);
  }
  const select = form.querySelector("select[name=transport]");
  for (const option of select.options) {
    option.disabled = !meta.transports.includes(option.value);
  }
}

function selectedScenarios() {
  return [...form.querySelectorAll("input[name=scenario]:checked")].map((node) => node.value);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const chosen = selectedScenarios();
  if (chosen.length === 0) {
    status.textContent = "至少选择一种呼叫类型";
    return;
  }
  const data = new FormData(form);
  const response = await fetch("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      transport: data.get("transport"),
      cps: Number(data.get("cps")),
      duration_seconds: Number(data.get("duration_seconds")),
      hold_seconds: Number(data.get("hold_seconds")),
      workers: Number(data.get("workers")),
      scenarios: chosen,
    }),
  });
  const payload = await response.json();
  status.textContent = payload.error ? `未启动：${payload.error}` : "运行中";
});

document.querySelector("#stop").addEventListener("click", async () => {
  await fetch("/api/runs/stop", { method: "POST" });
  status.textContent = "正在停止新的呼叫";
});

function row(cells, tag) {
  const tr = document.createElement("tr");
  for (const value of cells) {
    const cell = document.createElement(tag);
    cell.textContent = value === null || value === undefined ? "" : String(value);
    tr.append(cell);
  }
  return tr;
}

function codes(map) {
  return Object.entries(map || {})
    .map(([code, count]) => `${code}×${count}`)
    .join(" ");
}

function render(snapshot) {
  if (snapshot.error) {
    status.textContent = `运行失败：${snapshot.error}`;
  } else if (snapshot.running) {
    status.textContent = "运行中";
  } else if (snapshot.summary) {
    status.textContent = "已结束";
  }
  const sent = snapshot.request;
  request.textContent = sent
    ? `本次：${sent.transport.toUpperCase()}，${sent.scenarios.join(" ")}，` +
      `${sent.cps} CPS，${sent.duration_seconds} 秒，保持 ${sent.hold_seconds} 秒，` +
      `并发上限 ${sent.workers}`
    : "";
  const summary = snapshot.summary;
  buckets.replaceChildren();
  total.replaceChildren();
  extra.textContent = "";
  if (!summary) {
    return;
  }
  for (const [name, bucket] of Object.entries(summary.by_scenario || {})) {
    const latency = bucket.setup_latency_ms || {};
    buckets.append(
      row(
        [
          name,
          bucket.invites_sent,
          bucket.established,
          bucket.failed,
          codes(bucket.response_codes),
          latency.p50,
          latency.p95,
        ],
        "td",
      ),
    );
  }
  const latency = summary.setup_latency_ms || {};
  total.append(
    row(
      [
        "合计",
        summary.invites_sent,
        summary.established,
        summary.failed,
        codes(summary.response_code_distribution),
        latency.p50,
        latency.p95,
      ],
      "th",
    ),
  );
  extra.textContent =
    `峰值同时接通 ${summary.peak_established}，未拆除 ${summary.unresolved}。` +
    `错误分布：${codes(summary.error_distribution) || "无"}`;
}

async function poll() {
  const response = await fetch("/api/runs/latest");
  render(await response.json());
}

loadMeta();
setInterval(poll, 1000);
