from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import config as config_routes
from app.api.routes import health, report, schedule, template
from app.config import settings
from app.core.config_auth import require_config_token

app = FastAPI(
    title="ReportAPI Self-Hosted",
    version="0.5.2",
    description="Container-native reporting engine. Runs entirely on your infrastructure.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(report.router, dependencies=[Depends(require_config_token)])
app.include_router(schedule.router, dependencies=[Depends(require_config_token)])
app.include_router(template.router, dependencies=[Depends(require_config_token)])
app.include_router(config_routes.router)


@app.on_event("startup")
async def startup_event():
    print(
        f"ReportAPI Self-Hosted starting — env={settings.app_env}, "
        f"llm_provider={settings.llm_provider}"
    )
