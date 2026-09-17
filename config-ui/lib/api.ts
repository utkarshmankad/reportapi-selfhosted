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
  created_at: string;
  output_format: string;
}
export interface Schedule extends Scope {
  id: string;
  cron_expression: string;
  output_format: Format;
  active: boolean;
  last_run_at: string | null;
}
export interface Template {
  id: string;
  name: string;
  content: string;
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
