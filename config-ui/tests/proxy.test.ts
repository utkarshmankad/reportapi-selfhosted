// @vitest-environment node
import { afterEach, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET, POST, PUT, DELETE } from "../app/api/[...path]/route";
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});
it.each([GET, POST, PUT, DELETE])(
  "proxies runtime URL and auth",
  async (handler) => {
    vi.stubEnv("API_INTERNAL_URL", "http://internal:8000");
    const fetch = vi.fn().mockResolvedValue(
      new Response("ok", {
        headers: {
          "Content-Type": "text/plain",
          "Content-Disposition": "attachment",
        },
      }),
    );
    vi.stubGlobal("fetch", fetch);
    const response = await handler(
      new NextRequest("http://localhost/api/config", {
        headers: { "X-Config-Token": "secret" },
      }),
      { params: Promise.resolve({ path: ["config"] }) },
    );
    expect(response.status).toBe(200);
    expect(await response.text()).toBe("ok");
    expect(fetch.mock.calls[0][0].hostname).toBe("internal");
  },
);
it("forwards writes, blocks unknown/cross-origin paths", async () => {
  const fetch = vi.fn().mockResolvedValue(new Response("{}"));
  vi.stubGlobal("fetch", fetch);
  vi.stubEnv("API_INTERNAL_URL", "");
  const context = { params: Promise.resolve({ path: ["schedule"] }) };
  expect(
    (
      await POST(
        new NextRequest("http://localhost/api/schedule", {
          method: "POST",
          body: "{}",
          headers: { origin: "http://localhost" },
        }),
        context,
      )
    ).status,
  ).toBe(200);
  expect(fetch.mock.calls[0][1].body).toBe("{}");
  expect(
    (
      await GET(new NextRequest("http://localhost/api/unknown"), {
        params: Promise.resolve({ path: ["unknown"] }),
      })
    ).status,
  ).toBe(404);
  expect(
    (
      await POST(
        new NextRequest("http://localhost/api/schedule", {
          method: "POST",
          headers: { origin: "http://evil.test" },
        }),
        context,
      )
    ).status,
  ).toBe(403);
});
it("handles unreachable upstream and 204", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
  const context = { params: Promise.resolve({ path: ["templates"] }) };
  expect(
    (await GET(new NextRequest("http://localhost/api/templates"), context))
      .status,
  ).toBe(502);
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response(null, { status: 204 })),
  );
  expect(
    (
      await DELETE(
        new NextRequest("http://localhost/api/templates", { method: "DELETE" }),
        context,
      )
    ).status,
  ).toBe(204);
});

it("accepts the browser host when Next has an internal URL", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}")));
  const response = await POST(
    new NextRequest("http://internal:8080/api/templates", {
      method: "POST",
      body: "{}",
      headers: {
        host: "reports.example.com",
        origin: "https://reports.example.com",
        "x-forwarded-proto": "https",
      },
    }),
    { params: Promise.resolve({ path: ["templates"] }) },
  );
  expect(response.status).toBe(200);
});
