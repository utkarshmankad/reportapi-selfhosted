import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  if (
    !["config", "report", "reports", "schedule", "templates"].includes(path[0])
  ) {
    return Response.json({ detail: "Not found" }, { status: 404 });
  }
  const origin = request.headers.get("origin");
  // Next may construct nextUrl with an internal container hostname. Browsers
  // address the public Host, which reverse proxies must preserve.
  const protocol =
    request.headers.get("x-forwarded-proto") ||
    request.nextUrl.protocol.replace(":", "");
  const expectedOrigin =
    process.env.UI_PUBLIC_ORIGIN ||
    `${protocol}://${request.headers.get("host") || request.nextUrl.host}`;
  if (request.method !== "GET" && origin && origin !== expectedOrigin) {
    return Response.json(
      { detail: "Cross-origin writes are disabled" },
      { status: 403 },
    );
  }
  const base = process.env.API_INTERNAL_URL || "http://127.0.0.1:8000";
  const url = new URL(
    `/api/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`,
    base,
  );
  try {
    const upstream = await fetch(url, {
      method: request.method,
      headers: {
        "Content-Type": "application/json",
        "X-Config-Token": request.headers.get("X-Config-Token") || "",
      },
      body: ["GET", "HEAD"].includes(request.method)
        ? undefined
        : await request.text(),
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(180_000),
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "Content-Type":
          upstream.headers.get("Content-Type") || "application/json",
        "Cache-Control": "no-store",
        ...(upstream.headers.get("Content-Disposition")
          ? {
              "Content-Disposition": upstream.headers.get(
                "Content-Disposition",
              )!,
            }
          : {}),
      },
    });
  } catch {
    return Response.json(
      {
        detail:
          "Reporting service is unavailable. Check API status and try again.",
      },
      { status: 502 },
    );
  }
}
export { proxy as GET, proxy as POST, proxy as PUT, proxy as DELETE };
