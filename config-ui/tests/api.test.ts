import { afterEach, expect, it, vi } from "vitest";
import { request, errorMessage, downloadReport } from "../lib/api";
afterEach(() => vi.unstubAllGlobals());
it("parses success/204 and attaches auth", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true })))
    .mockResolvedValueOnce(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetch);
  expect(await request("/config", "secret", "POST", {})).toEqual({ ok: true });
  expect(fetch.mock.calls[0][1].headers["X-Config-Token"]).toBe("secret");
  expect(await request("/templates/1", "", "DELETE")).toBeUndefined();
});
it.each([
  [401, {}, "Access denied"],
  [422, { detail: [{ msg: "Invalid scope" }] }, "Invalid scope"],
  [500, { detail: "Failed" }, "Failed"],
  [503, {}, "503"],
])("normalizes status %s", async (status, body, message) => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify(body), { status: status as number }),
      ),
  );
  await expect(request("/config", "")).rejects.toThrow(message as string);
});
it("handles non-JSON errors and unknown thrown values", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response("unavailable", { status: 502 })),
  );
  await expect(request("/config", "")).rejects.toThrow("502");
  expect(errorMessage("unknown")).toContain("Something went wrong");
  expect(errorMessage(new Error("known"))).toBe("known");
});
it.each(["text", "markdown", "pdf"] as const)(
  "downloads %s",
  async (format) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("report")));
    URL.createObjectURL = vi.fn().mockReturnValue("blob:report");
    URL.revokeObjectURL = vi.fn();
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    await downloadReport("id", format, format === "pdf" ? "t1" : "", "token");
    expect(click).toHaveBeenCalled();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:report");
    click.mockRestore();
  },
);
it("handles unauthenticated download failure", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response("no", { status: 401 })),
  );
  await expect(downloadReport("id", "pdf", "", "")).rejects.toThrow("401");
});
