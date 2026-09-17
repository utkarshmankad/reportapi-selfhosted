"""Config routes — backs the localhost-only config UI (Jira, LLM, test connection)."""

import httpx
from fastapi import APIRouter, Depends

from app.config import reload_runtime_settings
from app.core.config_auth import require_config_token
from app.core.env_writer import InvalidEnvValueError, upsert_env_values
from app.core.ssrf_guard import UnsafeURLError, safe_client, validate_target
from app.models.config import (
    AsanaConfigRequest,
    ConfigStatus,
    GitHubConfigRequest,
    JiraConfigRequest,
    LLMConfigRequest,
    TestResult,
)

router = APIRouter(
    prefix="/api/config", tags=["config"], dependencies=[Depends(require_config_token)]
)


@router.get("", response_model=ConfigStatus)
async def get_config_status():
    config = reload_runtime_settings()
    return ConfigStatus(
        config_read_only=config.config_read_only,
        app_env=config.app_env,
        llm_provider=config.llm_provider,
        jira_configured=bool(config.jira_url and config.jira_email and config.jira_api_token),
        asana_configured=bool(config.asana_pat),
        github_configured=bool(config.github_pat),
        openai_configured=bool(config.openai_api_key),
        anthropic_configured=bool(config.anthropic_api_key),
        ollama_base_url=config.ollama_base_url,
        groq_configured=bool(config.groq_api_key),
    )


@router.post("/jira/test", response_model=TestResult)
async def test_jira_connection(request: JiraConfigRequest):
    # Jira URL should always be a public Atlassian Cloud host — never a
    # private/internal address, so no allow_private here.
    try:
        await validate_target(request.jira_url, "jira")
    except (UnsafeURLError, TimeoutError) as e:
        return TestResult(ok=False, detail=f"Refusing to test that URL: {e}")

    try:
        async with safe_client(
            request.jira_url,
            "jira",
            auth=(request.jira_email, request.jira_api_token),
            timeout=10.0,
        ) as client:
            response = await client.get(f"{request.jira_url.rstrip('/')}/rest/api/3/myself")
        if response.status_code == 200:
            return TestResult(ok=True, detail="Connected to Jira successfully.")
        return TestResult(ok=False, detail=f"Jira responded with status {response.status_code}.")
    except Exception:
        return TestResult(ok=False, detail="Could not reach Jira. Check connection settings.")


@router.post("/jira", response_model=TestResult)
async def save_jira_config(request: JiraConfigRequest):
    try:
        await validate_target(request.jira_url, "jira")
        upsert_env_values(
            {
                "JIRA_URL": request.jira_url,
                "JIRA_EMAIL": request.jira_email,
                "JIRA_API_TOKEN": request.jira_api_token,
            }
        )
    except (InvalidEnvValueError, UnsafeURLError, TimeoutError) as e:
        return TestResult(ok=False, detail=str(e))
    reload_runtime_settings()
    return TestResult(ok=True, detail="Saved. New reports will use these settings.")


@router.post("/asana/test", response_model=TestResult)
async def test_asana_connection(request: AsanaConfigRequest):
    # Asana's API is a fixed host — no user-supplied URL, so no SSRF check needed.
    try:
        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {request.asana_pat}"},
            timeout=10.0,
            follow_redirects=False,
        ) as client:
            response = await client.get("https://app.asana.com/api/1.0/users/me")
        if response.status_code == 200:
            return TestResult(ok=True, detail="Connected to Asana successfully.")
        return TestResult(ok=False, detail=f"Asana responded with status {response.status_code}.")
    except Exception:
        return TestResult(ok=False, detail="Could not reach Asana. Check connection settings.")


@router.post("/asana", response_model=TestResult)
async def save_asana_config(request: AsanaConfigRequest):
    try:
        upsert_env_values({"ASANA_PAT": request.asana_pat})
    except (InvalidEnvValueError, UnsafeURLError, TimeoutError) as e:
        return TestResult(ok=False, detail=str(e))
    reload_runtime_settings()
    return TestResult(ok=True, detail="Saved. New reports will use these settings.")


