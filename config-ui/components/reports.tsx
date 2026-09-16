import { useEffect, useState } from "react";
import {
  request,
  errorMessage,
  downloadReport,
  type Report,
  type Scope,
  type Format,
  type Template,
} from "../lib/api";
import { ScopeFields, FormatField, Notice } from "./shared";

export function Reports({ token }: { token: string }) {
  const [scope, setScope] = useState<Scope>({
    connector: "jira",
    board_id: "",
    sprint_id: "",
  });
  const [format, setFormat] = useState<Format>("markdown");
  const [template, setTemplate] = useState("");
  const [templates, setTemplates] = useState<Template[]>([]);
  const [reports, setReports] = useState<Report[]>([]);
  const [selected, setSelected] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([
      request<Report[]>(`/reports?limit=20&offset=${offset}`, token),
      request<Template[]>("/templates", token),
    ])
      .then(([rows, presets]) => {
        if (active) {
          setReports(rows);
          setTemplates(presets);
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
  }, [token, offset, version]);
  async function generate() {
    setBusy(true);
    setError("");
    try {
      const result = await request<{ report_id: string }>(
        "/report/generate",
        token,
        "POST",
        { ...scope, output_format: format },
      );
      setSelected(await request<Report>(`/report/${result.report_id}`, token));
      setOffset(0);
      setVersion((v) => v + 1);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  async function remove(id: string) {
    if (!window.confirm("Delete this report permanently?")) return;
    setBusy(true);
    setError("");
    try {
      await request(`/report/${id}`, token, "DELETE");
      if (selected?.id === id) setSelected(null);
      setVersion((v) => v + 1);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <header className="section-heading">
        <div>
          <p className="eyebrow">02 / UNDERSTAND</p>
          <h2>Reports</h2>
          <p>Turn project activity into a clear, shareable update.</p>
        </div>
      </header>
      <section className="card">
        <h3>Generate a report</h3>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void generate();
          }}
        >
          <fieldset disabled={busy}>
            <ScopeFields value={scope} onChange={setScope} />
            <FormatField value={format} onChange={setFormat} />
            <button type="submit">
              {busy ? "Working…" : "Generate report"}
            </button>
          </fieldset>
        </form>
        {busy && (
          <p role="status">
            Please keep this page open while the request completes.
          </p>
        )}
      </section>
      <Notice message={error} error />
      {selected && (
        <section className="card report-detail" aria-label="Report detail">
          <div className="section-heading">
            <h3>Report preview</h3>
            <button className="secondary" onClick={() => setSelected(null)}>
              Close preview
            </button>
          </div>
          <p className="muted">
            {selected.connector} · {selected.model_used} ·{" "}
            {selected.tokens_used} tokens
          </p>
          <pre>{selected.narrative || "No narrative available."}</pre>
          <div className="actions">
            <FormatField value={format} onChange={setFormat} />
            {format === "pdf" && (
              <label>
                PDF template
                <select
                  value={template}
                  onChange={(e) => setTemplate(e.target.value)}
                >
                  <option value="">Default template</option>
                  {templates.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <button
              onClick={() =>
                void downloadReport(selected.id, format, template, token).catch(
                  (e) => setError(errorMessage(e)),
                )
              }
            >
              Download report
            </button>
          </div>
        </section>
      )}
      <section className="card">
        <div className="section-heading">
          <h3>Report history</h3>
          <button
            className="secondary"
            onClick={() => setVersion((v) => v + 1)}
          >
            Refresh
          </button>
        </div>
        {loading ? (
          <p role="status">Loading reports…</p>
        ) : reports.length === 0 ? (
          <p className="empty">
            No reports on this page. Generate your first report above.
          </p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Created</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {reports.map((row) => (
                  <tr key={row.id}>
                    <td>{row.connector}</td>
                    <td>{new Date(row.created_at).toLocaleString()}</td>
                    <td>
                      <span className="badge ready">{row.status}</span>
                    </td>
                    <td>
                      <div className="actions">
                        <button
                          className="secondary"
                          onClick={() => setSelected(row)}
                        >
                          View report
                        </button>
                        <button
                          className="danger"
                          disabled={busy}
                          onClick={() => void remove(row.id)}
                        >
                          Delete report
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="actions pagination">
          <button
            className="secondary"
            disabled={offset === 0 || loading}
            onClick={() => setOffset((o) => Math.max(0, o - 20))}
          >
            Previous
          </button>
          <span>Page {offset / 20 + 1}</span>
          <button
            className="secondary"
            disabled={reports.length < 20 || loading}
            onClick={() => setOffset((o) => o + 20)}
          >
            Next
          </button>
        </div>
      </section>
    </>
  );
}
