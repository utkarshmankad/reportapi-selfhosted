from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import health, report, schedule, template, config as config_routes
from app.config import settings

app = FastAPI(
    title="ReportAPI Self-Hosted",
    version="0.1.0",
    description="Container-native reporting engine. Runs entirely on your infrastructure.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(report.router)
app.include_router(schedule.router)
app.include_router(template.router)
app.include_router(config_routes.router)


@app.on_event("startup")
async def startup_event():
    print(f"ReportAPI Self-Hosted starting — env={settings.app_env}, "
          f"llm_provider={settings.llm_provider}")
