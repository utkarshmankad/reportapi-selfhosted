import { beforeEach, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { JobHistory } from "../components/job-history";
import { request, type Job, type Report } from "../lib/api";
vi.mock("../lib/api", async (original) => ({
  ...(await original<typeof import("../lib/api")>()),
  request: vi.fn(),
}));
const api = vi.mocked(request);
const job: Job = {
  id: "j1",
  status: "queued",
  connector: "jira",
  board_id: "DEMO",
  sprint_id: null,
  output_format: "markdown",
  template_id: null,
  report_id: null,
  error_reason: null,
  attempts: 0,
  schedule_id: null,
  scheduled_for: null,
  queued_at: "2026-10-13T00:00:00Z",
  started_at: null,
  finished_at: null,
  created_at: "2026-10-13T00:00:00Z",
};
beforeEach(() => vi.resetAllMocks());
it("loads persisted states on remount and opens only completed reports", async () => {
  const user = userEvent.setup(),
    onOpen = vi.fn();
  const report = { id: "r1" } as Report;
  api.mockImplementation(async (path) =>
    path === "/report/r1"
      ? report
      : [
          job,
          { ...job, id: "j2", status: "running", attempts: 2 },
          {
            ...job,
            id: "j3",
            status: "failed",
            error_reason: "Provider unavailable",
          },
          { ...job, id: "j4", status: "failed" },
          { ...job, id: "j5", status: "succeeded", report_id: "r1" },
          { ...job, id: "j6", status: "succeeded" },
        ],
  );
  const first = render(
    <JobHistory token="secret" version={0} onOpen={onOpen} />,
  );
  await screen.findByText("queued");
  first.unmount();
  render(<JobHistory token="secret" version={0} onOpen={onOpen} />);
  await screen.findByText("running");
  expect(screen.getByText("Provider unavailable")).toBeVisible();
  expect(screen.getByText("Report generation failed.")).toBeVisible();
  expect(screen.getAllByRole("button", { name: "Open report" })).toHaveLength(
    1,
  );
  await user.click(screen.getByRole("button", { name: "Open report" }));
  await waitFor(() => expect(onOpen).toHaveBeenCalledWith(report));
  expect(api).toHaveBeenCalledWith("/report/r1", "secret");
});
it("paginates, refreshes and reloads after generation", async () => {
  const user = userEvent.setup();
  api.mockImplementation(async (path) =>
    path.includes("offset=20")
      ? []
      : Array.from({ length: 20 }, (_, i) => ({ ...job, id: `j${i}` })),
  );
  const view = render(<JobHistory token="" version={0} onOpen={vi.fn()} />);
  await screen.findAllByText("queued");
  await user.click(screen.getByRole("button", { name: "Next jobs" }));
  await screen.findByText("No report jobs on this page.");
  expect(screen.getByText("Jobs page 2")).toBeVisible();
  expect(screen.getByRole("button", { name: "Next jobs" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "Previous jobs" }));
  await screen.findAllByText("queued");
  expect(screen.getByRole("button", { name: "Previous jobs" })).toBeDisabled();
  const before = api.mock.calls.length;
  await user.click(screen.getByRole("button", { name: "Refresh jobs" }));
  await waitFor(() => expect(api.mock.calls.length).toBe(before + 1));
  view.rerender(<JobHistory token="" version={1} onOpen={vi.fn()} />);
  await waitFor(() => expect(api.mock.calls.length).toBe(before + 2));
});
it("shows list errors and recovers on refresh", async () => {
  const user = userEvent.setup();
  api.mockRejectedValueOnce(new Error("Access denied")).mockResolvedValue([]);
  render(<JobHistory token="bad" version={0} onOpen={vi.fn()} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Access denied");
  await user.click(screen.getByRole("button", { name: "Refresh jobs" }));
  await waitFor(() =>
    expect(screen.queryByRole("alert")).not.toBeInTheDocument(),
  );
  expect(await screen.findByText("No report jobs on this page.")).toBeVisible();
});
it("shows result errors without opening a preview", async () => {
  const user = userEvent.setup(),
    onOpen = vi.fn();
  api
    .mockResolvedValueOnce([{ ...job, status: "succeeded", report_id: "r1" }])
    .mockRejectedValueOnce(new Error("Report not found"));
  render(<JobHistory token="" version={0} onOpen={onOpen} />);
  await user.click(await screen.findByRole("button", { name: "Open report" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Report not found",
  );
  expect(onOpen).not.toHaveBeenCalled();
});
it("ignores an old list response when the access token changes", async () => {
  let resolveOld!: (rows: Job[]) => void;
  api
    .mockReturnValueOnce(
      new Promise((resolve) => {
        resolveOld = resolve;
      }),
    )
    .mockResolvedValueOnce([{ ...job, connector: "github" }]);
  const view = render(
    <JobHistory key="old" token="old" version={0} onOpen={vi.fn()} />,
  );
  view.rerender(
    <JobHistory key="new" token="new" version={0} onOpen={vi.fn()} />,
  );
  await screen.findByText("github");
  resolveOld([job]);
  await waitFor(() =>
    expect(screen.queryByText("jira")).not.toBeInTheDocument(),
  );
  expect(api).toHaveBeenCalledWith("/report/jobs?limit=20&offset=0", "new");
});
it.each(["resolve", "reject"])(
  "ignores a stale result %s after unmount",
  async (outcome) => {
    const user = userEvent.setup(),
      onOpen = vi.fn();
    let resolve!: (value: Report) => void, reject!: (error: Error) => void;
    api
      .mockResolvedValueOnce([{ ...job, status: "succeeded", report_id: "r1" }])
      .mockReturnValueOnce(
        new Promise((yes, no) => {
          resolve = yes;
          reject = no;
        }),
      );
    const view = render(<JobHistory token="old" version={0} onOpen={onOpen} />);
    await user.click(
      await screen.findByRole("button", { name: "Open report" }),
    );
    view.unmount();
    if (outcome === "resolve") resolve({ id: "r1" } as Report);
    else reject(new Error("old error"));
    await Promise.resolve();
    expect(onOpen).not.toHaveBeenCalled();
  },
);
