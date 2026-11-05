import { expect, test } from "@playwright/test";
import path from "node:path";
import {
  addManual,
  apiLogin,
  DEMO,
  expectAccessible,
  registerUser,
  screenshot,
  signIn,
} from "./helpers";

const SAMPLE = path.resolve(__dirname, "fixtures/synthetic_rx.png");

test.describe("public catalogue", () => {
  test("search tolerates typos and explains results", async ({ page }, info) => {
    await page.goto("/en");
    await expect(page.getByTestId("medical-notice")).toContainText("not medical advice");
    await expectAccessible(page, info, "home");
    await screenshot(page, info, "home");
    await page.getByRole("textbox", { name: /Search by brand/ }).fill("metformn");
    await page.getByRole("button", { name: "Search", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Possible matches" })).toBeVisible();
    await expect(page.getByText(/does not mean the same medicine/).first()).toBeVisible();
    await expectAccessible(page, info, "search");
    await screenshot(page, info, "search-typo");
  });

  test("detail shows sourced prices, stale labels and unlike products", async ({ page }, info) => {
    await page.goto("/en/search?q=Metformin");
    await page.getByRole("link", { name: "Metformin 500mg Tablet" }).first().click();
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Metformin 500mg Tablet");
    await expect(page.getByText(/not a shop price/)).toBeVisible();
    await expect(page.getByText("May be out of date").first()).toBeVisible();
    await expect(page.getByText(/Source: NPPA/)).toBeVisible();
    await expect(page.getByText("Not stated by the source")).toBeVisible();
    await expect(page.getByTestId("not-comparable").first()).toBeVisible();
    await expectAccessible(page, info, "medicine-real");
    await screenshot(page, info, "medicine-real");
  });

  test("demo brand shows options to discuss with a saving statement", async ({ page }, info) => {
    await page.goto("/en/search?q=DemoAtorvAlpha");
    await page
      .getByRole("link", { name: /DemoAtorvAlpha/ })
      .first()
      .click();
    await expect(page.getByText("Demo data").first()).toBeVisible();
    await expect(page.getByText(/options, not recommendations/)).toBeVisible();
    await expectAccessible(page, info, "medicine-demo");
    await screenshot(page, info, "medicine-demo");
  });

  test("emergency input interrupts with 112", async ({ page }, info) => {
    await page.goto("/en");
    await page.getByRole("textbox", { name: /Search by brand/ }).fill("I took too many tablets");
    await page.getByRole("button", { name: "Search", exact: true }).click();
    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("link", { name: "Call 112" })).toHaveAttribute("href", "tel:112");
    await expectAccessible(page, info, "emergency");
    await screenshot(page, info, "emergency");
    await dialog.getByRole("button", { name: "This is not an emergency" }).click();
    await expect(dialog).toBeHidden();
  });

  test("emergency in a direct URL also interrupts", async ({ page }) => {
    await page.goto("/en/search?q=overdose");
    await expect(page.getByRole("alertdialog")).toBeVisible();
  });

  test("Jan Aushadhi lookup has no stock claims", async ({ page }, info) => {
    await page.goto("/en/jan-aushadhi");
    await expect(page.getByText(/Real PMBJP data is not loaded/)).toBeVisible();
    await page.getByLabel("PIN code").fill("600001");
    await page.getByRole("button", { name: "Search by PIN" }).click();
    await expect(page.getByText(/Demo Kendra 1 /)).toBeVisible();
    const text = (await page.locator("body").innerText()).toLowerCase();
    for (const word of ["in stock", "out of stock", "available now", "buy now"]) {
      expect(text).not.toContain(word);
    }
    await expectAccessible(page, info, "jan-aushadhi");
    await screenshot(page, info, "jan-aushadhi");
  });

  test("Hindi and Tamil interfaces render fully", async ({ page }, info) => {
    await page.goto("/hi");
    await expect(page.locator("html")).toHaveAttribute("lang", "hi");
    await expect(page.getByTestId("medical-notice")).toContainText("चिकित्सीय सलाह नहीं");
    await expectAccessible(page, info, "home-hi");
    await screenshot(page, info, "home-hi");
    await page.goto("/ta");
    await expect(page.locator("html")).toHaveAttribute("lang", "ta");
    await expect(page.getByTestId("medical-notice")).toContainText("மருத்துவ ஆலோசனை அல்ல");
    await expectAccessible(page, info, "home-ta");
    await screenshot(page, info, "home-ta");
    await page.goto("/ta/search?q=பாராசிட்டமால்");
    await expect(page.getByRole("link", { name: /Paracetamol/ }).first()).toBeVisible();
  });

  test("static pages are accessible", async ({ page }, info) => {
    for (const route of ["about", "privacy", "login", "register", "pharmacist/register"]) {
      await page.goto(`/en/${route}`);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await expectAccessible(page, info, route.replace("/", "-"));
    }
    await screenshot(page, info, "login");
  });

  test("security headers and PWA assets are served", async ({ page, request }) => {
    const response = await page.goto("/en");
    const headers = response?.headers() ?? {};
    expect(headers["content-security-policy"]).toContain("nonce-");
    expect(headers["x-frame-options"]).toBe("DENY");
    expect((await request.get("/manifest.webmanifest")).ok()).toBeTruthy();
    expect((await request.get("/sw.js")).ok()).toBeTruthy();
    expect(await (await request.get("/offline.html")).text()).toContain("112");
  });
});

test.describe("prescriptions", () => {
  test("manual path: verify, compare, summarise, share, expire on delete", async ({
    page,
    context,
  }, info) => {
    await registerUser(page);
    const id = await addManual(page, "Atorvastatin", "10 mg");
    await expect(page.getByText("Needs your check").first()).toBeVisible();
    await expectAccessible(page, info, "verify");
    await screenshot(page, info, "verify-manual");
    const itemUrl = await page.evaluate(async (rx) => {
      const data = await (await fetch(`/api/v1/prescriptions/${rx}`)).json();
      return `/en/prescriptions/${rx}/items/${data.items[0].id}`;
    }, id);
    await page.goto(itemUrl);
    await expect(page.getByTestId("gate-blocked")).toBeVisible();
    await expect(page.getByTestId("price-row")).toHaveCount(0);
    await expectAccessible(page, info, "gate-blocked");
    await screenshot(page, info, "gate-blocked");
    await page.goto(`/en/prescriptions/${id}`);
    await page.getByRole("button", { name: "This is my medicine" }).first().click();
    await expect(page.getByTestId("verified-by")).toHaveText("Confirmed by you");
    await page.getByRole("link", { name: "See prices and options" }).click();
    await expect(page.getByText(/options, not recommendations/)).toBeVisible();
    await expect(page.getByTestId("price-row").first()).toBeVisible();
    await expectAccessible(page, info, "comparison");
    await screenshot(page, info, "comparison");
    await page.goto(`/en/prescriptions/${id}/summary`);
    await expect(page.getByText(/before changing any medicine/)).toBeVisible();
    await page.getByRole("button", { name: "Create share link" }).click();
    const url = await page.getByTestId("share-url").innerText();
    await expectAccessible(page, info, "summary");
    await screenshot(page, info, "summary");
    const download = page.waitForEvent("download");
    await page.getByRole("link", { name: "Download PDF" }).click();
    expect((await download).suggestedFilename()).toBe("medicompare-summary.pdf");
    const anonymous = await context.browser()!.newContext();
    const shared = await anonymous.newPage();
    await shared.goto(url);
    await expect(
      shared.getByText("Discuss with your doctor", { exact: false }).first(),
    ).toBeVisible();
    await page.goto("/en/prescriptions");
    page.on("dialog", (dialog) => void dialog.accept());
    await page.getByRole("button", { name: "Delete" }).first().click();
    await expect(page.getByText(/no saved prescriptions/)).toBeVisible();
    await shared.reload();
    await expect(shared.getByText("We could not find this.")).toBeVisible();
    await anonymous.close();
  });

  test("look-alike name needs an explicit check", async ({ page }, info) => {
    await registerUser(page);
    await addManual(page, "DemoMetacin", "500 mg");
    await expect(page.getByText(/Check carefully: this name looks like/)).toBeVisible();
    const confirm = page.getByRole("button", { name: "This is my medicine" }).first();
    await expect(confirm).toBeDisabled();
    await expectAccessible(page, info, "lasa");
    await screenshot(page, info, "lasa-warning");
    await page.getByRole("checkbox").check();
    await confirm.click();
    await expect(page.getByTestId("verified-by")).toBeVisible();
  });

  test("unknown medicine can be left unresolved and directs to a prescriber", async ({
    page,
  }, info) => {
    await registerUser(page);
    await addManual(page, "xqzvbnwrtl", "5 mg");
    await expect(page.getByText(/No catalogue medicine matches/)).toBeVisible();
    await screenshot(page, info, "no-match");
    await page.getByRole("button", { name: "I can't confirm this" }).click();
    await expect(page.getByText(/ask your prescriber or pharmacist/)).toBeVisible();
  });

  test("upload path with OCR, as a guest, with consent", async ({ page }, info) => {
    test.setTimeout(180_000);
    await page.goto("/en/prescriptions/new");
    await page.getByRole("button", { name: "Upload a photo or PDF" }).click();
    await expect(page.getByText(/deleted automatically after 7 days/)).toBeVisible();
    await expectAccessible(page, info, "upload");
    await screenshot(page, info, "upload-consent");
    await page.getByLabel(/Choose a JPEG/).setInputFiles(SAMPLE);
    await expect(page.getByRole("button", { name: "Upload", exact: true })).toBeDisabled();
    await page.getByRole("checkbox").check();
    await page.getByRole("button", { name: "Upload", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Check each medicine" })).toBeVisible({
      timeout: 120_000,
    });
    await expect(page.getByAltText("Your prescription 1")).toBeVisible();
    await expect(page.getByText("Needs your check").first()).toBeVisible();
    await expect(page.locator("body")).not.toContainText("Democase");
    await expectAccessible(page, info, "verify-upload");
    await screenshot(page, info, "verify-upload");
  });

  test("a corrupt file is refused cleanly", async ({ page }) => {
    await page.goto("/en/prescriptions/new");
    await page.getByRole("button", { name: "Upload a photo or PDF" }).click();
    await page.getByRole("checkbox").check();
    await page.getByLabel(/Choose a JPEG/).setInputFiles({
      name: "rx.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("this is not a pdf"),
    });
    await page.getByRole("button", { name: "Upload", exact: true }).click();
    await expect(page.getByText("Only JPEG, PNG or PDF files are accepted.")).toBeVisible();
  });

  test("direct API calls cannot bypass the gate", async ({ page }) => {
    await registerUser(page);
    const id = await addManual(page, "Metformin", "500 mg");
    const statuses = await page.evaluate(async (rx) => {
      const data = await (await fetch(`/api/v1/prescriptions/${rx}`)).json();
      const base = `/api/v1/prescriptions/${rx}/items/${data.items[0].id}`;
      return Promise.all(
        [`${base}/prices`, `${base}/options`].map(async (url) => (await fetch(url)).status),
      );
    }, id);
    expect(statuses).toEqual([409, 409]);
  });
});

test.describe("pharmacist and admin", () => {
  test("user shares, pharmacist verifies, label differs", async ({ page, context }, info) => {
    await registerUser(page);
    const id = await addManual(page, "Atorvastatin", "10 mg");
    await page
      .getByLabel("Choose a pharmacist")
      .selectOption({ label: "Demo Pharmacist (Demo council (fictional))" });
    await page.getByRole("button", { name: "Share for review" }).click();
    await expect(page.getByText(/Shared with a pharmacist/)).toBeVisible();
    await screenshot(page, info, "share");
    const other = await context.browser()!.newContext();
    const pharmacist = await other.newPage();
    await signIn(pharmacist, DEMO.pharmacist);
    await pharmacist.goto("/en/pharmacist");
    await expectAccessible(pharmacist, info, "pharmacist-queue");
    await screenshot(pharmacist, info, "pharmacist-queue");
    await pharmacist.goto(`/en/pharmacist/${id}`);
    await expect(
      pharmacist.getByRole("heading", { name: "Review a shared prescription" }),
    ).toBeVisible();
    await expectAccessible(pharmacist, info, "pharmacist-review");
    await pharmacist.getByRole("button", { name: "This is my medicine" }).first().click();
    await expect(pharmacist.getByTestId("verified-by")).toHaveText("Confirmed by a pharmacist");
    await screenshot(pharmacist, info, "pharmacist-review");
    await other.close();
    await page.reload();
    await expect(page.getByTestId("verified-by")).toHaveText("Confirmed by a pharmacist");
  });

  test("a pharmacist cannot open an unshared prescription", async ({ page, context }) => {
    await registerUser(page);
    const id = await addManual(page, "Atorvastatin", "10 mg");
    const other = await context.browser()!.newContext();
    const pharmacist = await other.newPage();
    await signIn(pharmacist, DEMO.pharmacist);
    await pharmacist.goto(`/en/pharmacist/${id}`);
    await expect(pharmacist.getByText("We could not find this.")).toBeVisible();
    await other.close();
  });

  test("admin sees freshness, queue, approvals and audit", async ({ page }, info) => {
    await signIn(page, DEMO.admin);
    await page.goto("/en/admin");
    await expect(page.getByText("Update overdue").first()).toBeVisible();
    await expect(page.getByText(/strength: cannot parse/).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "Audit log" })).toBeVisible();
    await expectAccessible(page, info, "admin");
    await screenshot(page, info, "admin");
  });

  test("ordinary users are refused admin data", async ({ page, request }) => {
    await registerUser(page);
    await page.goto("/en/admin");
    await expect(page.getByText("Something went wrong")).toBeVisible();
    await apiLogin(request, DEMO.user);
    expect((await request.get("/api/v1/admin/audit")).status()).toBe(403);
  });
});

test.describe("privacy", () => {
  test("export and delete account", async ({ page }, info) => {
    const email = await registerUser(page);
    await addManual(page, "Atorvastatin", "10 mg");
    await page.goto("/en/account");
    await expect(page.getByText(email)).toBeVisible();
    await expectAccessible(page, info, "account");
    await screenshot(page, info, "account");
    const exported = await page.evaluate(async () => (await fetch("/api/v1/me/export")).json());
    expect(exported.account.email).toBe(email);
    expect(exported.prescriptions).toHaveLength(1);
    page.on("dialog", (dialog) => void dialog.accept());
    await page.getByRole("button", { name: "Delete my account" }).click();
    await expect(page).toHaveURL(/\/en$/);
    const status = await page.evaluate(async () => (await fetch("/api/v1/me/export")).status);
    expect(status).toBe(401);
  });
});
