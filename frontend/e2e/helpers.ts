import AxeBuilder from "@axe-core/playwright";
import { expect, type APIRequestContext, type Page, type TestInfo } from "@playwright/test";

export const DEMO_PASSWORD = process.env.DEMO_PASSWORD ?? "local-demo-only-password";
export const DEMO = {
  user: "demo.user@example.com",
  pharmacist: "demo.pharmacist@example.com",
  admin: "demo.admin@example.com",
};

export async function signIn(page: Page, email: string) {
  await page.goto("/en/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(DEMO_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/en\/account/);
}

export function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
}

export async function registerUser(page: Page, email = uniqueEmail("e2e")) {
  await page.goto("/en/register");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/en\/account/);
  return email;
}

export async function addManual(page: Page, name: string, strength: string, form = "Tab") {
  await page.goto("/en/prescriptions/new");
  await page.getByLabel("Medicine name").fill(name);
  await page.getByLabel("Strength").fill(strength);
  await page.getByLabel("Form").fill(form);
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/en\/prescriptions\/[0-9a-f-]{36}/);
  return page.url().split("/").pop() as string;
}

/** WCAG 2.2 AA rule tags. Serious and critical violations fail the test. */
export async function expectAccessible(page: Page, testInfo: TestInfo, label: string) {
  // The title is briefly absent during client navigation. A page with no title still fails here.
  await page.waitForFunction(() => document.title.length > 0, undefined, { timeout: 10_000 });
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const blocking = results.violations.filter((violation) =>
    ["serious", "critical"].includes(violation.impact ?? ""),
  );
  await testInfo.attach(`axe-${label}.json`, {
    body: JSON.stringify(
      {
        label,
        url: page.url(),
        violations: results.violations.map((v) => [v.id, v.impact, v.nodes.length]),
      },
      null,
      1,
    ),
    contentType: "application/json",
  });
  expect(
    blocking.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`),
    label,
  ).toEqual([]);
}

export async function screenshot(page: Page, testInfo: TestInfo, name: string) {
  await page.screenshot({
    path: `../portfolio/demo/screenshots/${testInfo.project.name}-${name}.png`,
    fullPage: true,
  });
}

export async function apiLogin(request: APIRequestContext, email: string): Promise<string> {
  const response = await request.post("/api/v1/auth/login", {
    data: { email, password: DEMO_PASSWORD },
  });
  expect(response.ok()).toBeTruthy();
  return (await response.json()).csrf_token as string;
}
