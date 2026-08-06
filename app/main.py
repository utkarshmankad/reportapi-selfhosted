from fastapi import FastAPI
from app.api.routes import health, report
from app.config import settings

app = FastAPI(
    title="ReportAPI Self-Hosted",
    version="0.1.0",
    description="Container-native reporting engine. Runs entirely on your infrastructure.",
)

app.include_router(health.router)
app.include_router(report.router)


@app.on_event("startup")
async def startup_event():
    print(f"ReportAPI Self-Hosted starting — env={settings.app_env}, "
          f"llm_provider={settings.llm_provider}")
