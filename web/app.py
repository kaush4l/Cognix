import asyncio
import json
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from core.events import event_bus, LogEvent


@asynccontextmanager
async def lifespan(app):
    event_bus.set_loop(asyncio.get_event_loop())
    yield


app = FastAPI(lifespan=lifespan)

_web_dir = Path(__file__).parent
app.mount('/static', StaticFiles(directory=_web_dir / 'static'), name='static')
templates = Jinja2Templates(directory=_web_dir / 'templates')

# Gateway is set at startup from main.py
gateway = None


def set_gateway(g):
    global gateway
    gateway = g


@app.get('/', response_class=HTMLResponse)
async def chat_page(request: Request):
    return templates.TemplateResponse(request, 'chat.html')


@app.post('/chat', response_class=HTMLResponse)
async def chat(request: Request):
    form = await request.form()
    message = form.get('message', '').strip()
    if not message or gateway is None:
        return HTMLResponse('<div class="msg bot">No input or engine not loaded.</div>')

    answer = await asyncio.to_thread(gateway.run, message, None, event_bus.emit)
    escaped = (answer or 'No response.').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return HTMLResponse(
        f'<div class="msg human" hx-swap-oob="beforeend:#messages">'
        f'<span class="label">You</span><p>{form.get("message", "").replace("<", "&lt;")}</p></div>'
        f'<div class="msg bot">'
        f'<span class="label">Agent</span><p>{escaped}</p></div>'
    )


@app.get('/events')
async def event_stream():
    async def generate():
        q = event_bus.subscribe()
        try:
            while True:
                event: LogEvent = await q.get()
                data = json.dumps(event.to_dict())
                yield f'data: {data}\n\n'
        except asyncio.CancelledError:
            pass
        finally:
            event_bus.unsubscribe(q)

    return StreamingResponse(generate(), media_type='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no',
    })
