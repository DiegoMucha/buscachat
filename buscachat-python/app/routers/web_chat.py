from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.adapters.green_api import Notifier
from app.config import Settings, get_settings
from app.database import get_session
from app.face import FaceMatcher
from app.messaging import MessageKind
from app.messaging.adapters.web import WEB_CHAT_ID, adapt_web_message
from app.messaging.conversation import set_conversation_state
from app.messaging.dependencies import (
    get_conversation_state_store_dependency,
    get_face_matcher_dependency,
    get_notifier_dependency,
)
from app.messaging.pipeline import run_message_pipeline
from app.messaging.session_store import ConversationStateStore
from app.messaging.web_chat_store import WebChatMessage, web_chat_store

router = APIRouter(prefix="/web-chat", tags=["web-chat"])


class WebChatSendRequest(BaseModel):
    text: str = ""
    image_ref: str | None = Field(default=None, max_length=2000)


class WebChatSendResponse(BaseModel):
    ok: bool = True
    messages: list[WebChatMessage]


class WebChatClearResponse(BaseModel):
    ok: bool = True


@router.get("", response_class=HTMLResponse, summary="Open the browser chat tester")
def web_chat_page() -> str:
    return _WEB_CHAT_HTML


@router.get("/messages", response_model=list[WebChatMessage])
def list_web_chat_messages(
    after_id: Annotated[int, Query(ge=0)] = 0,
) -> list[WebChatMessage]:
    return web_chat_store.list_messages(after_id=after_id)


@router.delete("/messages", response_model=WebChatClearResponse)
def clear_web_chat_messages(
    conversation_store: Annotated[
        ConversationStateStore,
        Depends(get_conversation_state_store_dependency),
    ],
) -> WebChatClearResponse:
    web_chat_store.clear()
    set_conversation_state(WEB_CHAT_ID, None, conversation_store)
    return WebChatClearResponse()


