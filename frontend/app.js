const chatContainer = document.getElementById("chat-container");
const chatForm = document.getElementById("chat-form");
const messageInput = document.getElementById("message-input");
const sendBtn = document.getElementById("send-btn");

let sessionId = localStorage.getItem("session_id");
if (!sessionId) {
  sessionId = crypto.randomUUID();
  localStorage.setItem("session_id", sessionId);
}

function renderMarkdown(text) {
  let html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, "<em>$1</em>");

  const lines = html.split("\n");
  const result = [];
  let inList = false;

  for (const line of lines) {
    const trimmed = line.trim();
    const listMatch = trimmed.match(/^[-•]\s+(.+)/);

    if (listMatch) {
      if (!inList) {
        result.push("<ul>");
        inList = true;
      }
      result.push(`<li>${listMatch[1]}</li>`);
    } else {
      if (inList) {
        result.push("</ul>");
        inList = false;
      }
      if (trimmed.match(/^\d+\.\s+(.+)/)) {
        const content = trimmed.replace(/^\d+\.\s+/, "");
        if (!inList) {
          result.push("<ol>");
          inList = "ol";
        }
        result.push(`<li>${content}</li>`);
      } else if (inList === "ol") {
        result.push("</ol>");
        inList = false;
        result.push(trimmed === "" ? "" : `<p>${trimmed}</p>`);
      } else {
        result.push(trimmed === "" ? "" : trimmed);
      }
    }
  }
  if (inList === "ol") result.push("</ol>");
  else if (inList) result.push("</ul>");

  return result
    .join("\n")
    .replace(/\n{2,}/g, "</p><p>")
    .replace(/\n/g, "<br>");
}

function addMessage(text, role) {
  const div = document.createElement("div");
  div.className = `message ${role}`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "You" : "🏥";

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  if (role === "user") {
    bubble.textContent = text;
  } else {
    bubble.innerHTML = renderMarkdown(text);
  }

  if (role === "user") {
    div.appendChild(bubble);
    div.appendChild(avatar);
  } else {
    div.appendChild(avatar);
    div.appendChild(bubble);
  }

  chatContainer.appendChild(div);
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

function showTyping() {
  const div = document.createElement("div");
  div.className = "message assistant";
  div.id = "typing";

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = "🏥";

  const dots = document.createElement("div");
  dots.className = "bubble typing-dots";
  dots.innerHTML = "<span></span><span></span><span></span>";

  div.appendChild(avatar);
  div.appendChild(dots);
  chatContainer.appendChild(div);
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

function hideTyping() {
  const el = document.getElementById("typing");
  if (el) el.remove();
}

async function loadHistory() {
  try {
    const res = await fetch(`/api/chat/${sessionId}`);
    const data = await res.json();
    if (data.messages && data.messages.length > 0) {
      const welcome = chatContainer.querySelector(".message.assistant");
      if (welcome) welcome.remove();
      for (const msg of data.messages) {
        addMessage(msg.content, msg.role);
      }
    }
  } catch {}
}

loadHistory();

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const message = messageInput.value.trim();
  if (!message) return;

  addMessage(message, "user");
  messageInput.value = "";
  sendBtn.disabled = true;
  showTyping();

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: sessionId }),
    });
    const data = await res.json();
    hideTyping();
    addMessage(data.response, "assistant");
  } catch {
    hideTyping();
    addMessage("Sorry, something went wrong. Please try again.", "assistant");
  } finally {
    sendBtn.disabled = false;
    messageInput.focus();
  }
});
