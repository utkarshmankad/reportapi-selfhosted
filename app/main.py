from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import config as config_routes
from app.api.routes import health, job, report, schedule, template
from app.config import settings
from app.core.config_auth import require_config_token
from app.core.logging_config import configure_logging, get_logger

configure_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app):
    logger.info(
        "ReportAPI Self-Hosted starting",
        extra={"app_env": settings.app_env, "llm_provider": settings.llm_provider},
    )
    yield


app = FastAPI(
    lifespan=lifespan,
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
app.include_router(job.router, dependencies=[Depends(require_config_token)])
app.include_router(report.router, dependencies=[Depends(require_config_token)])
app.include_router(schedule.router, dependencies=[Depends(require_config_token)])
app.include_router(template.router, dependencies=[Depends(require_config_token)])
app.include_router(config_routes.router)
