from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uvicorn
from contextlib import asynccontextmanager
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import settings
from app.core.models.schema import init_db
from app.api.routes import api
from app.scheduler import scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database and scheduler
    init_db()
    print("[startup] Database initialized.")
    scheduler.start()
    yield
    # Shutdown
    scheduler.shutdown()
    print("[shutdown] Cleanup complete.")


app = FastAPI(
    title="VN Investment Intelligence",
    description="Local-first fund-following investment intelligence system",
    version="1.0.0",
    lifespan=lifespan
)

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
    # Debug: print which view is being rendered
    print(f"[DEBUG] Rendering view: {view}")
    return templates.TemplateResponse(f"{view}.html", {"request": request})


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
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
