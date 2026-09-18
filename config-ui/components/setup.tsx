import { useEffect, useState } from "react";
import {
  request,
  errorMessage,
  type Config,
  type TestResult,
} from "../lib/api";
import { Notice } from "./shared";

function ConnectionForm({
  kind,
  token,
  onSaved,
}: {
  kind: "jira" | "asana" | "github" | "llm";
  token: string;
  onSaved: () => void;
}) {
  const [provider, setProvider] = useState("openai");
  const [url, setUrl] = useState("");
  const [email, setEmail] = useState("");
  const [secret, setSecret] = useState("");
  const [result, setResult] = useState<TestResult | null>(null);
  const [busy, setBusy] = useState(false);
  const title = {
    jira: "Jira",
    asana: "Asana",
    github: "GitHub",
    llm: "LLM provider",
  }[kind];
  async function call(test: boolean) {
    setBusy(true);
    setResult(null);
    const body =
      kind === "jira"
        ? { jira_url: url, jira_email: email, jira_api_token: secret }
        : kind === "llm"
          ? {
              llm_provider: provider,
              api_key: secret || null,
              ollama_base_url:
                provider === "ollama" ? url || "http://ollama:11434" : null,
            }
          : { [`${kind}_pat`]: secret };
    try {
      const data = await request<TestResult>(
        `/config/${kind}${test ? "/test" : ""}`,
        token,
        "POST",
        body,
      );
      setResult(data);
      if (data.ok && !test) {
        setSecret("");
        onSaved();
      }
    } catch (error) {
      setResult({ ok: false, detail: errorMessage(error) });
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card" aria-label={`${title} connection`}>
      <h3>{title}</h3>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void call(false);
        }}
      >
        <fieldset disabled={busy}>
          {kind === "llm" && (
            <label>
              Provider
              <select
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
              >
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic</option>
                <option value="groq">Groq</option>
                <option value="ollama">Ollama (local)</option>
              </select>
            </label>
          )}
          {(kind === "jira" || (kind === "llm" && provider === "ollama")) && (
            <label>
              {kind === "jira" ? "Jira URL" : "Ollama URL"}
              <input
                type="url"
                value={url}
                placeholder={
                  kind === "jira"
                    ? "https://team.atlassian.net"
                    : "http://ollama:11434"
                }
                onChange={(e) => setUrl(e.target.value)}
                required={kind === "jira"}
              />
            </label>
          )}
          {kind === "jira" && (
            <label>
              Email
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </label>
          )}
          {!(kind === "llm" && provider === "ollama") && (
            <label>
              {kind === "llm" ? "API key" : "Access token"}
              <input
                type="password"
                autoComplete="off"
                value={secret}
                onChange={(e) => setSecret(e.target.value)}
                required
              />
            </label>
          )}
          <div className="actions">
            <button type="submit">
              {busy ? "Working…" : "Save connection"}
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => void call(true)}
            >
              Test connection
            </button>
          </div>
        </fieldset>
      </form>
      {result && <Notice message={result.detail} error={!result.ok} />}
    </section>
  );
}
export function Setup({ token }: { token: string }) {
  const [config, setConfig] = useState<Config | null>(null);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let active = true;
    request<Config>("/config", token)
      .then((data) => {
        if (active) {
          setConfig(data);
          setError("");
        }
      })
      .catch((e) => {
        if (active) setError(errorMessage(e));
      });
    return () => {
      active = false;
    };
  }, [token, version]);
  return (
    <>
      <header className="section-heading">
        <div>
          <p className="eyebrow">01 / CONNECT</p>
          <h2>Connections</h2>
          <p>Connect your work and choose where reports are generated.</p>
        </div>
      </header>
      <Notice message={error} error />
      {config && (
        <div className="status-bar">
          {(["jira", "asana", "github"] as const).map((kind) => (
            <span
              key={kind}
              className={config[`${kind}_configured`] ? "badge ready" : "badge"}
            >
              {kind}:{" "}
              {config[`${kind}_configured`] ? "configured" : "not configured"}
            </span>
          ))}
          <span className="badge">Provider: {config.llm_provider}</span>
        </div>
      )}
      {config?.config_read_only ? (
        <Notice message="Connections are managed by your operator. Changes are disabled here." />
      ) : (
        <div className="cards">
          {(["jira", "asana", "github", "llm"] as const).map((kind) => (
            <ConnectionForm
              key={kind}
              kind={kind}
              token={token}
              onSaved={() => setVersion((v) => v + 1)}
            />
          ))}
        </div>
      )}
    </>
  );
}
