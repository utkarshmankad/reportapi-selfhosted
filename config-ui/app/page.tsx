"use client";
import { useState } from "react";
import { Setup } from "../components/setup";
import { Reports } from "../components/reports";
import { Schedules } from "../components/schedules";
import { Templates } from "../components/templates";

const screens = { Connections: Setup, Reports, Schedules, Templates };
export default function Home() {
  const [screen, setScreen] = useState<keyof typeof screens>("Connections");
  const [token, setToken] = useState("");
  const [draft, setDraft] = useState("");
  const [accessMessage, setAccessMessage] = useState("");
  const Screen = screens[screen];
  return (
    <div className="workspace">
      <aside className="sidebar">
        <a className="brand" href="/">
          Report<span>API</span>
          <small>SELF-HOSTED WORKSPACE</small>
        </a>
        <nav aria-label="Workspace">
          {(Object.keys(screens) as (keyof typeof screens)[]).map(
            (name, index) => (
              <button
                key={name}
                aria-current={screen === name ? "page" : undefined}
                onClick={() => setScreen(name)}
              >
                <span>0{index + 1}</span>
                {name}
              </button>
            ),
          )}
        </nav>
        <p className="sidebar-note">
          Your sources. Your models.
          <br />
          Your infrastructure.
        </p>
      </aside>
      <main>
        <div className="topbar">
          <span className="badge">Community edition</span>
          <details className="access">
            <summary>
              API access {token ? "• token applied" : "• local mode"}
            </summary>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                setToken(draft);
                setDraft("");
                setAccessMessage(
                  "Access settings applied for this page session.",
                );
              }}
            >
              <label>
                API token
                <input
                  type="password"
                  autoComplete="off"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                />
              </label>
              <small>
                Required when the server has a configuration token. Kept in
                memory; re-enter after refresh.
              </small>
              <div className="actions">
                <button type="submit">Apply token</button>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => {
                    setToken("");
                    setDraft("");
                    setAccessMessage("Token cleared.");
                  }}
                >
                  Clear token
                </button>
              </div>
              <p role="status">{accessMessage}</p>
            </form>
          </details>
        </div>
        <Screen key={`${screen}:${token}`} token={token} />
        <footer>
          ReportAPI · Generated narratives should be reviewed before sharing.
        </footer>
      </main>
    </div>
  );
}
