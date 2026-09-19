import { beforeEach, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Home from "../app/page";
import { Setup } from "../components/setup";
import { Reports } from "../components/reports";
import { Schedules } from "../components/schedules";
import { Templates } from "../components/templates";
import {
  request,
  downloadReport,
  type Report,
  type Schedule,
  type Template,
  type Job,
} from "../lib/api";
vi.mock("../lib/api", async (original) => ({
  ...(await original<typeof import("../lib/api")>()),
  request: vi.fn(),
  downloadReport: vi.fn(),
}));
const api = vi.mocked(request),
  download = vi.mocked(downloadReport);
const report: Report = {
  id: "r1",
  connector: "jira",
  board_id: "DEMO",
  sprint_id: null,
  status: "complete",
  narrative: "Two issues shipped.",
  model_used: "test",
  tokens_used: 12,
  ticket_count: 4,
  prompt_version: 1,
  created_at: "2026-09-16T00:00:00Z",
  output_format: "text",
  is_truncated: false,
  truncation_reason: null,
  period_start: null,
  period_end: null,
  period_semantics: null,
  template_id: null,
  template_version: null,
};
const schedule: Schedule = {
  id: "s1",
  connector: "jira",
  board_id: "DEMO",
  sprint_id: "",
  cron_expression: "0 9 * * 1",
  output_format: "text",
  active: true,
  assigned_means_in_progress: true,
  last_run_at: null,
  last_attempted_at: null,
  period_start: null,
  period_end: null,
  created_at: "2026-09-16T00:00:00Z",
};
const template: Template = {
  id: "t1",
  name: "Client update",
  content: "<h1>Update</h1>",
  version: 1,
  archived: false,
  created_at: "2026-09-16T00:00:00Z",
};
let reports: Report[],
  schedules: Schedule[],
  templates: Template[],
  jobs: Job[],
  fail: string,
  failMethod: string;
beforeEach(() => {
  vi.resetAllMocks();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  download.mockResolvedValue(undefined);
  reports = [report];
  schedules = [schedule];
  templates = [template];
  jobs = [];
  fail = "";
  failMethod = "GET";
  api.mockImplementation(async (path, _token, method = "GET", body) => {
    if (path === fail && method === failMethod)
      throw new Error("Service unavailable");
    if (path === "/config")
      return {
        llm_provider: "openai",
        jira_configured: true,
        asana_configured: false,
        github_configured: false,
      };
    if (path.startsWith("/config/"))
      return { ok: true, detail: "Connection successful." };
    if (path.startsWith("/reports"))
      return path.includes("offset=20") ? [] : reports;
    if (path === "/report/jobs") return { id: "j1", status: "queued" };
    if (path === "/report/jobs/j1")
      return { id: "j1", status: "succeeded", report_id: "r1", attempts: 1 };
    if (path === "/report/r1") {
      if (method === "DELETE") reports = [];
      return report;
    }
    if (path === "/schedule") {
      if (method === "POST") schedules = [{ ...schedule, ...(body as object) }];
      return schedules;
    }
    if (path === "/schedule/s1/jobs") return jobs;
    if (path.startsWith("/schedule/")) {
      schedules =
        method === "DELETE" ? [] : [{ ...schedule, ...(body as object) }];
      return schedules[0];
    }
    if (path.startsWith("/templates") && !path.includes("/templates/")) {
      if (method === "POST") templates = [{ ...template, ...(body as object) }];
      return templates;
    }
    if (path.endsWith("/preview")) return { html: "<h1>Preview</h1>" };
    if (path.endsWith("/archive")) {
      templates = [{ ...templates[0], archived: true }];
      return templates[0];
    }
    if (path.endsWith("/restore")) {
      templates = [{ ...templates[0], archived: false }];
      return templates[0];
    }
    if (path.startsWith("/templates/")) {
      templates =
        method === "DELETE" ? [] : [{ ...template, ...(body as object) }];
      return templates[0];
    }
    throw new Error(`Unexpected path ${path}`);
  });
});
it("navigates every screen and applies/clears token", async () => {
  const user = userEvent.setup();
  render(<Home />);
  await screen.findByText("jira: configured");
  await user.click(screen.getByText(/API access/));
  await user.type(screen.getByLabelText("API token"), "secret");
  await user.click(screen.getByRole("button", { name: "Apply token" }));
  await waitFor(() => expect(api).toHaveBeenCalledWith("/config", "secret"));
  for (const name of ["Reports", "Schedules", "Templates", "Connections"]) {
    await user.click(screen.getByRole("button", { name: new RegExp(name) }));
    expect(
      await screen.findByRole("heading", { level: 2, name }),
    ).toBeVisible();
  }
  await user.click(screen.getByRole("button", { name: "Clear token" }));
  expect(await screen.findByText("Token cleared.")).toBeVisible();
});
it.each(["Jira", "Asana", "GitHub", "LLM provider"])(
  "tests and saves %s and handles failures",
  async (title) => {
    const user = userEvent.setup();
    render(<Setup token="t" />);
    await screen.findByText("jira: configured");
    const form = within(
      screen.getByRole("region", { name: `${title} connection` }),
    );
    if (title === "Jira") {
      await user.type(
        form.getByLabelText("Jira URL"),
        "https://team.atlassian.net",
      );
      await user.type(form.getByLabelText("Email"), "test@example.com");
    }
    const label = title === "LLM provider" ? "API key" : "Access token";
    await user.type(form.getByLabelText(label), "synthetic");
    await user.click(form.getByRole("button", { name: "Test connection" }));
    expect(await form.findByText("Connection successful.")).toBeVisible();
    await user.click(form.getByRole("button", { name: "Save connection" }));
    await waitFor(() => expect(form.getByLabelText(label)).toHaveValue(""));
    api.mockRejectedValueOnce(new Error("Failed connection"));
    await user.click(form.getByRole("button", { name: "Test connection" }));
    expect(await form.findByRole("alert")).toHaveTextContent(
      "Failed connection",
    );
  },
);
it("handles status failure, Ollama default/custom URL and rejected tests", async () => {
  const user = userEvent.setup();
  fail = "/config";
  render(<Setup token="" />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Service unavailable",
  );
  const form = within(
    screen.getByRole("region", { name: "LLM provider connection" }),
  );
  await user.selectOptions(form.getByLabelText("Provider"), "ollama");
  await user.click(form.getByRole("button", { name: "Test connection" }));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      "/config/llm/test",
      "",
      "POST",
      expect.objectContaining({ ollama_base_url: "http://ollama:11434" }),
    ),
  );
  await user.type(form.getByLabelText("Ollama URL"), "http://private:11434");
  api.mockResolvedValueOnce({ ok: false, detail: "URL refused" });
  await user.click(form.getByRole("button", { name: "Test connection" }));
  expect(await form.findByRole("alert")).toHaveTextContent("URL refused");
});
it("generates, downloads PDF with selected template, and deletes", async () => {
  const user = userEvent.setup();
  render(<Reports token="t" />);
  await screen.findByRole("button", { name: "View report" });
  await user.type(screen.getByLabelText("Project key"), "DEMO");
  await user.click(screen.getByRole("button", { name: "Generate report" }));
  expect(await screen.findByText("Two issues shipped.")).toBeVisible();
  const detail = within(screen.getByRole("region", { name: "Report detail" }));
  await user.selectOptions(detail.getByLabelText("Output format"), "pdf");
  await user.selectOptions(detail.getByLabelText("PDF template"), "t1");
  await user.click(detail.getByRole("button", { name: "Download report" }));
  expect(download).toHaveBeenCalledWith("r1", "pdf", "t1", "t");
  download.mockRejectedValueOnce(new Error("Download unavailable"));
  await user.click(detail.getByRole("button", { name: "Download report" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Download unavailable",
  );
  await user.click(screen.getByRole("button", { name: "Delete report" }));
  expect(await screen.findByText(/No reports on this page/)).toBeVisible();
});
it("handles report failures and cancellation", async () => {
  const user = userEvent.setup();
  fail = "/reports?limit=20&offset=0";
  render(<Reports token="" />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Service unavailable",
  );
  fail = "";
  await user.click(screen.getByRole("button", { name: "Refresh" }));
  await screen.findByRole("button", { name: "View report" });
  await user.click(screen.getByRole("button", { name: "View report" }));
  await user.click(screen.getByRole("button", { name: "Close preview" }));
  vi.mocked(window.confirm).mockReturnValueOnce(false);
  await user.click(screen.getByRole("button", { name: "Delete report" }));
  expect(api).not.toHaveBeenCalledWith("/report/r1", "", "DELETE");
  fail = "/report/r1";
  failMethod = "DELETE";
  await user.click(screen.getByRole("button", { name: "Delete report" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Service unavailable",
  );
  fail = "/report/jobs";
  failMethod = "POST";
  await user.type(screen.getByLabelText("Project key"), "D");
  await user.click(screen.getByRole("button", { name: "Generate report" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Service unavailable",
  );
});
it("surfaces a failed job's error_reason", async () => {
  const user = userEvent.setup();
  api.mockImplementation(async (path, _token, method = "GET") => {
    if (path.startsWith("/reports"))
      return path.includes("offset=20") ? [] : reports;
    if (path === "/templates") return templates;
    if (path === "/report/jobs" && method === "POST")
      return { id: "j1", status: "queued", attempts: 0 };
    if (path === "/report/jobs/j1")
      return {
        id: "j1",
        status: "failed",
        attempts: 3,
        error_reason: "Jira fetch failed; check connection settings",
      };
    throw new Error(`Unexpected path ${path}`);
  });
  render(<Reports token="t" />);
  await screen.findByRole("button", { name: "View report" });
  await user.type(screen.getByLabelText("Project key"), "DEMO");
  await user.click(screen.getByRole("button", { name: "Generate report" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Jira fetch failed; check connection settings",
  );
});
it("paginates reports and accepts GitHub/Asana scopes", async () => {
  const user = userEvent.setup();
  reports = Array.from({ length: 20 }, (_, i) => ({
    ...report,
    id: `r${i}`,
    narrative: null,
  }));
  render(<Reports token="" />);
  await screen.findAllByRole("button", { name: "View report" });
  await user.click(screen.getAllByRole("button", { name: "View report" })[0]);
  expect(screen.getByText("No narrative available.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Next" }));
  await screen.findByText(/No reports on this page/);
  await user.click(screen.getByRole("button", { name: "Previous" }));
  await screen.findAllByRole("button", { name: "View report" });
  await user.selectOptions(screen.getByLabelText("Source"), "github");
  await user.type(
    screen.getByLabelText("Repository (owner/repo)"),
    "owner/repo",
  );
  await user.type(screen.getByLabelText("Milestone (optional)"), "2");
  await user.selectOptions(screen.getByLabelText("Source"), "asana");
  await user.type(screen.getByLabelText("Section ID (optional)"), "123");
  expect(screen.getByLabelText("Project ID")).not.toBeRequired();
});
it("creates, edits, pauses/resumes and deletes schedules", async () => {
  const user = userEvent.setup();
  schedules = [];
  render(<Schedules token="t" />);
  await screen.findByText(/No schedules yet/);
  await user.type(screen.getByLabelText("Project key"), "DEMO");
  await user.selectOptions(screen.getByLabelText("Output format"), "pdf");
  await user.clear(screen.getByLabelText("Cron expression (UTC)"));
  await user.type(screen.getByLabelText("Cron expression (UTC)"), "0 12 * * *");
  await user.click(screen.getByRole("button", { name: "Create schedule" }));
  await screen.findByText("Active");
  await user.click(screen.getByRole("button", { name: "Edit schedule" }));
  await user.click(screen.getByRole("button", { name: "Cancel edit" }));
  await user.click(screen.getByRole("button", { name: "Edit schedule" }));
  await user.click(screen.getByRole("button", { name: "Save schedule" }));
  await user.click(await screen.findByRole("button", { name: "Pause" }));
  expect(await screen.findByText("Paused")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Resume" }));
  await screen.findByText("Active");
  await user.click(screen.getByRole("button", { name: "Edit schedule" }));
  await user.click(screen.getByRole("button", { name: "Delete schedule" }));
  expect(await screen.findByText(/No schedules yet/)).toBeVisible();
});
it("handles schedule errors and section scopes", async () => {
  const user = userEvent.setup();
  fail = "/schedule";
  const view = render(<Schedules token="" />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Service unavailable",
  );
  view.unmount();
  fail = "";
  schedules = [
    {
      ...schedule,
      board_id: "",
      sprint_id: "10",
      last_run_at: "2026-09-16T00:00:00Z",
    },
  ];
  render(<Schedules token="" />);
  await screen.findByRole("button", { name: "Edit schedule" });
  await user.click(screen.getByRole("button", { name: "Edit schedule" }));
  vi.mocked(window.confirm).mockReturnValueOnce(false);
  await user.click(screen.getByRole("button", { name: "Delete schedule" }));
  fail = "/schedule/s1";
  failMethod = "PUT";
  await user.click(screen.getByRole("button", { name: "Save schedule" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Service unavailable",
  );
});
it("views and hides a schedule's run history, and handles history errors", async () => {
  const user = userEvent.setup();
  jobs = [
    {
      id: "j1",
      status: "succeeded",
      connector: "jira",
      board_id: "DEMO",
      sprint_id: null,
      output_format: "text",
      template_id: null,
      report_id: "r1",
      error_reason: null,
      attempts: 1,
      schedule_id: "s1",
      scheduled_for: "2026-09-16T09:00:00Z",
      queued_at: "2026-09-16T09:00:00Z",
      started_at: "2026-09-16T09:00:01Z",
      finished_at: "2026-09-16T09:00:05Z",
      created_at: "2026-09-16T09:00:00Z",
    },
  ];
  render(<Schedules token="t" />);
  await screen.findByRole("button", { name: "View history" });
  await user.click(screen.getByRole("button", { name: "View history" }));
  const historyPanel = within(
    screen.getByRole("region", { name: "Schedule run history" }),
  );
  expect(await historyPanel.findByText("succeeded")).toBeVisible();
  expect(historyPanel.getByText("Succeeded")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Hide history" }));
  expect(screen.queryByText("Run history")).not.toBeInTheDocument();

  fail = "/schedule/s1/jobs";
  await user.click(screen.getByRole("button", { name: "View history" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Service unavailable",
  );
});
it("creates, edits and deletes templates", async () => {
  const user = userEvent.setup();
  templates = [];
  render(<Templates token="t" />);
  await screen.findByText(/No custom templates/);
  await user.type(screen.getByLabelText("Template name"), "New layout");
  await user.clear(screen.getByLabelText("HTML template"));
  await user.type(screen.getByLabelText("HTML template"), "<h1>Update</h1>");
  await user.click(screen.getByRole("button", { name: "Save template" }));
  await screen.findByRole("heading", { name: "New layout" });
  await user.click(screen.getByRole("button", { name: "Edit template" }));
  await user.click(screen.getByRole("button", { name: "Cancel edit" }));
  await user.click(screen.getByRole("button", { name: "Edit template" }));
  await user.click(screen.getByRole("button", { name: "Save template" }));
  await user.click(
    await screen.findByRole("button", { name: "Edit template" }),
  );
  await user.click(screen.getByRole("button", { name: "Delete template" }));
  expect(await screen.findByText(/No custom templates/)).toBeVisible();
});
it("previews, archives and restores a template", async () => {
  const user = userEvent.setup();
  render(<Templates token="t" />);
  await screen.findByRole("heading", { name: "Client update" });
  await user.click(screen.getByRole("button", { name: "Preview" }));
  const previewPanel = within(
    screen.getByRole("region", { name: "Template preview" }),
  );
  expect(previewPanel.getByTitle(/Preview of/)).toBeInTheDocument();
  await user.click(previewPanel.getByRole("button", { name: "Close preview" }));
  expect(
    screen.queryByRole("region", { name: "Template preview" }),
  ).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Archive" }));
  expect(await screen.findByText(/Archived/)).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Restore" }));
  await waitFor(() =>
    expect(screen.queryByText(/Archived/)).not.toBeInTheDocument(),
  );
  await user.click(screen.getByLabelText("Show archived"));
});
it("handles template errors and cancelled deletion", async () => {
  const user = userEvent.setup();
  fail = "/templates";
  const view = render(<Templates token="" />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Service unavailable",
  );
  view.unmount();
  fail = "";
  render(<Templates token="" />);
  await screen.findByRole("button", { name: "Edit template" });
  vi.mocked(window.confirm).mockReturnValueOnce(false);
  await user.click(screen.getByRole("button", { name: "Delete template" }));
  fail = "/templates/t1";
  failMethod = "DELETE";
  await user.click(screen.getByRole("button", { name: "Delete template" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Service unavailable",
  );
  failMethod = "PUT";
  await user.click(screen.getByRole("button", { name: "Edit template" }));
  await user.click(screen.getByRole("button", { name: "Save template" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Service unavailable",
  );
});

it("identifies externally managed connections and removes save forms", async () => {
  api.mockResolvedValueOnce({ config_read_only: true, llm_provider: "ollama" });
  render(<Setup token="t" />);
  expect(
    await screen.findByText(/Connections are managed by your operator/),
  ).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Save connection" }),
  ).not.toBeInTheDocument();
});
