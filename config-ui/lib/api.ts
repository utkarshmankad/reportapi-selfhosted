export type Connector = "jira" | "asana" | "github";
export type Format = "text" | "markdown" | "pdf";
export interface Scope {
  connector: Connector;
  board_id: string;
  sprint_id: string;
}
export interface Report {
  id: string;
  connector: string;
  status: string;
  narrative: string | null;
  model_used: string;
  tokens_used: number;
  ticket_count?: number;
  created_at: string;
  output_format: string;
  template_id?: string | null;
  template_version?: number | null;
}
export interface Schedule extends Scope {
  id: string;
  cron_expression: string;
  output_format: Format;
  active: boolean;
  last_run_at: string | null;
  last_attempted_at?: string | null;
}
export type JobStatus = "queued" | "running" | "succeeded" | "failed";
export interface Job {
  id: string;
  status: JobStatus;
  connector: string;
  board_id: string | null;
  sprint_id: string | null;
  output_format: string;
  report_id: string | null;
  error_reason: string | null;
  attempts: number;
  schedule_id: string | null;
  scheduled_for: string | null;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}
export interface Template {
  id: string;
  name: string;
  content: string;
  version: number;
  archived: boolean;
}
export interface Config {
  config_read_only: boolean;
  llm_provider: string;
  jira_configured: boolean;
  asana_configured: boolean;
  github_configured: boolean;
  openai_configured: boolean;
  anthropic_configured: boolean;
  groq_configured: boolean;
  ollama_base_url: string;
}
export interface TestResult {
  ok: boolean;
  detail: string;
}

export function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "Something went wrong. Please try again.";
}
export async function request<T>(
  path: string,
  token: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { "X-Config-Token": token } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  if (!response.ok) {
    if (response.status === 401)
      throw new Error(
        "Access denied. Check your API token in the access panel.",
      );
    const data = await response.json().catch(() => ({}));
    const detail = data.detail;
    throw new Error(
      Array.isArray(detail)
        ? detail.map((item: { msg: string }) => item.msg).join("; ")
        : detail || `Request failed (${response.status}).`,
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
const TERMINAL_JOB_STATUSES: JobStatus[] = ["succeeded", "failed"];
// Bounds how long the browser polls a single job before giving up, so a
// stuck job (or a worker that's down) surfaces as an error instead of an
// infinite spinner.
const JOB_POLL_TIMEOUT_MS = 120_000;
export async function pollJob(
  // Takes `request` as a parameter, rather than calling the module-level
  // function directly, so a caller under test can pass its own (mocked)
  // `request` binding — a same-module call would bypass a `vi.mock` of
  // this file's `request` export entirely.
  fetcher: typeof request,
  id: string,
  token: string,
  onUpdate?: (job: Job) => void,
  intervalMs = 1500,
): Promise<Job> {
  const deadline = Date.now() + JOB_POLL_TIMEOUT_MS;
  for (;;) {
    const job = await fetcher<Job>(`/report/jobs/${id}`, token);
    onUpdate?.(job);
    if (TERMINAL_JOB_STATUSES.includes(job.status)) return job;
    if (Date.now() >= deadline)
      throw new Error(
        "This report is taking longer than expected. Check back in Report history shortly.",
      );
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}
export async function downloadReport(
  id: string,
  format: Format,
  templateId: string,
  token: string,
) {
  const params = new URLSearchParams({ format });
  if (format === "pdf" && templateId) params.set("template_id", templateId);
  const response = await fetch(`/api/report/${id}/render?${params}`, {
    headers: token ? { "X-Config-Token": token } : {},
  });
  if (!response.ok)
    throw new Error(
      `Download failed (${response.status}). Check access and try again.`,
    );
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = `report-${id}.${format === "markdown" ? "md" : format === "text" ? "txt" : "pdf"}`;
  link.click();
  URL.revokeObjectURL(url);
}
