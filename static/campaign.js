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
let names = {};   // email -> detected/edited display name ("" = none)
let currentStep = 1;
let attachmentFiles = [];
let recipientLimit = 0;

/* ─── Name detection & merge tags ────────────────────────────────
   Mirrors the server-side logic: guess a person's name from the
   local part of their email address (john.smith@x.com → John Smith),
   skipping generic role inboxes like info@ or sales@. */
const GENERIC_LOCALPARTS = new Set([
  "info", "contact", "sales", "support", "admin", "hello", "hi", "team",
  "office", "mail", "email", "enquiries", "inquiries", "inquiry", "help",
  "hr", "careers", "jobs", "billing", "accounts", "accounting", "marketing",
  "press", "media", "noreply", "no-reply", "donotreply", "newsletter",
  "webmaster", "postmaster", "abuse", "security", "service", "services",
  "orders", "bookings", "reception", "general", "feedback", "notifications",
  "alerts", "news", "updates", "subscribe", "unsubscribe", "recruiting"
]);

function deriveNameFromEmail(email) {
  let local = email.split("@")[0];
  if (GENERIC_LOCALPARTS.has(local.toLowerCase())) return "";
  local = local.replace(/([a-z])([A-Z])/g, "$1 $2"); // split camelCase
  const tokens = [];
  for (const part of local.toLowerCase().split(/[._\-+\s]+/)) {
    const p = part.replace(/\d+/g, "");
    if (p.length >= 2 && /^[a-z]+$/.test(p) && !GENERIC_LOCALPARTS.has(p)) {
      tokens.push(p.charAt(0).toUpperCase() + p.slice(1));
    }
    if (tokens.length === 2) break;
  }
  return tokens.join(" ");
}

/* Fill in a name for any email that doesn't have one yet. */
function ensureNames() {
  emails.forEach(email => {
    if (!(email in names)) names[email] = deriveNameFromEmail(email);
  });
}

const MERGE_TAG_RE = /\{\{\s*(name|first_name|firstname|last_name|lastname|email)\s*(?:\|([^}]*))?\}\}/gi;

function hasMergeTags(text) {
  MERGE_TAG_RE.lastIndex = 0;
  return MERGE_TAG_RE.test(text);
}

/* Client-side mirror of the server's personalization, used for the preview. */
function personalizePreview(text, email) {
  const full = (names[email] || "").trim();
  const parts = full.split(/\s+/).filter(Boolean);
  const values = {
    email: email,
    name: full,
    first_name: parts[0] || "",
    last_name: parts.length > 1 ? parts[parts.length - 1] : ""
  };
  return text.replace(MERGE_TAG_RE, (m, key, fallback) => {
    key = key.toLowerCase().replace("firstname", "first_name").replace("lastname", "last_name");
    const val = values[key] || "";
    if (val) return val;
    if (fallback && fallback.trim()) return fallback.trim();
    return key === "email" ? email : "there";
  });
}

/* ─── Recipient limit slider ────────────────────────────────────
   Lets the user cap sending to the first N emails in the list
   instead of always sending to everyone that was extracted. */
const limitWrap   = document.getElementById("recipient-limit-wrap");
const limitSlider = document.getElementById("recipient-limit-slider");
const limitNumber = document.getElementById("recipient-limit-number");
const limitTotal  = document.getElementById("recipient-limit-total");

function getEffectiveMax() {
  return (typeof SEND_LIMIT === "number" && SEND_LIMIT > 0)
    ? Math.min(emails.length, SEND_LIMIT)
    : emails.length;
}

function syncLimitControls(value) {
  const max = getEffectiveMax();
  limitSlider.max = max;
  limitNumber.max = max;
  limitTotal.textContent = max;

  let v = parseInt(value, 10);
  if (isNaN(v) || v < 1) v = 1;
  if (v > max) v = max;

  recipientLimit = v;
  limitSlider.value = v;
  limitNumber.value = v;
}

function refreshRecipientLimit() {
  const max = getEffectiveMax();
  if (max <= 0) {
    limitWrap.style.display = "none";
    recipientLimit = 0;
    return;
  }
  limitWrap.style.display = "";
  // Default to "send to everyone" whenever the list changes size, unless
  // the user already dialed in a smaller number that's still valid.
  const keep = recipientLimit > 0 && recipientLimit <= max ? recipientLimit : max;
  syncLimitControls(keep);
}

