import "./globals.css";
export const metadata = {
  title: "ReportAPI — Workspace",
  description:
    "Connect sources, generate reports, and manage schedules and templates.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
