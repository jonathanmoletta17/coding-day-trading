from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import trend_v1
from research_v1 import router as research_router, service as research_service

app = trend_v1.app
app.include_router(research_router)

# Keep the live trading engine's lifespan intact and add research as an isolated
# background task. A research failure must never stop PAPER market polling.
_original_lifespan = app.router.lifespan_context

@asynccontextmanager
async def combined_lifespan(fastapi_app):
    async with _original_lifespan(fastapi_app):
        research_service.start(force=False)
        try:
            yield
        finally:
            task = research_service.task
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

app.router.lifespan_context = combined_lifespan

# Small navigation link; the original root handler reads trend_v1.HTML at
# request time, so this does not replace or duplicate the dashboard.
if "/research" not in trend_v1.HTML:
    trend_v1.HTML = trend_v1.HTML.replace(
        "</header>",
        "<a href='/research' style='color:#8fd3ff;text-decoration:none;font-weight:700;margin-left:16px'>30-day Research →</a></header>",
        1,
    )
