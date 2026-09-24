from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import uvicorn
from contextlib import asynccontextmanager
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import settings
from app.core.models.schema import init_db
from app.api.routes import api
from app.scheduler import scheduler
from app.core.logging_config import setup_logging, get_logger

logger = get_logger(__name__)


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject request bodies larger than settings.MAX_BODY_BYTES (413)."""

    async def dispatch(self, request: Request, call_next):
        raw_len = request.headers.get("content-length")
        if raw_len and raw_len.isdigit() and int(raw_len) > settings.MAX_BODY_BYTES:
            return JSONResponse(
                status_code=413,
                content={"detail": f"payload too large (max {settings.MAX_BODY_BYTES} bytes)"},
            )
        return await call_next(request)


class OptionalAuthMiddleware(BaseHTTPMiddleware):
    """Bearer-token gate, active only when AUTH_TOKEN is configured.

    /health stays open so the Compose healthcheck works without secrets;
    /static assets are same-origin UI bundles, also open.
    """

    _PUBLIC = {"/health"}

    async def dispatch(self, request: Request, call_next):
        token = settings.AUTH_TOKEN
        if not token or request.url.path in self._PUBLIC or request.url.path.startswith("/static"):
            return await call_next(request)

        import secrets
        provided = request.headers.get("authorization", "")
        if provided.lower().startswith("bearer "):
            provided = provided[7:].strip()
        else:
            provided = provided.strip() or request.query_params.get("token", "")
        if not provided or not secrets.compare_digest(provided, token):
            return JSONResponse(status_code=401, content={"detail": "unauthorized"})
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database and scheduler
    setup_logging("INFO", "data/app.log")
    init_db()
    logger.info("Database initialized.")
    scheduler.start()
    yield
    # Shutdown
    scheduler.shutdown()
    logger.info("Cleanup complete.")


app = FastAPI(
    title="VN Investment Intelligence",
    description="Local-first fund-following investment intelligence system",
    version="1.0.0",
    lifespan=lifespan
)

# Local-only CORS (same-origin UI does not need it; prevents browser abuse)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8001",
        "http://127.0.0.1:8001",
    ],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)
# Order: added last runs first → auth → body limit → routes
app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(OptionalAuthMiddleware)

# Jinja2 environment with synchronous rendering (async causes issues)
jinja_env = Environment(
    loader=FileSystemLoader("app/templates"),
    autoescape=select_autoescape(['html', 'xml']),
    cache_size=0,
    enable_async=False,  # Disable async rendering to avoid unhashable dict error
)

# Custom template renderer
class SyncTemplates:
    def __init__(self, env):
        self.env = env

    def TemplateResponse(self, name: str, context: dict, status_code: int = 200, headers: dict = None):
        template = self.env.get_template(name)
        content = template.render(context)
        return HTMLResponse(content=content, status_code=status_code, headers=headers)

templates = SyncTemplates(jinja_env)

# Mount static
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include API routes
app.include_router(api)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# UI Partial routes (for HTMX navigation)
@app.get("/ui/{view}", response_class=HTMLResponse)
async def ui_partial(view: str, request: Request):
    valid_views = ['shortlist', 'portfolio', 'events', 'track-record', 'settings']
    if view not in valid_views:
        return HTMLResponse(content="View not found", status_code=404)
    logger.debug("Rendering view: %s", view)
    return templates.TemplateResponse(f"{view}.html", {"request": request})


# ============================================================
# HEALTH (DB + market-data + LLM dependency status)
# ============================================================

def _probe_db() -> dict:
    from sqlalchemy import inspect, text
    from app.core.models.schema import engine
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
    try:
        if not inspect(engine).has_table("funds"):
            return {
                "status": "error",
                "error": "schema missing (no 'funds' table) — run `alembic upgrade head` then `python -m app.storage.seed`",
            }
    except Exception as e:
        return {"status": "error", "error": f"schema inspect failed: {type(e).__name__}: {e}"}
    return {"status": "ok"}


def _probe_market_data(timeout: float = 8.0) -> dict:
    from concurrent.futures import ThreadPoolExecutor
    from concurrent.futures import TimeoutError as FuturesTimeout

    def probe():
        from datetime import date, timedelta
        from vnstock.api.quote import Quote
        today = date.today()
        df = Quote(symbol="VNINDEX", source="VCI").history(
            start=(today - timedelta(days=7)).isoformat(),
            end=today.isoformat(),
        )
        if df is None or df.empty:
            raise RuntimeError("vnstock returned empty history for VNINDEX")

    ex = ThreadPoolExecutor(max_workers=1)
    try:
        ex.submit(probe).result(timeout=timeout)
        return {"status": "ok", "provider": "vnstock/VCI"}
    except FuturesTimeout:
        return {"status": "error", "error": f"vnstock probe timed out after {timeout}s"}
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
    finally:
        ex.shutdown(wait=False, cancel_futures=True)


def _probe_llm() -> dict:
    import shutil
    from app.config import settings
    oc = shutil.which(settings.OPENCODE_BIN)
    if oc:
        return {
            "status": "ok",
            "provider": "opencode",
            "binary": oc,
            "default_model": settings.OPENCODE_DEFAULT_MODEL,
        }
    ol = shutil.which("ollama")
    if ol:
        return {"status": "ok", "provider": "ollama", "binary": ol}
    return {
        "status": "error",
        "error": f"no LLM provider: '{settings.OPENCODE_BIN}' not in PATH and 'ollama' not found — LLM jobs will fail",
    }


@app.get("/health")
def health():
    checks = {
        "database": _probe_db(),
        "market_data": _probe_market_data(),
        "llm": _probe_llm(),
    }
    failed = [name for name, res in checks.items() if res.get("status") != "ok"]
    body = {"status": "ok" if not failed else "error", "dependencies": checks}
    if failed:
        body["error"] = "failed dependencies: " + ", ".join(failed)
    return JSONResponse(status_code=200 if not failed else 503, content=body)


# Test LLM endpoint
@app.post("/api/test-llm")
async def test_llm():
    try:
        import subprocess, json
        result = subprocess.run(
            ["opencode", "run", "--pure", "-m", "opencode/big-pickle",
             "--title", "test", "--format", "json",
             "Chỉ trả lời JSON: {\"ok\": true, \"message\": \"Test thành công\"}"],
            capture_output=True, text=True, timeout=60
        )
        # Parse streaming JSON events
        for line in result.stdout.strip().split('\n'):
            try:
                evt = json.loads(line)
                if evt.get('type') == 'text':
                    return {"ok": True, "response": evt.get('part', {}).get('text', '')}
            except:
                pass
        return {"ok": True, "response": "Connected"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# Manual job trigger endpoints
@app.post("/api/jobs/ingestion")
async def trigger_ingestion():
    from app.ingestion.pipeline.main import run_ingestion_job
    return run_ingestion_job()


@app.post("/api/jobs/opportunity-scan")
async def trigger_opportunity_scan():
    from app.core.engines.opportunity_engine import run_opportunity_scan_job
    return run_opportunity_scan_job()


@app.post("/api/jobs/portfolio-reeval")
async def trigger_portfolio_reeval():
    from app.core.engines.portfolio_engine import run_portfolio_reevaluation_job
    return run_portfolio_reevaluation_job()


@app.post("/api/jobs/evaluation")
async def trigger_evaluation():
    from app.core.engines.evaluation_engine import run_evaluation_job
    return run_evaluation_job()


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
