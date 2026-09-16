import type { Connector, Scope, Format } from "../lib/api";

export function Notice({
  message,
  error = false,
}: {
  message: string;
  error?: boolean;
}) {
  return message ? (
    <p
      className={error ? "notice error" : "notice"}
      role={error ? "alert" : "status"}
    >
      {message}
    </p>
  ) : null;
}
export function ScopeFields({
  value,
  onChange,
}: {
  value: Scope;
  onChange: (scope: Scope) => void;
}) {
  return (
    <div className="form-grid">
      <label>
        Source
        <select
          value={value.connector}
          onChange={(e) =>
            onChange({
              ...value,
              connector: e.target.value as Connector,
              board_id: "",
              sprint_id: "",
            })
          }
        >
          <option value="jira">Jira</option>
          <option value="asana">Asana</option>
          <option value="github">GitHub Issues</option>
        </select>
      </label>
      <label>
        {value.connector === "github"
          ? "Repository (owner/repo)"
          : value.connector === "asana"
            ? "Project ID"
            : "Project key"}
        <input
          value={value.board_id}
          onChange={(e) => onChange({ ...value, board_id: e.target.value })}
          required={!value.sprint_id || value.connector === "github"}
          maxLength={100}
        />
      </label>
      <label>
        {value.connector === "github"
          ? "Milestone (optional)"
          : value.connector === "asana"
            ? "Section ID (optional)"
            : "Sprint ID (optional)"}
        <input
          value={value.sprint_id}
          onChange={(e) => onChange({ ...value, sprint_id: e.target.value })}
          maxLength={100}
        />
      </label>
    </div>
  );
}
export function FormatField({
  value,
  onChange,
}: {
  value: Format;
  onChange: (format: Format) => void;
}) {
  return (
    <label>
      Output format
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as Format)}
      >
        <option value="text">Text</option>
        <option value="markdown">Markdown</option>
        <option value="pdf">PDF</option>
      </select>
    </label>
  );
}
