export const metadata = {
  title: "ReportAPI — Setup",
  description: "Configure Jira, your LLM provider, and report schedules.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{
        margin: 0,
        fontFamily: "ui-sans-serif, system-ui, sans-serif",
        background: "#12151b",
        color: "#e7eaef",
      }}>
        {children}
      </body>
    </html>
  );
}
