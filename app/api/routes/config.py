"""Config routes — backs the localhost-only config UI (Jira, LLM, test connection)."""
import httpx
from fastapi import APIRouter
from app.models.config import (
    JiraConfigRequest, LLMConfigRequest, TestResult, ConfigStatus,
)
from app.core.env_writer import upsert_env_values
from app.config import settings

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("", response_model=ConfigStatus)
async def get_config_status():
    return ConfigStatus(
        app_env=settings.app_env,
        llm_provider=settings.llm_provider,
        jira_configured=bool(settings.jira_url and settings.jira_email and settings.jira_api_token),
        openai_configured=bool(settings.openai_api_key),
        anthropic_configured=bool(settings.anthropic_api_key),
        ollama_base_url=settings.ollama_base_url,
    )


@router.post("/jira/test", response_model=TestResult)
async def test_jira_connection(request: JiraConfigRequest):
    try:
        async with httpx.AsyncClient(
            auth=(request.jira_email, request.jira_api_token), timeout=10.0
        ) as client:
            response = await client.get(f"{request.jira_url.rstrip('/')}/rest/api/3/myself")
        if response.status_code == 200:
            return TestResult(ok=True, detail="Connected to Jira successfully.")
        return TestResult(ok=False, detail=f"Jira responded with status {response.status_code}.")
    except Exception as e:
        return TestResult(ok=False, detail=f"Could not reach Jira: {str(e)}")


@router.post("/jira", response_model=TestResult)
async def save_jira_config(request: JiraConfigRequest):
    upsert_env_values({
        "JIRA_URL": request.jira_url,
        "JIRA_EMAIL": request.jira_email,
        "JIRA_API_TOKEN": request.jira_api_token,
    })
    return TestResult(ok=True, detail="Saved. Restart the api/worker containers to apply.")


@router.post("/llm/test", response_model=TestResult)
async def test_llm_connection(request: LLMConfigRequest):
    try:
        if request.llm_provider == "openai":
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {request.api_key}"},
                    json={"model": "gpt-4o-mini", "max_tokens": 5,
                          "messages": [{"role": "user", "content": "ping"}]},
                )
        elif request.llm_provider == "anthropic":
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": request.api_key, "anthropic-version": "2023-06-01"},
                    json={"model": "claude-sonnet-4-5", "max_tokens": 5,
                          "messages": [{"role": "user", "content": "ping"}]},
                )
        else:  # ollama
            base_url = (request.ollama_base_url or settings.ollama_base_url).rstrip("/")
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{base_url}/api/tags")

        if response.status_code == 200:
            return TestResult(ok=True, detail=f"Connected to {request.llm_provider} successfully.")
        return TestResult(ok=False, detail=f"{request.llm_provider} responded with status {response.status_code}.")
    except Exception as e:
        return TestResult(ok=False, detail=f"Could not reach {request.llm_provider}: {str(e)}")


@router.post("/llm", response_model=TestResult)
async def save_llm_config(request: LLMConfigRequest):
    values = {"LLM_PROVIDER": request.llm_provider}
    if request.llm_provider == "openai" and request.api_key:
        values["OPENAI_API_KEY"] = request.api_key
    elif request.llm_provider == "anthropic" and request.api_key:
        values["ANTHROPIC_API_KEY"] = request.api_key
    elif request.llm_provider == "ollama" and request.ollama_base_url:
        values["OLLAMA_BASE_URL"] = request.ollama_base_url

    upsert_env_values(values)
    return TestResult(ok=True, detail="Saved. Restart the api/worker containers to apply.")
