"""
WebChat Platform Adapter

Browser-based chat interface for Hermes. Serves a single-page chat UI
and handles messages via WebSocket. Useful for longer research sessions
where Telegram's formatting/length limits are restrictive.

Requires: aiohttp (already in messaging extras)

Config (.env):
    WEBCHAT_PORT=8765           # Default port
    WEBCHAT_TOKEN=<secret>      # Optional auth token
"""

import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional

from .base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
)
from gateway.session import SessionSource
from gateway.config import Platform

logger = logging.getLogger(__name__)

WEBCHAT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hermes Chat</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #0d1117; color: #c9d1d9; height: 100vh; display: flex; flex-direction: column; }
  #header { padding: 12px 20px; background: #161b22; border-bottom: 1px solid #30363d;
            display: flex; align-items: center; gap: 10px; }
  #header h1 { font-size: 16px; font-weight: 600; color: #58a6ff; }
  #header .status { font-size: 12px; color: #8b949e; }
  #header .status.connected { color: #3fb950; }
  #messages { flex: 1; overflow-y: auto; padding: 16px 20px; display: flex;
              flex-direction: column; gap: 12px; }
  .msg { max-width: 80%; padding: 10px 14px; border-radius: 12px; line-height: 1.5;
         font-size: 14px; word-wrap: break-word; white-space: pre-wrap; }
  .msg.user { align-self: flex-end; background: #1f6feb; color: #fff; border-bottom-right-radius: 4px; }
  .msg.bot { align-self: flex-start; background: #21262d; border: 1px solid #30363d;
             border-bottom-left-radius: 4px; }
  .msg.bot code { background: #161b22; padding: 2px 6px; border-radius: 4px; font-size: 13px; }
  .msg.bot pre { background: #161b22; padding: 8px 12px; border-radius: 6px; overflow-x: auto;
                 margin: 6px 0; font-size: 13px; }
  .msg.system { align-self: center; background: transparent; color: #8b949e; font-size: 12px;
                font-style: italic; }
  .typing { align-self: flex-start; color: #8b949e; font-size: 13px; padding: 4px 0; }
  #input-area { padding: 12px 20px; background: #161b22; border-top: 1px solid #30363d;
                display: flex; gap: 10px; }
  #input { flex: 1; background: #0d1117; border: 1px solid #30363d; color: #c9d1d9;
           border-radius: 8px; padding: 10px 14px; font-size: 14px; font-family: inherit;
           resize: none; outline: none; min-height: 40px; max-height: 120px; }
  #input:focus { border-color: #58a6ff; }
  #send-btn { background: #1f6feb; color: #fff; border: none; border-radius: 8px;
              padding: 10px 20px; font-size: 14px; cursor: pointer; font-weight: 500; }
  #send-btn:hover { background: #388bfd; }
  #send-btn:disabled { opacity: 0.5; cursor: default; }
</style>
</head>
<body>
<div id="header">
  <h1>Hermes</h1>
  <span id="status" class="status">Connecting...</span>
</div>
<div id="messages"></div>
<div id="input-area">
  <textarea id="input" rows="1" placeholder="Type a message..." autofocus></textarea>
  <button id="send-btn">Send</button>
</div>
<script>
const token = new URLSearchParams(window.location.search).get('token') || '';
const wsUrl = `ws://${window.location.host}/ws?token=${encodeURIComponent(token)}`;
let ws;
let reconnectDelay = 1000;

function connect() {
  ws = new WebSocket(wsUrl);
  ws.onopen = () => {
    document.getElementById('status').textContent = 'Connected';
    document.getElementById('status').className = 'status connected';
    reconnectDelay = 1000;
  };
  ws.onclose = () => {
    document.getElementById('status').textContent = 'Disconnected';
    document.getElementById('status').className = 'status';
    setTimeout(connect, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, 10000);
  };
  ws.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.type === 'response') addMsg(data.text, 'bot');
    else if (data.type === 'typing') showTyping(true);
    else if (data.type === 'typing_stop') showTyping(false);
  };
}

function addMsg(text, cls) {
  showTyping(false);
  const el = document.createElement('div');
  el.className = 'msg ' + cls;
  // Basic markdown: **bold**, `code`, ```blocks```
  let html = text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/```([\\s\\S]*?)```/g, '<pre>$1</pre>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\\*\\*([^*]+)\\*\\*/g, '<strong>$1</strong>');
  el.innerHTML = html;
  document.getElementById('messages').appendChild(el);
  el.scrollIntoView({behavior: 'smooth'});
}

function showTyping(show) {
  let el = document.getElementById('typing-indicator');
  if (show && !el) {
    el = document.createElement('div');
    el.id = 'typing-indicator';
    el.className = 'typing';
    el.textContent = 'Hermes is thinking...';
    document.getElementById('messages').appendChild(el);
    el.scrollIntoView({behavior: 'smooth'});
  } else if (!show && el) {
    el.remove();
  }
}

function send() {
  const input = document.getElementById('input');
  const text = input.value.trim();
  if (!text || !ws || ws.readyState !== 1) return;
  addMsg(text, 'user');
  ws.send(JSON.stringify({type: 'message', text}));
  input.value = '';
  input.style.height = 'auto';
}

