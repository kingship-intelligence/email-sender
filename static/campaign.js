/* ─── CSRF helper ────────────────────────────────────────────── */
function getCsrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.getAttribute("content") : "";
}
function jsonPost(url, body) {
  return fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken()
    },
    body: JSON.stringify(body)
  });
}

/* ─── State ──────────────────────────────────────────────────── */
let emails = [];
let currentStep = 1;
let attachmentFiles = [];

/* ─── Step navigation ────────────────────────────────────────── */
function goToStep(n) {
  document.querySelectorAll(".wizard-step").forEach((el, i) => {
    el.style.display = (i + 1 === n) ? "" : "none";
  });
  document.querySelectorAll(".step").forEach((el, i) => {
    el.classList.toggle("active", i + 1 === n);
    el.classList.toggle("done", i + 1 < n);
  });
  currentStep = n;
}

/* ─── Email chips ─────────────────────────────────────────────── */
function renderChips() {
  const container = document.getElementById("email-chips");
  const countEl   = document.getElementById("email-count");
  const listWrap  = document.getElementById("email-list-wrap");
  const nextBtn   = document.getElementById("step1-next");

  container.innerHTML = "";

  emails.forEach((email, idx) => {
    const chip = document.createElement("div");
    chip.className = "chip";
    chip.innerHTML = `<span>${email}</span><button class="chip__remove" data-idx="${idx}" title="Remove">×</button>`;
    container.appendChild(chip);
  });

  container.querySelectorAll(".chip__remove").forEach(btn => {
    btn.addEventListener("click", () => {
      const i = parseInt(btn.dataset.idx);
      emails.splice(i, 1);
      renderChips();
    });
  });

  const cnt = emails.length;
  countEl.textContent = `${cnt} email${cnt !== 1 ? "s" : ""} found`;
  listWrap.style.display = cnt > 0 ? "" : "none";
  nextBtn.disabled = cnt === 0;
}

function setExtractStatus(type, msg) {
  const el = document.getElementById("extract-status");
  el.className = "status-msg " + type;
  el.textContent = msg;
}

/* ─── File upload (email extraction) ─────────────────────────── */
function handleFile(file) {
  if (!file) return;
  setExtractStatus("info", `Parsing ${file.name}…`);
  const fd = new FormData();
  fd.append("file", file);
  fetch("/extract", { method: "POST", body: fd, headers: { "X-CSRFToken": getCsrfToken() } })
    .then(r => r.json())
    .then(data => {
      if (data.error) { setExtractStatus("error", data.error); return; }
      emails = data.emails;
      renderChips();
      setExtractStatus("success", `Found ${data.total} email addresses.`);
    })
    .catch(e => setExtractStatus("error", "Upload failed: " + e.message));
}

const fileInput = document.getElementById("file-input");
const dropZone  = document.getElementById("drop-zone");

fileInput.addEventListener("change", () => handleFile(fileInput.files[0]));

dropZone.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("dragover",  e => { e.preventDefault(); dropZone.classList.add("drag-over"); });
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
dropZone.addEventListener("drop", e => {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  handleFile(e.dataTransfer.files[0]);
});

/* ─── URL scraping ─────────────────────────────────────────────── */
document.getElementById("scrape-btn").addEventListener("click", () => {
  const url = document.getElementById("url-input").value.trim();
  if (!url) return;
  setExtractStatus("info", "Scraping page…");
  jsonPost("/extract-url", { url })
    .then(r => r.json())
    .then(data => {
      if (data.error) { setExtractStatus("error", data.error); return; }
      emails = data.emails;
      renderChips();
      setExtractStatus("success", `Found ${data.total} email addresses.`);
    })
    .catch(e => setExtractStatus("error", "Scrape failed: " + e.message));
});

/* ─── Tab bar ─────────────────────────────────────────────────── */
document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById("tab-file").style.display = tab.dataset.tab === "file" ? "" : "none";
    document.getElementById("tab-url").style.display  = tab.dataset.tab === "url"  ? "" : "none";
  });
});

/* ─── Clear ───────────────────────────────────────────────────── */
document.getElementById("clear-emails-btn").addEventListener("click", () => {
  emails = [];
  renderChips();
  setExtractStatus("hidden", "");
});

/* ─── Step 1 → 2 ──────────────────────────────────────────────── */
document.getElementById("step1-next").addEventListener("click", () => goToStep(2));
document.getElementById("step2-back").addEventListener("click", () => goToStep(1));

/* ─── AI generation ───────────────────────────────────────────── */
const genBtn = document.getElementById("generate-btn");
if (genBtn) {
  genBtn.addEventListener("click", () => {
    const brief = document.getElementById("brief-input").value.trim();
    if (!brief) { setGenStatus("error", "Please enter a campaign brief."); return; }
    genBtn.disabled = true;
    genBtn.textContent = "Generating…";
    setGenStatus("info", "Asking AI to write your email…");

    jsonPost("/generate", { brief })
      .then(r => r.json())
      .then(data => {
        if (data.error) { setGenStatus("error", data.error); return; }
        document.getElementById("subject-input").value = data.subject;
        document.getElementById("body-input").value    = data.body;
        setGenStatus("success", "Email generated! Feel free to edit it below.");
      })
      .catch(e => setGenStatus("error", "Generation failed: " + e.message))
      .finally(() => { genBtn.disabled = false; genBtn.textContent = "✨ Generate with AI"; });
  });
}

