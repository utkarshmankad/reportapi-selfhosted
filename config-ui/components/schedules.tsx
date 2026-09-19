import { useEffect, useState } from "react";
import {
  request,
  errorMessage,
  type Schedule,
  type Scope,
  type Connector,
  type Format,
  type Job,
} from "../lib/api";
import { ScopeFields, FormatField, Notice } from "./shared";

const empty: Scope = { connector: "jira", board_id: "", sprint_id: "" };
export function Schedules({ token }: { token: string }) {
  const [rows, setRows] = useState<Schedule[]>([]);
  const [scope, setScope] = useState(empty);
  const [cron, setCron] = useState("0 9 * * 1");
  const [format, setFormat] = useState<Format>("text");
  const [editing, setEditing] = useState<Schedule | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);
  const [historyFor, setHistoryFor] = useState<string | null>(null);
  const [history, setHistory] = useState<Job[]>([]);
  const [historyError, setHistoryError] = useState("");
  const [historyLoading, setHistoryLoading] = useState(false);
  useEffect(() => {
    let active = true;
    setLoading(true);
    request<Schedule[]>("/schedule", token)
      .then((data) => {
        if (active) {
          setRows(data);
          setError("");
        }
      })
      .catch((e) => {
        if (active) setError(errorMessage(e));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [token, version]);
  function reset() {
    setEditing(null);
    setScope(empty);
    setCron("0 9 * * 1");
    setFormat("text");
  }
  async function toggleHistory(scheduleId: string) {
    if (historyFor === scheduleId) {
      setHistoryFor(null);
      return;
    }
    setHistoryFor(scheduleId);
    setHistory([]);
    setHistoryError("");
    setHistoryLoading(true);
    try {
      setHistory(await request<Job[]>(`/schedule/${scheduleId}/jobs`, token));
    } catch (e) {
      setHistoryError(errorMessage(e));
    } finally {
      setHistoryLoading(false);
    }
  }
  async function mutate(path: string, method: string, body?: unknown) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await request(path, token, method, body);
      setVersion((v) => v + 1);
      setMessage("Schedule updated.");
      return true;
    } catch (e) {
      setError(errorMessage(e));
      return false;
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <header className="section-heading">
        <div>
          <p className="eyebrow">03 / AUTOMATE</p>
          <h2>Schedules</h2>
          <p>Set a cadence for recurring reports. All times are UTC.</p>
        </div>
      </header>
      <section className="card">
        <h3>{editing ? "Edit schedule" : "New schedule"}</h3>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            if (
              await mutate(
                editing ? `/schedule/${editing.id}` : "/schedule",
                editing ? "PUT" : "POST",
                {
                  ...scope,
                  cron_expression: cron,
                  output_format: format,
                  active: editing?.active ?? true,
                },
              )
            )
              reset();
          }}
        >
          <fieldset disabled={busy}>
            <ScopeFields value={scope} onChange={setScope} />
            <div className="form-grid">
              <label>
                Cron expression (UTC)
                <input
                  aria-label="Cron expression (UTC)"
                  value={cron}
                  onChange={(e) => setCron(e.target.value)}
                  required
                  maxLength={100}
                />
                <small>
                  Five fields: minute hour day month weekday. Monday 09:00 UTC:
                  0 9 * * 1.
                </small>
              </label>
              <FormatField value={format} onChange={setFormat} />
            </div>
            <div className="actions">
              <button type="submit">
                {editing ? "Save schedule" : "Create schedule"}
              </button>
              {editing && (
                <button type="button" className="secondary" onClick={reset}>
                  Cancel edit
                </button>
              )}
            </div>
          </fieldset>
        </form>
      </section>
      <Notice message={error} error />
      <Notice message={message} />
      <section className="card">
        <h3>Recurring reports</h3>
        {loading ? (
          <p role="status">Loading schedules…</p>
        ) : rows.length === 0 ? (
          <p className="empty">
            No schedules yet. Create a recurring report above.
          </p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Source / scope</th>
                  <th>Cadence (UTC)</th>
                  <th>Status</th>
                  <th>Last attempt</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td>
                      {row.connector} / {row.board_id || row.sprint_id}
                    </td>
                    <td>
                      <code>{row.cron_expression}</code>
                    </td>
                    <td>{row.active ? "Active" : "Paused"}</td>
                    <td>
                      {row.last_run_at
                        ? new Date(row.last_run_at).toLocaleString()
                        : "Not run yet"}
                    </td>
                    <td>
                      <div className="actions">
                        <button
                          className="secondary"
                          disabled={busy}
                          onClick={() => {
                            setEditing(row);
                            setScope({
                              connector: row.connector as Connector,
                              board_id: row.board_id || "",
                              sprint_id: row.sprint_id || "",
                            });
                            setCron(row.cron_expression);
                            setFormat(row.output_format as Format);
                          }}
                        >
                          Edit schedule
                        </button>
                        <button
                          className="secondary"
                          disabled={busy}
                          onClick={() =>
                            void mutate(`/schedule/${row.id}`, "PUT", {
                              ...row,
                              active: !row.active,
                            })
                          }
                        >
                          {row.active ? "Pause" : "Resume"}
                        </button>
                        <button
                          className="danger"
                          disabled={busy}
                          onClick={async () => {
                            if (
                              window.confirm(
                                "Delete this schedule? Existing reports will remain.",
                              )
                            ) {
                              if (
                                (await mutate(
                                  `/schedule/${row.id}`,
                                  "DELETE",
                                )) &&
                                editing?.id === row.id
                              )
                                reset();
                            }
                          }}
                        >
                          Delete schedule
                        </button>
                        <button
                          className="secondary"
                          onClick={() => void toggleHistory(row.id)}
                        >
                          {historyFor === row.id
                            ? "Hide history"
                            : "View history"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {historyFor && (
          <div
            className="table-wrap"
            role="region"
            aria-label="Schedule run history"
          >
            <h4>Run history</h4>
            <Notice message={historyError} error />
            {historyLoading ? (
              <p role="status">Loading run history…</p>
            ) : history.length === 0 ? (
              <p className="empty">No runs recorded yet for this schedule.</p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Scheduled for</th>
                    <th>Status</th>
                    <th>Attempts</th>
                    <th>Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((job) => (
                    <tr key={job.id}>
                      <td>
                        {job.scheduled_for
                          ? new Date(job.scheduled_for).toLocaleString()
                          : "—"}
                      </td>
                      <td>
                        <span className={`badge ${job.status}`}>
                          {job.status}
                        </span>
                      </td>
                      <td>{job.attempts}</td>
                      <td>
                        {job.error_reason ||
                          (job.report_id ? "Succeeded" : "—")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </section>
    </>
  );
}
