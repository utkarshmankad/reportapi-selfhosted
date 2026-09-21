from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import config as config_routes
from app.api.routes import health, job, ops, report, report_profile, schedule, template, webhook
from app.config import settings
from app.core.config_auth import require_config_token
from app.core.errors import RequestIdMiddleware, register_error_handlers
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
app.add_middleware(RequestIdMiddleware)
register_error_handlers(app)

app.include_router(health.router)
app.include_router(job.router, dependencies=[Depends(require_config_token)])
app.include_router(report.router, dependencies=[Depends(require_config_token)])
app.include_router(report_profile.router, dependencies=[Depends(require_config_token)])
app.include_router(schedule.router, dependencies=[Depends(require_config_token)])
app.include_router(template.router, dependencies=[Depends(require_config_token)])
app.include_router(webhook.router, dependencies=[Depends(require_config_token)])
app.include_router(ops.router, dependencies=[Depends(require_config_token)])
app.include_router(config_routes.router)