@router.post("/webhook", response_model=WebChatSendResponse)
def web_chat_webhook(
    payload: WebChatSendRequest,
    session: Annotated[Session, Depends(get_session)],
    matcher: Annotated[FaceMatcher, Depends(get_face_matcher_dependency)],
    notifier: Annotated[Notifier, Depends(get_notifier_dependency)],
    conversation_store: Annotated[
        ConversationStateStore,
        Depends(get_conversation_state_store_dependency),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WebChatSendResponse:
    if not payload.text.strip() and not payload.image_ref:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="text or image_ref is required",
        )

    inbound = adapt_web_message(payload.model_dump())

    # Si hay URL de imagen, descargarla para OCR
    if inbound.image_ref and inbound.kind == MessageKind.IMAGE:
        try:
            from app.utils.images import download_image

            inbound.image_bytes = download_image(
                inbound.image_ref, timeout=settings.image_download_timeout_seconds
            )
        except Exception:
            pass  # No bloquea el flujo si falla

    user_message = web_chat_store.add_user_message(inbound)
    outbound = run_message_pipeline(
        inbound,
        session=session,
        matcher=matcher,
        notifier=notifier,
        settings=settings,
        conversation_store=conversation_store,
    )
    bot_message = web_chat_store.add_bot_message(outbound)
    return WebChatSendResponse(messages=[user_message, bot_message])


_WEB_CHAT_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BuscaChat Web Tester</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #1f2937;
      --muted: #596579;
      --line: #d9dee7;
      --accent: #116149;
      --accent-ink: #ffffff;
      --bot: #eef2f7;
      --user: #dff3eb;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--ink);
    }
    .shell {
      width: min(920px, 100%);
      min-height: 100vh;
      margin: 0 auto;
      display: flex;
      flex-direction: column;
      padding: 20px;
      gap: 14px;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    h1 {
      margin: 0;
      font-size: 1.15rem;
      line-height: 1.2;
    }
    .subhead {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 0.9rem;
    }
    .status {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 6px 10px;
      color: var(--muted);
      background: var(--panel);
      font-size: 0.82rem;
      white-space: nowrap;
    }
    main {
      flex: 1;
      min-height: 420px;
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }
    #messages {
      flex: 1;
      overflow: auto;
      padding: 18px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .empty {
      margin: auto;
      max-width: 420px;
      color: var(--muted);
      text-align: center;
      line-height: 1.5;
    }
    .message {
      max-width: min(680px, 88%);
      border-radius: 8px;
      padding: 10px 12px;
      line-height: 1.45;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    .message.user {
      align-self: flex-end;
      background: var(--user);
    }
    .message.bot {
      align-self: flex-start;
      background: var(--bot);
    }
    .meta {
      display: block;
      margin-bottom: 4px;
      color: var(--muted);
      font-size: 0.75rem;
      font-weight: 600;
    }
    .buttons {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }
    button {
      border: 0;
      border-radius: 6px;
      padding: 9px 12px;
      font: inherit;
      font-weight: 650;
      cursor: pointer;
    }
    button:focus-visible, input:focus-visible {
      outline: 3px solid rgba(17, 97, 73, 0.28);
      outline-offset: 2px;
    }
    .quick {
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--ink);
    }
    .composer {
      border-top: 1px solid var(--line);
      padding: 12px;
      display: grid;
      grid-template-columns: 1fr auto auto;
      gap: 10px;
      background: #fbfcfd;
    }
    .fields {
      display: grid;
      gap: 8px;
    }
    input {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px 11px;
      font: inherit;
      color: var(--ink);
      background: var(--panel);
    }
    input::placeholder { color: #667286; }
    .send {
      align-self: end;
      background: var(--accent);
      color: var(--accent-ink);
    }
    .clear {
      align-self: end;
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--ink);
    }
    @media (max-width: 680px) {
      .shell { padding: 12px; }
      header { align-items: flex-start; flex-direction: column; }
      .composer { grid-template-columns: 1fr; }
      .send, .clear { width: 100%; }
      .message { max-width: 96%; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <div>
        <h1>BuscaChat Web Tester</h1>
        <p class="subhead">Shared in-memory chat using the generic chatbot pipeline.</p>
      </div>
      <div id="status" class="status">Polling</div>
    </header>
    <main>
      <section id="messages" aria-live="polite">
        <p class="empty">Send <strong>hola</strong> or <strong>menu</strong> to start.
        Use the optional image field only when the bot asks for a photo.</p>
      </section>
      <form id="composer" class="composer">
        <div class="fields">
          <input id="text" name="text" autocomplete="off" placeholder="Message">
          <input id="image_ref" name="image_ref" autocomplete="off" placeholder="Optional image URL or media ref">
        </div>
        <button class="send" type="submit">Send</button>
        <button class="clear" id="clear" type="button">Clear</button>
      </form>
    </main>
  </div>
  <script>
    const messagesEl = document.querySelector("#messages");
    const statusEl = document.querySelector("#status");
    const form = document.querySelector("#composer");
    const textInput = document.querySelector("#text");
    const imageInput = document.querySelector("#image_ref");
    const clearButton = document.querySelector("#clear");
    let lastId = 0;
    const seen = new Set();

    function renderMessage(message) {
      if (seen.has(message.id)) return;
      seen.add(message.id);
      const empty = messagesEl.querySelector(".empty");
      if (empty) empty.remove();

      const bubble = document.createElement("article");
      bubble.className = `message ${message.role}`;

      const meta = document.createElement("span");
      meta.className = "meta";
      meta.textContent = message.role === "user" ? "You" : "Bot";
      bubble.append(meta);

      const body = document.createElement("div");
      body.textContent = message.image_ref
        ? `${message.text || "[image]"}\\n${message.image_ref}`
        : message.text;
      bubble.append(body);

      if (message.buttons && message.buttons.length) {
        const buttons = document.createElement("div");
        buttons.className = "buttons";
        for (const item of message.buttons) {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "quick";
          button.textContent = item.title;
          button.addEventListener("click", () => sendMessage(item.id, ""));
          buttons.append(button);
        }
        bubble.append(buttons);
      }

      messagesEl.append(bubble);
      lastId = Math.max(lastId, message.id);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    async function poll() {
      try {
        const response = await fetch(`/web-chat/messages?after_id=${lastId}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const messages = await response.json();
        messages.forEach(renderMessage);
        statusEl.textContent = "Polling";
      } catch (error) {
        statusEl.textContent = "Disconnected";
      }
    }

    async function sendMessage(text, imageRef) {
      const payload = { text, image_ref: imageRef || null };
      const response = await fetch("/web-chat/webhook", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        statusEl.textContent = "Send failed";
        return;
      }
      const data = await response.json();
      data.messages.forEach(renderMessage);
      statusEl.textContent = "Polling";
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const text = textInput.value.trim();
      const imageRef = imageInput.value.trim();
      if (!text && !imageRef) return;
      textInput.value = "";
      imageInput.value = "";
      await sendMessage(text, imageRef);
      textInput.focus();
    });

    clearButton.addEventListener("click", async () => {
      await fetch("/web-chat/messages", { method: "DELETE" });
      lastId = 0;
      seen.clear();
      messagesEl.innerHTML = '<p class="empty">Chat cleared. Send <strong>hola</strong> ' +
        'or <strong>menu</strong> to start.</p>';
    });

    poll();
    setInterval(poll, 1200);
  </script>
</body>
</html>
"""