if (limitSlider && limitNumber) {
  limitSlider.addEventListener("input", () => syncLimitControls(limitSlider.value));
  limitNumber.addEventListener("input", () => syncLimitControls(limitNumber.value));
}

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
  ensureNames();

  emails.forEach((email, idx) => {
    const chip = document.createElement("div");
    chip.className = "chip";
    const name = names[email] || "";
    chip.innerHTML = `<span>${email}</span>`
      + (name ? `<span class="chip__name">${name}</span>` : "")
      + `<button class="chip__remove" data-idx="${idx}" title="Remove">×</button>`;
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

  refreshRecipientLimit();
}

/* Returns the emails that will actually be sent to, respecting the
   recipient-limit slider on step 1. */
function getSelectedEmails() {
  if (recipientLimit > 0 && recipientLimit < emails.length) {
    return emails.slice(0, recipientLimit);
  }
  return emails;
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
      names = Object.assign({}, data.names || {});
      renderChips();
      const named = emails.filter(e => (names[e] || "").trim()).length;
      setExtractStatus("success", `Found ${data.total} email addresses${named ? ` — detected ${named} name${named !== 1 ? "s" : ""}` : ""}.`);
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
      names = Object.assign({}, data.names || {});
      renderChips();
      const named = emails.filter(e => (names[e] || "").trim()).length;
      setExtractStatus("success", `Found ${data.total} email addresses${named ? ` — detected ${named} name${named !== 1 ? "s" : ""}` : ""}.`);
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
  names = {};
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
        const pastedHtml = '<p>' + data.body.replace(/\n\n+/g, '</p><p>').replace(/\n/g, '<br>') + '</p>';
        bodyQuill.clipboard.dangerouslyPasteHTML(pastedHtml);
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

/* ─── Personalization UI ──────────────────────────────────────── */
const subjectInput = document.getElementById("subject-input");

/* Track where the user last typed so tag buttons insert in the right place. */
let lastFocusedField = "body";
if (subjectInput) {
  subjectInput.addEventListener("focus", () => { lastFocusedField = "subject"; });
}
if (typeof bodyQuill !== "undefined") {
  bodyQuill.on("selection-change", range => { if (range) lastFocusedField = "body"; });
}

function insertMergeTag(tag) {
  if (lastFocusedField === "subject" && subjectInput) {
    const start = subjectInput.selectionStart ?? subjectInput.value.length;
    const end   = subjectInput.selectionEnd ?? start;
    subjectInput.value = subjectInput.value.slice(0, start) + tag + subjectInput.value.slice(end);
    subjectInput.focus();
    subjectInput.setSelectionRange(start + tag.length, start + tag.length);
  } else {
    const range = bodyQuill.getSelection(true);
    bodyQuill.insertText(range.index, tag, "user");
    bodyQuill.setSelection(range.index + tag.length);
  }
}

document.querySelectorAll(".tag-btn").forEach(btn => {
  // mousedown, not click, so the editor/input doesn't lose focus first
  btn.addEventListener("mousedown", e => e.preventDefault());
  btn.addEventListener("click", () => insertMergeTag(btn.dataset.tag));
});

const namesEditor    = document.getElementById("names-editor");
const toggleNamesBtn = document.getElementById("toggle-names-btn");

function renderNamesEditor() {
  if (!namesEditor) return;
  namesEditor.innerHTML = "";
  ensureNames();
  const list = getSelectedEmails();
  if (list.length === 0) {
    namesEditor.innerHTML = '<p class="muted small">No recipients yet — extract emails in step 1 first.</p>';
    return;
  }
  list.forEach(email => {
    const row = document.createElement("div");
    row.className = "names-row";
    const label = document.createElement("span");
    label.className = "names-row__email";
    label.textContent = email;
    const input = document.createElement("input");
    input.type = "text";
    input.className = "names-row__input";
    input.placeholder = "No name detected";
    input.value = names[email] || "";
    input.addEventListener("input", () => { names[email] = input.value; });
    input.addEventListener("change", renderChips);
    row.appendChild(label);
    row.appendChild(input);
    namesEditor.appendChild(row);
  });
}

if (toggleNamesBtn) {
  toggleNamesBtn.addEventListener("click", () => {
    const open = namesEditor.style.display !== "none";
    if (open) {
      namesEditor.style.display = "none";
      toggleNamesBtn.textContent = "Review & edit detected names ▾";
    } else {
      renderNamesEditor();
      namesEditor.style.display = "";
      toggleNamesBtn.textContent = "Hide detected names ▴";
    }
  });
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
  const subject  = document.getElementById("subject-input").value.trim();
  const bodyHtml = bodyQuill.root.innerHTML;
  const bodyText = bodyQuill.getText().trim();
  if (!subject || !bodyText) {
    alert("Please fill in the subject and body.");
    return;
  }
  document.getElementById("body-input").value = bodyHtml;
  const selectedEmails = getSelectedEmails();
  document.getElementById("review-count").textContent   = selectedEmails.length + " recipient" + (selectedEmails.length !== 1 ? "s" : "")
    + (selectedEmails.length !== emails.length ? ` (of ${emails.length} found)` : "");

  // Show the preview personalized for the first recipient when merge tags are used.
  const personalized = selectedEmails.length > 0 && (hasMergeTags(subject) || hasMergeTags(bodyHtml));
  const previewEmail = selectedEmails[0];
  const note = document.getElementById("review-personalized-note");
  if (personalized) {
    document.getElementById("review-subject").textContent = personalizePreview(subject, previewEmail);
    document.getElementById("review-body").innerHTML      = personalizePreview(bodyHtml, previewEmail);
    if (note) {
      note.textContent = `Personalized preview for ${previewEmail} — every recipient gets their own version.`;
      note.style.display = "";
    }
  } else {
    document.getElementById("review-subject").textContent = subject;
    document.getElementById("review-body").innerHTML      = bodyHtml;
    if (note) note.style.display = "none";
  }

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

/* ─── Send / Schedule buttons ─────────────────────────────────── */
const sendBtn = document.getElementById("send-btn");

/* ─── Schedule toggle ─────────────────────────────────────────── */
const scheduleCheckbox = document.getElementById("schedule-checkbox");
const scheduleOptions  = document.getElementById("schedule-options");
const scheduleAttHint  = document.getElementById("schedule-attachments-hint");
const scheduleBtn      = document.getElementById("schedule-btn");

if (scheduleCheckbox) {
  scheduleCheckbox.addEventListener("change", () => {
    const on = scheduleCheckbox.checked;
    scheduleOptions.style.display = on ? "" : "none";
    if (sendBtn) sendBtn.style.display = on ? "none" : "";
    if (scheduleBtn) scheduleBtn.style.display = on ? "" : "none";
    if (scheduleAttHint) scheduleAttHint.style.display = (on && attachmentFiles.length > 0) ? "" : "none";
  });
}

/* ─── Send ────────────────────────────────────────────────────── */
if (sendBtn) {
  sendBtn.addEventListener("click", async () => {
    const subject = document.getElementById("subject-input").value.trim();
    const body    = bodyQuill.root.innerHTML;
    const nameEl  = document.getElementById("campaign-name-ai") || document.getElementById("campaign-name-manual");
    const name    = (nameEl ? nameEl.value.trim() : "") || "Campaign";

    sendBtn.disabled = true;
    document.getElementById("step3-actions").style.display = "none";
    document.getElementById("send-progress").style.display = "";

    const bar   = document.getElementById("progress-bar");
    const label = document.getElementById("progress-label");
    const log   = document.getElementById("send-log");
    const selectedEmails = getSelectedEmails();
    const total = selectedEmails.length;
    let done = 0, ok = 0, fail = 0;

    try {
      const fd = new FormData();
      fd.append("emails", JSON.stringify(selectedEmails));
      fd.append("names", JSON.stringify(names));
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

/* ─── Schedule ────────────────────────────────────────────────── */
if (scheduleBtn) {
  scheduleBtn.addEventListener("click", async () => {
    const subject = document.getElementById("subject-input").value.trim();
    const body    = bodyQuill.root.innerHTML;
    const nameEl  = document.getElementById("campaign-name-ai") || document.getElementById("campaign-name-manual");
    const name    = (nameEl ? nameEl.value.trim() : "") || "Campaign";
    const frequency = document.getElementById("schedule-frequency").value;
    const firstRun  = document.getElementById("schedule-first-run").value;
    const selectedEmails = getSelectedEmails();

    if (!firstRun) {
      alert("Please choose a first send date/time.");
      return;
    }

    scheduleBtn.disabled = true;
    scheduleBtn.textContent = "Creating schedule…";

    try {
      const resp = await jsonPost("/campaign/schedule", {
        name,
        subject,
        body,
        emails: selectedEmails,
        names,
        frequency,
        first_run: firstRun
      });
      const data = await resp.json();
      if (!resp.ok || data.error) {
        alert(data.error || "Could not create schedule.");
        scheduleBtn.disabled = false;
        scheduleBtn.textContent = "🗓️ Create Schedule";
        return;
      }
      window.location.href = "/scheduled";
    } catch (e) {
      alert("Could not create schedule: " + e.message);
      scheduleBtn.disabled = false;
      scheduleBtn.textContent = "🗓️ Create Schedule";
    }
  });
}

/* ─── Prefill (e.g. "Resend to failed" from a campaign page) ──── */
if (typeof PREFILL !== "undefined" && PREFILL) {
  emails = Array.isArray(PREFILL.emails) ? PREFILL.emails.slice() : [];
  renderChips();
  if (PREFILL.subject) document.getElementById("subject-input").value = PREFILL.subject;
  if (PREFILL.body) {
    const html = '<p>' + PREFILL.body.replace(/\n\n+/g, '</p><p>').replace(/\n/g, '<br>') + '</p>';
    bodyQuill.clipboard.dangerouslyPasteHTML(html);
  }
  if (PREFILL.name) {
    const nameEl = document.getElementById("campaign-name-ai") || document.getElementById("campaign-name-manual");
    if (nameEl) nameEl.value = PREFILL.name;
  }
  if (emails.length) {
    setExtractStatus("info", `Loaded ${emails.length} recipient${emails.length !== 1 ? "s" : ""} — review the list and continue.`);
  }
}
