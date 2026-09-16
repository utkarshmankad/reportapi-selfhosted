import { useEffect, useState } from "react";
import { request, errorMessage, type Template } from "../lib/api";
import { Notice } from "./shared";

const defaultContent =
  '<h1>Project update</h1>\n<p>{{ report.created_at }}</p>\n<div style="white-space: pre-wrap">{{ report.narrative }}</div>';
export function Templates({ token }: { token: string }) {
  const [rows, setRows] = useState<Template[]>([]);
  const [name, setName] = useState("");
  const [content, setContent] = useState(defaultContent);
  const [editing, setEditing] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true);
    request<Template[]>("/templates", token)
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
    setName("");
    setContent(defaultContent);
  }
  async function save() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await request(
        editing ? `/templates/${editing}` : "/templates",
        token,
        editing ? "PUT" : "POST",
        { name, content },
      );
      reset();
      setVersion((v) => v + 1);
      setMessage(
        "Template saved. Select it when downloading a PDF from Reports.",
      );
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  async function remove(id: string) {
    if (
      !window.confirm(
        "Delete this template? Stored report narratives will remain.",
      )
    )
      return;
    setBusy(true);
    setError("");
    try {
      await request(`/templates/${id}`, token, "DELETE");
      if (editing === id) reset();
      setVersion((v) => v + 1);
      setMessage("Template deleted.");
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
          <p className="eyebrow">04 / PRESENT</p>
          <h2>Templates</h2>
          <p>Give PDF reports a consistent layout for your audience.</p>
        </div>
      </header>
      <section className="card">
        <h3>{editing ? "Edit template" : "New template"}</h3>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <fieldset disabled={busy}>
            <label>
              Template name
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                maxLength={100}
              />
            </label>
            <label>
              HTML template
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                required
                maxLength={50000}
                rows={10}
                spellCheck={false}
              />
            </label>
            <p className="muted">
              Use <code>{"{{ report.narrative }}"}</code>,{" "}
              <code>{"{{ report.connector }}"}</code> and{" "}
              <code>{"{{ report.created_at }}"}</code>. External images and
              stylesheets are disabled. Download a PDF in Reports to preview the
              rendered result.
            </p>
            <div className="actions">
              <button type="submit">Save template</button>
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
        <h3>Saved templates</h3>
        {loading ? (
          <p role="status">Loading templates…</p>
        ) : rows.length === 0 ? (
          <p className="empty">
            No custom templates yet. The default PDF layout is always available.
          </p>
        ) : (
          rows.map((row) => (
            <article className="list-item" key={row.id}>
              <h4>{row.name}</h4>
              <div className="actions">
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => {
                    setEditing(row.id);
                    setName(row.name);
                    setContent(row.content);
                  }}
                >
                  Edit template
                </button>
                <button
                  className="danger"
                  disabled={busy}
                  onClick={() => void remove(row.id)}
                >
                  Delete template
                </button>
              </div>
            </article>
          ))
        )}
      </section>
    </>
  );
}