document.getElementById('send-btn').onclick = send;
document.getElementById('input').onkeydown = (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
};
// Auto-resize textarea
document.getElementById('input').oninput = function() {
  this.style.height = 'auto';
  this.style.height = Math.min(this.scrollHeight, 120) + 'px';
};
connect();
</script>
</body>
</html>"""


class WebChatAdapter(BasePlatformAdapter):
    """WebSocket-based browser chat adapter."""

    name = "webchat"
    _ws_clients: dict  # ws_id -> websocket

    def __init__(self, config=None):
        super().__init__(config)
        self._ws_clients = {}
        self._port = int(os.getenv("WEBCHAT_PORT", "8765"))
        self._token = os.getenv("WEBCHAT_TOKEN", "")
        self._app = None
        self._runner = None

    async def connect(self) -> bool:
        try:
            import aiohttp.web as web
        except ImportError:
            logger.error("WebChat requires aiohttp. Install with: pip install aiohttp")
            return False

        self._app = web.Application()
        self._app.router.add_get("/", self._handle_http)
        self._app.router.add_get("/ws", self._handle_ws)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self._port)
        await site.start()
        logger.info("WebChat server running on http://0.0.0.0:%d", self._port)
        return True

    async def disconnect(self):
        for ws in list(self._ws_clients.values()):
            await ws.close()
        self._ws_clients.clear()
        if self._runner:
            await self._runner.cleanup()

    async def _handle_http(self, request):
        import aiohttp.web as web
        # Check token if configured
        if self._token:
            token = request.query.get("token", "")
            if token != self._token:
                return web.Response(text="Unauthorized. Add ?token=<your_token> to the URL.", status=401)
        return web.Response(text=WEBCHAT_HTML, content_type="text/html")

    async def _handle_ws(self, request):
        import aiohttp.web as web
        import aiohttp

        # Check token
        if self._token:
            token = request.query.get("token", "")
            if token != self._token:
                return web.Response(text="Unauthorized", status=401)

        ws = web.WebSocketResponse()
        await ws.prepare(request)
        ws_id = str(uuid.uuid4())[:8]
        self._ws_clients[ws_id] = ws
        logger.info("WebChat client connected: %s", ws_id)

        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        if data.get("type") == "message":
                            event = MessageEvent(
                                text=data["text"],
                                source=SessionSource(
                                    platform=Platform.LOCAL,
                                    chat_id=f"webchat:{ws_id}",
                                    chat_name="WebChat",
                                    chat_type="dm",
                                    user_id=f"webchat:{ws_id}",
                                    user_name="WebChat User",
                                ),
                                message_id=str(uuid.uuid4())[:8],
                                message_type=MessageType.TEXT,
                            )
                            # Store ws reference for response routing
                            event._webchat_ws_id = ws_id
                            await self.handle_message(event)
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning("WebChat bad message: %s", e)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error("WebChat ws error: %s", ws.exception())
        finally:
            del self._ws_clients[ws_id]
            logger.info("WebChat client disconnected: %s", ws_id)

        return ws

    async def send(self, chat_id: str, content: str, **kwargs) -> SendResult:
        # chat_id format: "webchat:<ws_id>"
        ws_id = chat_id.split(":", 1)[1] if ":" in chat_id else chat_id
        ws = self._ws_clients.get(ws_id)
        if ws and not ws.closed:
            try:
                await ws.send_json({"type": "response", "text": content})
                return SendResult(success=True, message_id=str(uuid.uuid4())[:8])
            except Exception as e:
                return SendResult(success=False, error=str(e))
        return SendResult(success=False, error="Client not connected")

    async def send_typing(self, chat_id: str, **kwargs):
        ws_id = chat_id.split(":", 1)[1] if ":" in chat_id else chat_id
        ws = self._ws_clients.get(ws_id)
        if ws and not ws.closed:
            try:
                await ws.send_json({"type": "typing"})
            except Exception:
                pass

    async def edit_message(self, chat_id: str, message_id: str, content: str, **kwargs) -> SendResult:
        # WebChat doesn't support editing - just send as new message
        return await self.send(chat_id, content, **kwargs)

    async def send_image(self, chat_id: str, image_url: str, **kwargs) -> SendResult:
        return await self.send(chat_id, f"![image]({image_url})")

    async def send_voice(self, chat_id: str, audio_path: str, **kwargs) -> SendResult:
        return await self.send(chat_id, f"[Voice message: {audio_path}]")

    async def send_document(self, chat_id: str, file_path: str, **kwargs) -> SendResult:
        return await self.send(chat_id, f"[Document: {file_path}]")

    async def send_animation(self, chat_id: str, animation_url: str, **kwargs) -> SendResult:
        return await self.send(chat_id, f"![animation]({animation_url})")

    async def send_video(self, chat_id: str, video_path: str, **kwargs) -> SendResult:
        return await self.send(chat_id, f"[Video: {video_path}]")

    async def send_image_file(self, chat_id: str, image_path: str, **kwargs) -> SendResult:
        return await self.send(chat_id, f"[Image: {image_path}]")