function setGenStatus(type, msg) {
  const el = document.getElementById("generate-status");
  if (!el) return;
  el.className = "status-msg " + type;
  el.textContent = msg;
}

/* ─── Attachments ─────────────────────────────────────────────── */
const attachInput = document.getElementById("attach-input");
const attachBtn   = document.getElementById("attach-btn");

attachBtn.addEventListener("click", () => attachInput.click());

attachInput.addEventListener("change", () => {
  Array.from(attachInput.files).forEach(f => {
    if (!attachmentFiles.find(x => x.name === f.name && x.size === f.size)) {
      attachmentFiles.push(f);
    }
  });
  attachInput.value = "";
  renderAttachments();
});

function renderAttachments() {
  const list = document.getElementById("attach-list");
  list.innerHTML = "";
  attachmentFiles.forEach((f, idx) => {
    const item = document.createElement("div");
    item.className = "attach-item";
    const sizeKb = (f.size / 1024).toFixed(0);
    item.innerHTML = `<span class="attach-name">📎 ${f.name}</span><span class="attach-size muted small">${sizeKb} KB</span><button class="attach-remove" data-idx="${idx}" title="Remove">✕</button>`;
    list.appendChild(item);
  });
  list.querySelectorAll(".attach-remove").forEach(btn => {
    btn.addEventListener("click", () => {
      attachmentFiles.splice(parseInt(btn.dataset.idx), 1);
      renderAttachments();
    });
  });
}

/* ─── Step 2 → 3 ──────────────────────────────────────────────── */
document.getElementById("step2-next").addEventListener("click", () => {
  const subject = document.getElementById("subject-input").value.trim();
  const body    = document.getElementById("body-input").value.trim();
  if (!subject || !body) {
    alert("Please fill in the subject and body.");
    return;
  }
  document.getElementById("review-count").textContent   = emails.length + " recipient" + (emails.length !== 1 ? "s" : "");
  document.getElementById("review-subject").textContent = subject;
  document.getElementById("review-body").textContent    = body;

  const attItem = document.getElementById("review-attachments-item");
  if (attachmentFiles.length > 0) {
    document.getElementById("review-attachments").textContent = attachmentFiles.map(f => f.name).join(", ");
    attItem.style.display = "";
  } else {
    attItem.style.display = "none";
  }

  goToStep(3);
});

document.getElementById("step3-back").addEventListener("click", () => goToStep(2));

/* ─── Send ────────────────────────────────────────────────────── */
const sendBtn = document.getElementById("send-btn");
if (sendBtn) {
  sendBtn.addEventListener("click", async () => {
    const subject = document.getElementById("subject-input").value.trim();
    const body    = document.getElementById("body-input").value.trim();
    const nameEl  = document.getElementById("campaign-name-ai") || document.getElementById("campaign-name-manual");
    const name    = (nameEl ? nameEl.value.trim() : "") || "Campaign";

    sendBtn.disabled = true;
    document.getElementById("step3-actions").style.display = "none";
    document.getElementById("send-progress").style.display = "";

    const bar   = document.getElementById("progress-bar");
    const label = document.getElementById("progress-label");
    const log   = document.getElementById("send-log");
    const total = emails.length;
    let done = 0, ok = 0, fail = 0;

    try {
      const fd = new FormData();
      fd.append("emails", JSON.stringify(emails));
      fd.append("subject", subject);
      fd.append("body", body);
      fd.append("name", name);
      attachmentFiles.forEach(f => fd.append("attachments", f));

      const resp = await fetch("/send-bulk", {
        method: "POST",
        headers: { "X-CSRFToken": getCsrfToken() },
        body: fd
      });

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done: streamDone } = await reader.read();
        if (streamDone) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();
        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const msg = JSON.parse(line);
            if (msg.done) {
              ok   = msg.ok;
              fail = msg.fail;
              bar.style.width = "100%";
              label.textContent = `Done — ${ok} delivered, ${fail} failed.`;
              document.getElementById("send-progress").style.display = "none";
              document.getElementById("done-ok").textContent   = ok;
              document.getElementById("done-fail").textContent = fail;
              document.getElementById("send-done").style.display = "";
            } else {
              done++;
              const pct = Math.round((done / total) * 100);
              bar.style.width = pct + "%";
              label.textContent = `Sending… ${done} / ${total}`;
              const row = document.createElement("div");
              row.className = msg.status === "sent" ? "log-ok" : "log-fail";
              row.textContent = (msg.status === "sent" ? "✓ " : "✗ ") + msg.email + (msg.error ? " — " + msg.error : "");
              log.appendChild(row);
              log.scrollTop = log.scrollHeight;
            }
          } catch (_) {}
        }
      }
    } catch (e) {
      label.textContent = "Error: " + e.message;
    }
  });
}
