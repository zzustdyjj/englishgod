// Personal English Agent demo 前端：原生 JS，无构建步骤。

const $ = (sel) => document.querySelector(sel);

// 创建元素：h("div", {class: "x", onclick: fn}, "文字", child...)
function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

async function api(path, options = {}) {
  const res = await fetch(path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `请求失败（${res.status}）`);
  return data;
}
const jsonBody = (method, body) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

let toastTimer;
function toast(text, ms = 2500) {
  const el = $("#toast");
  el.textContent = text;
  el.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), ms);
}

const fmtDate = (iso) => iso.slice(0, 16).replace("T", " ");

// ---------- 标签页 ----------

const tabLoaders = { learn: loadConversations, gaps: loadGaps, review: loadReview, export: () => {} };

function showTab(name) {
  document.querySelectorAll(".tab").forEach((s) => s.classList.toggle("hidden", s.id !== `tab-${name}`));
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $("#composer").classList.toggle("hidden", name !== "learn" || state.convId == null);
  tabLoaders[name]();
}
document.querySelectorAll("#tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));

// ---------- 学习：对话 ----------

const state = { convId: null, image: null };

async function loadConversations() {
  if (state.convId != null) return;
  const convs = await api("/api/conversations");
  const list = $("#conv-list");
  list.replaceChildren(
    ...convs.map((c) =>
      h("li", { onclick: () => openConversation(c.id) },
        h("div", {}, c.title),
        h("div", { class: "sub" }, fmtDate(c.created_at), c.pending ? ` · ${c.pending} 条未记录` : ""))
    )
  );
  if (!convs.length) list.append(h("div", { class: "empty" }, "遇到不懂的英语？点「新提问」，发一张截图开始。"));
}

async function openConversation(id) {
  state.convId = id;
  const conv = await api(`/api/conversations/${id}`);
  $("#conv-list-view").classList.add("hidden");
  $("#chat-view").classList.remove("hidden");
  $("#composer").classList.remove("hidden");
  $("#chat-title").textContent = conv.title;
  $("#messages").replaceChildren();
  let prevRecorded = null;
  for (const m of conv.messages) {
    if (prevRecorded === true && !m.recorded) $("#messages").append(h("div", { class: "divider" }, "—— 以上已记录 ——"));
    appendMessage(m);
    prevRecorded = m.recorded;
  }
  scrollToBottom();
}

function appendMessage(m) {
  $("#messages").append(
    h("div", { class: `msg ${m.role}${m.recorded ? " recorded" : ""}` },
      m.image_url && h("img", { src: m.image_url, alt: "截图" }),
      m.text)
  );
}
const scrollToBottom = () => window.scrollTo(0, document.body.scrollHeight);

function closeConversation() {
  state.convId = null;
  clearImage();
  $("#chat-view").classList.add("hidden");
  $("#composer").classList.add("hidden");
  $("#conv-list-view").classList.remove("hidden");
  loadConversations();
}

$("#new-conv").addEventListener("click", async () => {
  const conv = await api("/api/conversations", { method: "POST" });
  await openConversation(conv.id);
  $("#image-input").click();
});
$("#chat-back").addEventListener("click", closeConversation);

// 截图在上传前缩小到最长边 2000px，减少流量和模型费用
async function shrinkImage(file, maxSide = 2000) {
  const bitmap = await createImageBitmap(file).catch(() => null);
  if (!bitmap || Math.max(bitmap.width, bitmap.height) <= maxSide) return file;
  const scale = maxSide / Math.max(bitmap.width, bitmap.height);
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise((r) => canvas.toBlob(r, "image/jpeg", 0.9));
  return new File([blob], "screenshot.jpg", { type: "image/jpeg" });
}

$("#image-input").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  e.target.value = "";
  if (!file) return;
  state.image = await shrinkImage(file);
  $("#image-preview img").src = URL.createObjectURL(state.image);
  $("#image-preview").classList.remove("hidden");
  $("#text-input").focus();
});
function clearImage() {
  state.image = null;
  $("#image-preview").classList.add("hidden");
}
$("#image-clear").addEventListener("click", clearImage);

$("#text-input").addEventListener("input", (e) => {
  e.target.style.height = "auto";
  e.target.style.height = e.target.scrollHeight + "px";
});

$("#composer").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("#text-input").value.trim();
  if (!text && !state.image) return;
  const form = new FormData();
  form.append("text", text);
  if (state.image) form.append("image", state.image);

  const sendBtn = $("#send-btn");
  sendBtn.disabled = true;
  sendBtn.textContent = "思考中…";
  try {
    const res = await api(`/api/conversations/${state.convId}/messages`, { method: "POST", body: form });
    appendMessage(res.user);
    appendMessage(res.assistant);
    $("#text-input").value = "";
    $("#text-input").style.height = "auto";
    clearImage();
    scrollToBottom();
  } catch (err) {
    toast(err.message, 5000);
  } finally {
    sendBtn.disabled = false;
    sendBtn.textContent = "发送";
  }
});

$("#record-btn").addEventListener("click", async () => {
  const btn = $("#record-btn");
  btn.disabled = true;
  btn.textContent = "整理中…";
  try {
    const res = await api(`/api/conversations/${state.convId}/record`, { method: "POST" });
    if (!res.gaps.length) toast("这段对话里没有提炼出 GAP");
    else toast("已记录：\n" + res.gaps.map((g) => `${g.is_new ? "新增" : "再次遇见"} · ${g.anchor_text}`).join("\n"), 4000);
    await openConversation(state.convId);
  } catch (err) {
    toast(err.message, 5000);
  } finally {
    btn.disabled = false;
    btn.textContent = "记录";
  }
});

