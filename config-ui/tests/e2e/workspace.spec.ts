import { test, expect } from "@playwright/test";

test("authenticated setup, report/PDF, schedules and templates work in the real stack", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("alert").filter({ hasText: "Access denied" }),
  ).toContainText("Access denied");
  await page.getByText(/API access/).click();
  await page.getByLabel("API token", { exact: true }).fill("smoke-test-token");
  await page.getByRole("button", { name: "Apply token" }).click();
  await expect(page.getByText("jira: configured")).toBeVisible();
  await page.getByRole("button", { name: /Templates/ }).click();
  await page.getByLabel("Template name").fill("Browser template");
  await page.getByRole("button", { name: "Save template" }).click();
  await expect(
    page.getByRole("heading", { name: "Browser template" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: /Reports/, exact: false })
    .first()
    .click();
  await page.getByLabel("Project key").fill("DEMO");
  await page
    .getByRole("button", { name: "Generate report", exact: true })
    .click();
  const preview = page.getByRole("region", { name: "Report detail" });
  await expect(preview).toContainText("Reporting workspace shipped.");
  await preview.getByLabel("Output format").selectOption("pdf");
  await preview
    .getByLabel("PDF template")
    .selectOption({ label: "Browser template" });
  const downloading = page.waitForEvent("download");
  await preview.getByRole("button", { name: "Download report" }).click();
  expect((await downloading).suggestedFilename()).toMatch(/\.pdf$/);
  await page.getByRole("button", { name: /Schedules/ }).click();
  await page.getByLabel("Project key").fill("DEMO");
  await page.getByRole("button", { name: "Create schedule" }).click();
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await expect(page.getByText("Paused", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Edit schedule" }).click();
  await page.getByLabel("Cron expression (UTC)").fill("0 10 * * 1");
  await page.getByRole("button", { name: "Save schedule" }).click();
  await expect(page.getByText("0 10 * * 1", { exact: true })).toBeVisible();
  page.on("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete schedule" }).click();
  await expect(page.getByText(/No schedules yet/)).toBeVisible();
  await page.getByRole("button", { name: /Templates/ }).click();
  await page.getByRole("button", { name: "Edit template" }).click();
  await page.getByLabel("Template name").fill("Updated browser template");
  await page.getByRole("button", { name: "Save template" }).click();
  await expect(
    page.getByRole("heading", { name: "Updated browser template" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Delete template" }).click();
  await expect(page.getByText(/No custom templates/)).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
