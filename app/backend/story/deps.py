"""Request dependencies and SSE helpers."""
from __future__ import annotations

import json
from typing import Any, AsyncIterator, Iterator

from fastapi import Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .services.runtime import AppContext


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def get_db(request: Request) -> Iterator[Session]:
    ctx: AppContext = request.app.state.ctx
    s = ctx.db.SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def sse(gen: AsyncIterator[dict[str, Any]]) -> StreamingResponse:
    async def body():
        async for ev in gen:
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(body(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