@router.post("/github/test", response_model=TestResult)
async def test_github_connection(request: GitHubConfigRequest):
    # GitHub's API is a fixed host — no user-supplied URL, so no SSRF check needed.
    try:
        async with httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {request.github_pat}",
                "Accept": "application/vnd.github+json",
            },
            timeout=10.0,
            follow_redirects=False,
        ) as client:
            response = await client.get("https://api.github.com/user")
        if response.status_code == 200:
            return TestResult(ok=True, detail="Connected to GitHub successfully.")
        return TestResult(ok=False, detail=f"GitHub responded with status {response.status_code}.")
    except Exception:
        return TestResult(ok=False, detail="Could not reach GitHub. Check connection settings.")


@router.post("/github", response_model=TestResult)
async def save_github_config(request: GitHubConfigRequest):
    try:
        upsert_env_values({"GITHUB_PAT": request.github_pat})
    except (InvalidEnvValueError, UnsafeURLError, TimeoutError) as e:
        return TestResult(ok=False, detail=str(e))
    reload_runtime_settings()
    return TestResult(ok=True, detail="Saved. New reports will use these settings.")


@router.post("/llm/test", response_model=TestResult)
async def test_llm_connection(request: LLMConfigRequest):
    try:
        if request.llm_provider == "openai":
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {request.api_key}"},
                    json={
                        "model": "gpt-4o-mini",
                        "max_tokens": 5,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )
        elif request.llm_provider == "anthropic":
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": request.api_key, "anthropic-version": "2023-06-01"},
                    json={
                        "model": "claude-sonnet-4-5",
                        "max_tokens": 5,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )
        elif request.llm_provider == "groq":
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
                response = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {request.api_key}"},
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "max_tokens": 5,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )
        else:  # ollama — intentionally reachable on the private docker
            # network, but still blocked from loopback/link-local/metadata.
            base_url = (
                request.ollama_base_url or reload_runtime_settings().ollama_base_url
            ).rstrip("/")
            try:
                await validate_target(base_url, "ollama")
            except (UnsafeURLError, TimeoutError) as e:
                return TestResult(ok=False, detail=f"Refusing to test that URL: {e}")

            async with safe_client(base_url, "ollama", timeout=10.0) as client:
                response = await client.get(f"{base_url}/api/tags")

        if response.status_code == 200:
            return TestResult(ok=True, detail=f"Connected to {request.llm_provider} successfully.")
        return TestResult(
            ok=False, detail=f"{request.llm_provider} responded with status {response.status_code}."
        )
    except Exception:
        return TestResult(
            ok=False, detail=f"Could not reach {request.llm_provider}. Check connection settings."
        )


@router.post("/llm", response_model=TestResult)
async def save_llm_config(request: LLMConfigRequest):
    values = {"LLM_PROVIDER": request.llm_provider}
    if request.llm_provider == "openai" and request.api_key:
        values["OPENAI_API_KEY"] = request.api_key
    elif request.llm_provider == "anthropic" and request.api_key:
        values["ANTHROPIC_API_KEY"] = request.api_key
    elif request.llm_provider == "groq" and request.api_key:
        values["GROQ_API_KEY"] = request.api_key
    elif request.llm_provider == "ollama" and request.ollama_base_url:
        values["OLLAMA_BASE_URL"] = request.ollama_base_url

    try:
        if request.llm_provider == "ollama":
            await validate_target(
                request.ollama_base_url or reload_runtime_settings().ollama_base_url, "ollama"
            )
        upsert_env_values(values)
    except (InvalidEnvValueError, UnsafeURLError, TimeoutError) as e:
        return TestResult(ok=False, detail=str(e))
    reload_runtime_settings()
    return TestResult(ok=True, detail="Saved. New reports will use these settings.")
