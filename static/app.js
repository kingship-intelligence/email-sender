const form = document.getElementById("emailForm");
const sendBtn = document.getElementById("sendBtn");
const alert = document.getElementById("alert");

function showAlert(type, message) {
  alert.className = "alert " + type;
  alert.textContent = message;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  sendBtn.disabled = true;
  sendBtn.textContent = "Sending…";
  alert.className = "alert hidden";

  const payload = {
    smtp_host: document.getElementById("smtp_host").value,
    smtp_port: document.getElementById("smtp_port").value,
    smtp_user: document.getElementById("smtp_user").value,
    smtp_pass: document.getElementById("smtp_pass").value,
    from_addr: document.getElementById("from_addr").value,
    to_addr:   document.getElementById("to_addr").value,
    subject:   document.getElementById("subject").value,
    body:      document.getElementById("body").value,
    use_tls:   document.getElementById("use_tls").checked,
  };

  try {
    const res = await fetch("/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.success) {
      showAlert("success", data.message);
      form.reset();
      document.getElementById("smtp_port").value = "587";
      document.getElementById("use_tls").checked = true;
    } else {
      showAlert("error", data.error || "Something went wrong.");
    }
  } catch (err) {
    showAlert("error", "Network error: " + err.message);
  } finally {
    sendBtn.disabled = false;
    sendBtn.textContent = "Send Email";
  }
});
