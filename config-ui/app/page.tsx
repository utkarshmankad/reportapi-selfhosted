"use client";

import { useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const styles = {
  page: { maxWidth: 720, margin: "0 auto", padding: "48px 24px 80px" } as const,
  h1: { fontSize: 28, marginBottom: 4 } as const,
  sub: { color: "#8890a0", fontSize: 14.5, marginBottom: 40 } as const,
  section: {
    background: "#191d25",
    border: "1px solid #2a3040",
    borderRadius: 8,
    padding: 24,
    marginBottom: 24,
  } as const,
  h2: { fontSize: 17, marginTop: 0, marginBottom: 6 } as const,
  hint: { color: "#8890a0", fontSize: 13, marginBottom: 18 } as const,
  label: { display: "block", fontSize: 13, marginBottom: 6, color: "#c4c9d4" } as const,
  input: {
    width: "100%",
    boxSizing: "border-box" as const,
    background: "#0e1116",
    border: "1px solid #2a3040",
    borderRadius: 5,
    color: "#e7eaef",
    padding: "9px 11px",
    fontSize: 14,
    marginBottom: 14,
  },
  row: { display: "flex", gap: 10, marginTop: 4 },
  button: {
    background: "#5fd4c0",
    color: "#0e1116",
    border: "none",
    borderRadius: 5,
    padding: "9px 16px",
    fontSize: 13.5,
    fontWeight: 600,
    cursor: "pointer",
  },
  buttonSecondary: {
    background: "transparent",
    color: "#e7eaef",
    border: "1px solid #2a3040",
    borderRadius: 5,
    padding: "9px 16px",
    fontSize: 13.5,
    cursor: "pointer",
  },
  result: (ok: boolean) => ({
    marginTop: 12,
    fontSize: 13,
    color: ok ? "#5fd4c0" : "#e08e59",
  }),
  select: {
    width: "100%",
    boxSizing: "border-box" as const,
    background: "#0e1116",
    border: "1px solid #2a3040",
    borderRadius: 5,
    color: "#e7eaef",
    padding: "9px 11px",
    fontSize: 14,
    marginBottom: 14,
  },
};

function JiraForm() {
  const [jiraUrl, setJiraUrl] = useState("");
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [result, setResult] = useState<{ ok: boolean; detail: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function call(path: string) {
    setBusy(true);
    setResult(null);
    try {
      const res = await fetch(`${API_URL}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jira_url: jiraUrl, jira_email: email, jira_api_token: token }),
      });
      const data = await res.json();
      setResult(data);
    } catch (e: any) {
      setResult({ ok: false, detail: e.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section style={styles.section}>
      <h2 style={styles.h2}>Jira</h2>
      <p style={styles.hint}>Connect the board or sprint you want reported on.</p>

      <label style={styles.label}>Jira URL</label>
      <input style={styles.input} placeholder="https://yourcompany.atlassian.net"
        value={jiraUrl} onChange={(e) => setJiraUrl(e.target.value)} />

      <label style={styles.label}>Email</label>
      <input style={styles.input} placeholder="you@company.com"
        value={email} onChange={(e) => setEmail(e.target.value)} />

      <label style={styles.label}>API token</label>
      <input style={styles.input} type="password" placeholder="••••••••"
        value={token} onChange={(e) => setToken(e.target.value)} />

      <div style={styles.row}>
        <button style={styles.buttonSecondary} disabled={busy} onClick={() => call("/api/config/jira/test")}>
          Test connection
        </button>
        <button style={styles.button} disabled={busy} onClick={() => call("/api/config/jira")}>
          Save
        </button>
      </div>

      {result && <div style={styles.result(result.ok)}>{result.detail}</div>}
    </section>
  );
}

function AsanaForm() {
  const [pat, setPat] = useState("");
  const [result, setResult] = useState<{ ok: boolean; detail: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function call(path: string) {
    setBusy(true);
    setResult(null);
    try {
      const res = await fetch(`${API_URL}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ asana_pat: pat }),
      });
      const data = await res.json();
      setResult(data);
    } catch (e: any) {
      setResult({ ok: false, detail: e.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section style={styles.section}>
      <h2 style={styles.h2}>Asana</h2>
      <p style={styles.hint}>Connect a project (or a section within one) you want reported on.</p>

      <label style={styles.label}>Personal Access Token</label>
      <input style={styles.input} type="password" placeholder="••••••••"
        value={pat} onChange={(e) => setPat(e.target.value)} />

      <div style={styles.row}>
        <button style={styles.buttonSecondary} disabled={busy} onClick={() => call("/api/config/asana/test")}>
          Test connection
        </button>
        <button style={styles.button} disabled={busy} onClick={() => call("/api/config/asana")}>
          Save
        </button>
      </div>

      {result && <div style={styles.result(result.ok)}>{result.detail}</div>}
    </section>
  );
}

function GitHubForm() {
  const [pat, setPat] = useState("");
  const [result, setResult] = useState<{ ok: boolean; detail: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function call(path: string) {
    setBusy(true);
    setResult(null);
    try {
      const res = await fetch(`${API_URL}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ github_pat: pat }),
      });
      const data = await res.json();
      setResult(data);
    } catch (e: any) {
      setResult({ ok: false, detail: e.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section style={styles.section}>
      <h2 style={styles.h2}>GitHub Issues</h2>
      <p style={styles.hint}>Connect a repo (or a milestone within one) you want reported on.</p>

      <label style={styles.label}>Personal Access Token</label>
      <input style={styles.input} type="password" placeholder="••••••••"
        value={pat} onChange={(e) => setPat(e.target.value)} />

      <div style={styles.row}>
        <button style={styles.buttonSecondary} disabled={busy} onClick={() => call("/api/config/github/test")}>
          Test connection
        </button>
        <button style={styles.button} disabled={busy} onClick={() => call("/api/config/github")}>
          Save
        </button>
      </div>

      {result && <div style={styles.result(result.ok)}>{result.detail}</div>}
    </section>
  );
}

function LLMForm() {
  const [provider, setProvider] = useState("openai");
  const [apiKey, setApiKey] = useState("");
  const [ollamaUrl, setOllamaUrl] = useState("http://ollama:11434");
  const [result, setResult] = useState<{ ok: boolean; detail: string } | null>(null);
  const [busy, setBusy] = useState(false);

  function body() {
    return {
      llm_provider: provider,
      api_key: apiKey || null,
      ollama_base_url: provider === "ollama" ? ollamaUrl : null,
    };
  }

  async function call(path: string) {
    setBusy(true);
    setResult(null);
    try {
      const res = await fetch(`${API_URL}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body()),
      });
      const data = await res.json();
      setResult(data);
    } catch (e: any) {
      setResult({ ok: false, detail: e.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section style={styles.section}>
      <h2 style={styles.h2}>LLM provider</h2>
      <p style={styles.hint}>Choose what generates the narrative. Ollama runs fully local.</p>

      <label style={styles.label}>Provider</label>
      <select style={styles.select} value={provider} onChange={(e) => setProvider(e.target.value)}>
        <option value="openai">OpenAI</option>
        <option value="anthropic">Anthropic</option>
        <option value="groq">Groq</option>
        <option value="ollama">Ollama (local)</option>
      </select>

      {provider !== "ollama" ? (
        <>
          <label style={styles.label}>API key</label>
          <input style={styles.input} type="password" placeholder="••••••••"
            value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
        </>
      ) : (
        <>
          <label style={styles.label}>Ollama base URL</label>
          <input style={styles.input} value={ollamaUrl} onChange={(e) => setOllamaUrl(e.target.value)} />
        </>
      )}

      <div style={styles.row}>
        <button style={styles.buttonSecondary} disabled={busy} onClick={() => call("/api/config/llm/test")}>
          Test connection
        </button>
        <button style={styles.button} disabled={busy} onClick={() => call("/api/config/llm")}>
          Save
        </button>
      </div>

      {result && <div style={styles.result(result.ok)}>{result.detail}</div>}
    </section>
  );
}

function ScheduleForm() {
  const [connector, setConnector] = useState("jira");
  const [boardId, setBoardId] = useState("");
  const [sprintId, setSprintId] = useState("");
  const [cron, setCron] = useState("0 9 * * 1");
  const [outputFormat, setOutputFormat] = useState("text");
  const [result, setResult] = useState<{ ok: boolean; detail: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function create() {
    setBusy(true);
    setResult(null);
    try {
      const res = await fetch(`${API_URL}/api/schedule`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          connector,
          board_id: boardId || null,
          sprint_id: sprintId || null,
          cron_expression: cron,
          output_format: outputFormat,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        setResult({ ok: true, detail: `Schedule created (runs on: ${cron}).` });
      } else {
        setResult({ ok: false, detail: data.detail || "Could not create schedule." });
      }
    } catch (e: any) {
      setResult({ ok: false, detail: e.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section style={styles.section}>
      <h2 style={styles.h2}>Schedule</h2>
      <p style={styles.hint}>Reports generate automatically on this cadence via Celery beat.</p>

      <label style={styles.label}>Connector</label>
      <select style={styles.select} value={connector} onChange={(e) => setConnector(e.target.value)}>
        <option value="jira">Jira</option>
        <option value="asana">Asana</option>
        <option value="github">GitHub Issues</option>
      </select>

      <label style={styles.label}>
        {connector === "asana" ? "Project GID" : connector === "github" ? "Repo (owner/repo)" : "Board key"}
      </label>
      <input style={styles.input}
        placeholder={connector === "asana" ? "1201234567890" : connector === "github" ? "acme/widgets" : "PROJ"}
        value={boardId} onChange={(e) => setBoardId(e.target.value)} />

      <label style={styles.label}>
        {connector === "asana"
          ? "Section GID (optional, overrides project)"
          : connector === "github"
          ? "Milestone number (optional, filters within repo)"
          : "Sprint ID (optional, overrides board)"}
      </label>
      <input style={styles.input} value={sprintId} onChange={(e) => setSprintId(e.target.value)} />

      <label style={styles.label}>Cron expression</label>
      <input style={styles.input} value={cron} onChange={(e) => setCron(e.target.value)} />

      <label style={styles.label}>Output format</label>
      <select style={styles.select} value={outputFormat} onChange={(e) => setOutputFormat(e.target.value)}>
        <option value="text">Text</option>
        <option value="markdown">Markdown</option>
        <option value="pdf">PDF</option>
      </select>

      <div style={styles.row}>
        <button style={styles.button} disabled={busy} onClick={create}>
          Create schedule
        </button>
      </div>

      {result && <div style={styles.result(result.ok)}>{result.detail}</div>}
    </section>
  );
}

export default function Home() {
  return (
    <main style={styles.page}>
      <h1 style={styles.h1}>ReportAPI setup</h1>
      <p style={styles.sub}>Connect Jira, Asana, or GitHub Issues, choose your LLM, and schedule reports — no terminal required.</p>
      <JiraForm />
      <AsanaForm />
      <GitHubForm />
      <LLMForm />
      <ScheduleForm />
    </main>
  );
}
