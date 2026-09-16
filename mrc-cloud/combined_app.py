from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import trend_v1 as live
from research_v1 import router as research_router, service as research_service

app = live.app
app.include_router(research_router)
_original_lifespan = app.router.lifespan_context

@asynccontextmanager
async def _combined_lifespan(app_obj):
    async with _original_lifespan(app_obj):
        task = research_service.start(force=False)
        try:
            yield
        finally:
            if task and not task.done():
                task.cancel()

app.router.lifespan_context = _combined_lifespan
