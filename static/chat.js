(function () {
  const messagesEl = document.getElementById("messages");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const sendBtn = document.getElementById("send-btn");
  const suggestionsEl = document.getElementById("suggestions");
  const clearBtn = document.getElementById("clear-chat");
  const csrf = document.querySelector('meta[name="csrf-token"]').content;

  const URL_RE = /(https?:\/\/[^\s<>"']+)/g;

  // Builds DOM nodes (never innerHTML) so message text can't inject markup.
  // Bare http(s) links become clickable.
  function fillBubble(el, text) {
    text.split(URL_RE).forEach((part, i) => {
      if (i % 2 === 1) {
        const a = document.createElement("a");
        a.href = part;
        a.textContent = part;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        el.appendChild(a);
      } else if (part) {
        el.appendChild(document.createTextNode(part));
      }
    });
  }

  function addMessage(role, text) {
    const wrap = document.createElement("div");
    wrap.className = `msg ${role}`;

    const who = document.createElement("span");
    who.className = "who";
    who.textContent = role === "user" ? "You" : "Nocturna";

    const bubble = document.createElement("p");
    bubble.className = "bubble";
    fillBubble(bubble, text);

    wrap.append(who, bubble);
    messagesEl.appendChild(wrap);
    scrollDown();
    return wrap;
  }

  function addTyping() {
    const wrap = document.createElement("div");
    wrap.className = "msg bot typing";
    wrap.setAttribute("aria-label", "Nocturna is typing");
    const bubble = document.createElement("p");
    bubble.className = "bubble";
    for (let i = 0; i < 3; i++) {
      const dot = document.createElement("span");
      dot.className = "dot";
      bubble.appendChild(dot);
    }
    wrap.appendChild(bubble);
    messagesEl.appendChild(wrap);
    scrollDown();
    return wrap;
  }

  function scrollDown() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function setBusy(busy) {
    sendBtn.disabled = busy;
    input.disabled = busy;
    if (!busy) input.focus();
  }

  async function api(path, options = {}) {
    const res = await fetch(path, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrf,
        ...(options.headers || {}),
      },
    });
    if (res.status === 401) {
      window.location.href = "/login";
      throw new Error("Not logged in");
    }
    let data = {};
    try { data = await res.json(); } catch (_) { /* non-JSON error page */ }
    if (!res.ok) throw new Error(data.error || "Something went wrong. Please try again.");
    return data;
  }

  async function send(text) {
    suggestionsEl.hidden = true;
    addMessage("user", text);
    setBusy(true);
    const typing = addTyping();
    try {
      const data = await api("/api/chat", { method: "POST", body: JSON.stringify({ text }) });
      typing.remove();
      (data.replies || []).forEach((line) => addMessage("bot", line));
    } catch (err) {
      typing.remove();
      addMessage("bot", err.message);
    } finally {
      setBusy(false);
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    send(text);
  });

  suggestionsEl.addEventListener("click", (event) => {
    const chip = event.target.closest(".chip");
    if (chip) send(chip.textContent);
  });

  clearBtn.addEventListener("click", async () => {
    if (!window.confirm("Delete this conversation? Your notes and reminders are kept.")) return;
    try {
      await api("/api/clear", { method: "POST", body: "{}" });
      messagesEl.replaceChildren();
      await loadHistory();
    } catch (err) {
      addMessage("bot", err.message);
    }
  });

  async function loadHistory() {
    try {
      const data = await api("/api/history");
      messagesEl.replaceChildren();
      data.messages.forEach((m) => addMessage(m.role, m.content));
      suggestionsEl.hidden = data.messages.length > 1;
    } catch (err) {
      addMessage("bot", err.message);
    }
  }

  async function showDueReminders() {
    try {
      const data = await api("/api/due_reminders");
      (data.due || []).forEach((line) => addMessage("bot", line));
      if ((data.due || []).length) suggestionsEl.hidden = true;
    } catch (_) {
      // Non-critical: the rest of the chat still works without it.
    }
  }

  (async function init() {
    await loadHistory();
    await showDueReminders();
    input.focus();
  })();
})();
