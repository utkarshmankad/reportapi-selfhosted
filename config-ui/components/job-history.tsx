import { useEffect, useRef, useState } from "react";
import { errorMessage, request, type Job, type Report } from "../lib/api";
import { Notice } from "./shared";

export function JobHistory({
  token,
  version,
  onOpen,
}: {
  token: string;
  version: number;
  onOpen: (report: Report) => void;
}) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [offset, setOffset] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [opening, setOpening] = useState(false);
  const [error, setError] = useState("");
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    request<Job[]>(`/report/jobs?limit=20&offset=${offset}`, token)
      .then((rows) => {
        if (active) setJobs(rows);
      })
      .catch((e) => {
        if (active) {
          setJobs([]);
          setError(errorMessage(e));
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [token, offset, refresh, version]);
  async function open(id: string) {
    setOpening(true);
    setError("");
    try {
      const report = await request<Report>(`/report/${id}`, token);
      if (mounted.current) onOpen(report);
    } catch (e) {
      if (mounted.current) setError(errorMessage(e));
    } finally {
      if (mounted.current) setOpening(false);
    }
  }
  return (
    <section className="card" aria-label="Report jobs">
      <div className="section-heading">
        <h3>Report jobs</h3>
        <button
          className="secondary"
          disabled={loading}
          onClick={() => setRefresh((v) => v + 1)}
        >
          Refresh jobs
        </button>
      </div>
      <p className="muted">
        Jobs continue in the background. Refresh to check their progress, even
        after reopening this page.
      </p>
      <Notice message={error} error />
      {loading ? (
        <p role="status">Loading report jobs…</p>
      ) : jobs.length === 0 ? (
        <p className="empty">No report jobs on this page.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Source</th>
                <th>Created</th>
                <th>Status</th>
                <th>Attempts</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id}>
                  <td>{job.connector}</td>
                  <td>{new Date(job.created_at).toLocaleString()}</td>
                  <td>{job.status}</td>
                  <td>{job.attempts}</td>
                  <td>
                    {job.status === "succeeded" && job.report_id ? (
                      <button
                        className="secondary"
                        disabled={opening}
                        onClick={() => void open(job.report_id!)}
                      >
                        Open report
                      </button>
                    ) : job.status === "failed" ? (
                      job.error_reason || "Report generation failed."
                    ) : (
                      "—"
                    )}
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
          Previous jobs
        </button>
        <span>Jobs page {offset / 20 + 1}</span>
        <button
          className="secondary"
          disabled={jobs.length < 20 || loading}
          onClick={() => setOffset((o) => o + 20)}
        >
          Next jobs
        </button>
      </div>
    </section>
  );
}