// ---------- GAP 渲染（列表与复习共用） ----------

function renderOccurrence(o, i) {
  return h("div", { class: "occ" },
    h("div", {}, h("span", { class: "label" }, `遇见 ${i + 1}（${o.created_at.slice(0, 10)}）情景：`), o.scene),
    o.image_url && h("img", { src: o.image_url, alt: "原图" }),
    o.question && h("div", {}, h("span", { class: "label" }, "疑问："), o.question),
    o.user_attempt && h("div", {}, h("span", { class: "label" }, "我的原话："), o.user_attempt),
    o.error && h("div", { class: "err" }, h("span", { class: "label" }, "错误："), o.error),
    o.clarified && h("div", {}, h("span", { class: "label" }, "弄清楚了："), o.clarified),
    h("div", { class: "label" }, `程度：${o.evidence}`));
}

function renderGapHead(g) {
  return [
    h("span", { class: "anchor" }, g.anchor_text),
    g.kind && h("span", { class: "tag" }, g.kind),
    ...g.skills.map((s) => h("span", { class: "tag" }, s)),
    h("span", { class: "tag" }, `遇见 ${g.occurrences.length} 次`),
  ];
}

// ---------- GAP 列表 ----------

async function loadGaps() {
  const params = new URLSearchParams();
  if ($("#gap-skill").value) params.set("skill", $("#gap-skill").value);
  if ($("#gap-status").value) params.set("status", $("#gap-status").value);
  const gaps = await api(`/api/gaps?${params}`);
  const box = $("#gap-list");
  box.replaceChildren(...gaps.map(renderGapItem));
  if (!gaps.length) box.append(h("div", { class: "empty" }, "还没有 GAP。去「学习」提问，然后点「记录」。"));
}
$("#gap-skill").addEventListener("change", loadGaps);
$("#gap-status").addEventListener("change", loadGaps);

function renderGapItem(g) {
  const detail = h("div", { class: "hidden" },
    ...g.occurrences.map(renderOccurrence),
    h("div", { class: "actions" },
      h("button", { onclick: () => setGapStatus(g, g.status === "solved" ? "active" : "solved") },
        g.status === "solved" ? "设为未解决" : "标为已解决"),
      h("button", { class: "btn-bad", onclick: () => deleteGap(g) }, "删除")));
  return h("div", { class: "gap" },
    h("div", { class: "head", onclick: () => detail.classList.toggle("hidden") }, ...renderGapHead(g)),
    h("div", { class: "core" }, g.core_note),
    detail);
}

async function setGapStatus(g, status) {
  await api(`/api/gaps/${g.id}`, jsonBody("PATCH", { status }));
  toast(status === "solved" ? "已标为解决" : "已设为未解决");
  loadGaps();
}

async function deleteGap(g) {
  if (!confirm(`删除「${g.anchor_text}」及其所有遇见记录？`)) return;
  await api(`/api/gaps/${g.id}`, { method: "DELETE" });
  loadGaps();
}

// ---------- 复习：翻卡 ----------

async function loadReview() {
  const { gap, remaining } = await api("/api/review/next");
  $("#review-remaining").textContent = remaining ? `待复习 ${remaining}` : "";
  const box = $("#review-card");
  if (!gap) {
    box.replaceChildren(h("div", { class: "empty" }, "没有待复习的 GAP 🎉"));
    return;
  }
  // 正面：最近一次遇见的情景、原图和疑问；背面：表达、结论和全部遇见
  const latest = gap.occurrences[gap.occurrences.length - 1];
  const answer = h("div", { class: "answer hidden" },
    h("div", { class: "head" }, ...renderGapHead(gap)),
    h("div", { class: "core" }, gap.core_note),
    ...gap.occurrences.map(renderOccurrence),
    h("div", { class: "actions" },
      h("button", { class: "btn-bad", onclick: () => submitReview(gap, "forgot") }, "没想起来"),
      h("button", { class: "btn-ok", onclick: () => submitReview(gap, "remembered") }, "想起来了"),
      h("button", { onclick: () => submitReview(gap, "solved") }, "已解决")));
  const flip = h("button", { class: "primary", onclick: () => { answer.classList.remove("hidden"); flip.remove(); } }, "翻开答案");
  box.replaceChildren(
    h("div", { class: "card" },
      h("div", { class: "prompt" },
        latest?.image_url && h("img", { src: latest.image_url, alt: "原图", style: "max-width:100%;border-radius:8px" }),
        h("div", {}, h("span", { class: "label" }, "情景："), latest?.scene || ""),
        latest?.question && h("div", {}, h("span", { class: "label" }, "当时的疑问："), latest.question),
        h("p", { class: "muted" }, "先回忆：它是什么意思 / 该怎么说？")),
      h("div", { class: "actions" }, flip),
      answer));
}

async function submitReview(gap, result) {
  await api(`/api/review/${gap.id}`, jsonBody("POST", { result }));
  if (result === "solved") toast(`「${gap.anchor_text}」已解决，不再出现`);
  loadReview();
}

// ---------- 导出 ----------

$("#export-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const params = new URLSearchParams();
  for (const [k, v] of new FormData(e.target)) if (v) params.set(k, v);
  window.open(`/api/export?${params}`, "_blank");
});

// ---------- 启动 ----------

(async function init() {
  const status = await api("/api/status");
  $("#mock-banner").classList.toggle("hidden", !status.mock);
  const templates = await api("/api/templates");
  $("#export-template").replaceChildren(...templates.map((t) => h("option", { value: t.id }, t.name)));
  $("#composer").classList.add("hidden");
  loadConversations();
})();
