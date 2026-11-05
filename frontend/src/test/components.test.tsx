import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import path from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";
import en from "../../messages/en.json";
import hi from "../../messages/hi.json";
import ta from "../../messages/ta.json";
import { AccountPage, AdminPage, LoginForm, RegisterForm, SaveToList } from "@/components/account";
import {
  DemoNotice,
  JanAushadhiPage,
  MedicinePage,
  OptionsView,
  SearchBox,
  SearchResults,
} from "@/components/catalogue";
import {
  ItemComparison,
  NewPrescription,
  PharmacistQueue,
  PharmacistReview,
  PrescriptionList,
  SharedPage,
  SummaryPage,
  VerificationPage,
} from "@/components/prescriptions";
import { AppShell, EmergencyDialog } from "@/components/shell";
import { DemoBadge, ErrorState, PriceRow } from "@/components/ui";
import { ApiError, api, compressForUpload, setCsrfToken } from "@/lib/api";
import { buildCsp } from "@/lib/csp";
import { item, medicine, mockFetch, prescription, price, push, renderWithIntl } from "./helpers";
import type { OptionsResponse, SessionUser } from "@/lib/types";

const appState = vi.hoisted(() => ({
  user: null as SessionUser | null,
  raiseEmergency: vi.fn(),
  refreshSession: vi.fn(),
}));

vi.mock("@/i18n/navigation", () => ({
  Link: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => "/",
}));

vi.mock("@/components/shell", async (original) => {
  const actual = await original<typeof import("@/components/shell")>();
  return {
    ...actual,
    useApp: () => ({
      user: appState.user,
      sessionLoading: false,
      refreshSession: appState.refreshSession,
      raiseEmergency: appState.raiseEmergency,
    }),
  };
});

const signedIn: SessionUser = {
  id: "u1",
  email: "a@example.com",
  role: "user",
  display_name: null,
  is_guest: false,
  pharmacist_status: null,
};

beforeEach(() => {
  appState.user = null;
  appState.raiseEmergency.mockClear();
  appState.refreshSession.mockClear();
  push.mockClear();
  setCsrfToken(null);
});

const options = (overrides: Partial<OptionsResponse> = {}): OptionsResponse => ({
  reference: { medicine, prices: [price()] },
  equivalents: [
    {
      medicine: { ...medicine, id: 2, display_name: "DemoMetfoAlpha", is_demo: true },
      prices: [price({ is_demo: true, per_unit_inr: "1.50" })],
      differences: [{ code: "pack_size", detail: "Pack sizes differ: 10 tablet vs 15 tablet." }],
      savings: [{ statement: "Comparing MRP per tablet: A vs B.", price_type: "mrp" }],
      regulatory_flags: [],
    },
  ],
  not_equivalent: [
    {
      medicine: { ...medicine, id: 3, display_name: "Metformin SR" },
      reasons: ["sustained vs conventional."],
      difference_codes: ["release_type"],
      regulatory_flags: [
        {
          flag_type: "quality_alert",
          description: "Batch notice",
          source_name: "CDSCO",
          source_url: null,
          source_date: "2026-10-01",
          is_demo: false,
        },
      ],
    },
  ],
  jan_aushadhi: [
    {
      drug_code: "J1",
      generic_name: "Metformin JA",
      group_name: null,
      unit_size: "10 tablet",
      mrp_inr: "5.00",
      price_type_label: "Catalogue price",
      source: medicine.source,
      last_updated: "2026-10-01",
      is_stale: true,
      is_demo: true,
      medicine_id: 1,
    },
  ],
  disclaimer: "x",
  ...overrides,
});

describe("translations", () => {
  const keys = (value: object, prefix = ""): string[] =>
    Object.entries(value).flatMap(([key, child]) =>
      typeof child === "object" ? keys(child, `${prefix}${key}.`) : [`${prefix}${key}`],
    );

  it("Hindi and Tamil have exactly the English keys", () => {
    expect(keys(hi).sort()).toEqual(keys(en).sort());
    expect(keys(ta).sort()).toEqual(keys(en).sort());
  });

  it("no translated value is left in English or empty", () => {
    const flat = (value: object): string[] =>
      Object.values(value).flatMap((child) =>
        typeof child === "object" ? flat(child) : [String(child)],
      );
    for (const catalogue of [hi, ta]) {
      const strings = flat(catalogue);
      expect(strings.every((text) => text.length > 0)).toBe(true);
      const indic = strings.filter((text) => /[ऀ-ॿ஀-௿]/.test(text));
      expect(indic.length / strings.length).toBeGreaterThan(0.9);
    }
  });

  it.each([
    ["en", en],
    ["hi", hi],
    ["ta", ta],
  ])("%s keeps the safety statement and the 112 number", (_, catalogue) => {
    expect(catalogue.summary.statement.length).toBeGreaterThan(10);
    expect(catalogue.emergency.call).toContain("112");
    expect(catalogue.emergency.body).toContain("112");
    expect(catalogue.app.footer).toContain("112");
  });

  it("never uses stock or selling wording anywhere in the English UI", () => {
    const text = JSON.stringify(en).toLowerCase();
    for (const word of [
      "in stock",
      "out of stock",
      "available now",
      "stocked",
      "buy now",
      "add to cart",
      "we recommend",
    ]) {
      expect(text).not.toContain(word);
    }
  });

  it("no source file has stock or selling wording", () => {
    const folder = path.resolve(__dirname, "../components");
    for (const file of [
      "catalogue.tsx",
      "prescriptions.tsx",
      "account.tsx",
      "ui.tsx",
      "shell.tsx",
    ]) {
      const text = readFileSync(path.join(folder, file), "utf8").toLowerCase();
      expect(text).not.toMatch(/in stock|out of stock|buy now|add to cart/);
    }
  });
});

describe("security", () => {
  it("CSP uses a nonce and forbids framing and objects", () => {
    const csp = buildCsp("abc", false);
    expect(csp).toContain("script-src 'self' 'nonce-abc'");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).not.toContain("unsafe-eval");
    expect(buildCsp("abc", true)).toContain("unsafe-eval");
  });
});

describe("api client", () => {
  it("sends the CSRF token on writes only", async () => {
    const calls = mockFetch({ "POST /x": { body: {} }, "/y": { body: {} } });
    setCsrfToken("token-1");
    await api("/x", { method: "POST", body: "{}" });
    await api("/y");
    expect(new Headers(calls[0].init?.headers).get("X-CSRF-Token")).toBe("token-1");
    expect(new Headers(calls[1].init?.headers).get("X-CSRF-Token")).toBeNull();
  });

  it("turns problem details into ApiError", async () => {
    mockFetch({ "/x": { status: 409, body: { code: "item_not_verified", title: "Blocked" } } });
    await expect(api("/x")).rejects.toMatchObject({ status: 409, code: "item_not_verified" });
  });

  it("leaves PDFs untouched when compressing", async () => {
    const pdf = new File(["%PDF"], "a.pdf", { type: "application/pdf" });
    expect(await compressForUpload(pdf)).toBe(pdf);
  });

  it("falls back to the original image when compression is unavailable", async () => {
    const image = new File(["x"], "a.png", { type: "image/png" });
    vi.stubGlobal("createImageBitmap", vi.fn().mockRejectedValue(new Error("nope")));
    expect(await compressForUpload(image)).toBe(image);
    vi.stubGlobal("createImageBitmap", undefined);
    expect(await compressForUpload(image)).toBe(image);
  });
});

describe("shared UI", () => {
  it("every price shows type, source and date", () => {
    renderWithIntl(<PriceRow price={price()} />);
    expect(screen.getByText(/MRP \(printed/)).toBeInTheDocument();
    expect(screen.getByText("Source: Test source")).toBeInTheDocument();
    expect(screen.getByText("Last updated: 2026-10-01")).toBeInTheDocument();
  });

  it("ceiling prices explain they are not shop prices", () => {
    renderWithIntl(
      <PriceRow price={price({ price_type: "ceiling", price_type_label: "Ceiling" })} />,
    );
    expect(screen.getByText(/not what a shop charges/)).toBeInTheDocument();
  });

  it("labels stale prices and demo data", () => {
    renderWithIntl(<PriceRow price={price({ is_stale: true, is_demo: true })} />);
    expect(screen.getByText("May be out of date")).toBeInTheDocument();
    expect(screen.getByText("Demo data")).toBeInTheDocument();
  });

  it("demo badge can be hidden", () => {
    const { container } = renderWithIntl(<DemoBadge show={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("error state handles sign-in, not-found and retry", async () => {
    const retry = vi.fn();
    const { rerender } = renderWithIntl(<ErrorState error={new ApiError(401, "x", "")} />);
    expect(screen.getByText("Go to sign in")).toBeInTheDocument();
    rerender(<div />);
    renderWithIntl(<ErrorState error={new ApiError(500, "x", "")} onRetry={retry} />);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalled();
  });

  it("emergency dialog shows 112, takes focus and can be dismissed", async () => {
    const dismiss = vi.fn();
    renderWithIntl(<EmergencyDialog onDismiss={dismiss} />);
    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveFocus();
    expect(screen.getByRole("link", { name: "Call 112" })).toHaveAttribute("href", "tel:112");
    await userEvent.click(screen.getByRole("button", { name: "This is not an emergency" }));
    expect(dismiss).toHaveBeenCalled();
  });

  it("the shell always shows the medical notice", async () => {
    mockFetch({ "/auth/me": { body: { user: null, csrf_token: null } } });
    vi.stubGlobal("navigator", { ...navigator });
    renderWithIntl(
      <AppShell>
        <p>content</p>
      </AppShell>,
    );
    expect(screen.getByTestId("medical-notice")).toHaveTextContent("not medical advice");
    expect(screen.getByRole("main")).toHaveTextContent("content");
    expect(screen.getByRole("link", { name: "Sign in" })).toBeInTheDocument();
  });
});

describe("search", () => {
  it("interrupts before navigating when the query is an emergency", async () => {
    mockFetch({ "POST /safety/check": { body: { detected: true } } });
    renderWithIntl(<SearchBox />);
    await userEvent.type(screen.getByRole("textbox"), "took too many pills{enter}");
    await waitFor(() => expect(appState.raiseEmergency).toHaveBeenCalled());
    expect(push).not.toHaveBeenCalled();
  });

  it("navigates for ordinary queries, and ignores one letter", async () => {
    mockFetch({ "POST /safety/check": { body: { detected: false } } });
    renderWithIntl(<SearchBox />);
    await userEvent.type(screen.getByRole("textbox"), "m{enter}");
    expect(push).not.toHaveBeenCalled();
    await userEvent.type(screen.getByRole("textbox"), "etformin{enter}");
    await waitFor(() => expect(push).toHaveBeenCalledWith("/search?q=metformin"));
  });

  const hit = (id: number, type: string) => ({
    medicine: { ...medicine, id, display_name: `Med ${id}` },
    match_type: type,
    reason: `reason ${id}`,
  });

  it("separates exact from possible matches and explains each", async () => {
    mockFetch({
      "/search?q=met": {
        body: {
          query: "met",
          emergency: { detected: false },
          exact_matches: [hit(1, "exact")],
          possible_matches: [hit(2, "possible")],
        },
      },
    });
    renderWithIntl(<SearchResults query="met" />);
    expect(await screen.findByRole("heading", { name: "Exact matches" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Possible matches" })).toBeInTheDocument();
    expect(screen.getByText("reason 2")).toBeInTheDocument();
    expect(screen.getByText(/A similar name does not mean the same medicine/)).toBeInTheDocument();
  });

  it("has prompt, empty, error and emergency states", async () => {
    const { unmount } = renderWithIntl(<SearchResults query="" />);
    expect(screen.getByText(/at least two letters/)).toBeInTheDocument();
    unmount();
    const empty = {
      query: "zz",
      emergency: { detected: false },
      exact_matches: [],
      possible_matches: [],
    };
    mockFetch({
      "/search?q=zz": { body: empty },
      "/search?q=bad": { status: 500, body: {} },
      "/search?q=sos": { body: { ...empty, emergency: { detected: true } } },
    });
    const second = renderWithIntl(<SearchResults query="zz" />);
    expect(await screen.findByText(/No medicines found/)).toBeInTheDocument();
    second.unmount();
    const third = renderWithIntl(<SearchResults query="bad" />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    third.unmount();
    renderWithIntl(<SearchResults query="sos" />);
    await waitFor(() => expect(appState.raiseEmergency).toHaveBeenCalled());
  });
});

describe("options", () => {
  it("shows the disclaimer, differences, sources and not-comparable reasons", () => {
    const { container } = renderWithIntl(<OptionsView data={options()} />);
    expect(screen.getByText(/These are options, not recommendations/)).toBeInTheDocument();
    expect(screen.getByText(/Pack sizes differ/)).toBeInTheDocument();
    expect(screen.getByText(/Comparing MRP per tablet/)).toBeInTheDocument();
    const unlike = screen.getByTestId("not-comparable");
    expect(within(unlike).getByText(/sustained vs conventional/)).toBeInTheDocument();
    expect(within(unlike).getByText(/Batch notice/)).toBeInTheDocument();
    expect(within(unlike).queryByText(/per tablet/)).not.toBeInTheDocument();
    expect(screen.getByText(/A listing does not confirm/)).toBeInTheDocument();
    expect(container.innerHTML).not.toMatch(/green/);
    expect(container.textContent?.toLowerCase()).not.toContain("recommended");
  });

  it("handles no equivalent options", () => {
    renderWithIntl(
      <OptionsView data={options({ equivalents: [], not_equivalent: [], jan_aushadhi: [] })} />,
    );
    expect(screen.getByText(/no product with confirmed identical/)).toBeInTheDocument();
  });

  it("renders a medicine with composition and unstated salt", async () => {
    mockFetch({ "/medicines/1/options": { body: options() } });
    renderWithIntl(<MedicinePage id="1" />);
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Metformin 500mg");
    expect(screen.getByText("Not stated by the source")).toBeInTheDocument();
    expect(screen.getByText(/does not prove there are none/)).toBeInTheDocument();
  });

  it("shows not-found", async () => {
    mockFetch({});
    renderWithIntl(<MedicinePage id="9" />);
    expect(await screen.findByText("We could not find this.")).toBeInTheDocument();
  });
});

describe("Jan Aushadhi", () => {
  const kendra = {
    kendra_code: "K1",
    name: "Kendra One",
    address: "Road",
    district: "Chennai",
    state: "Tamil Nadu",
    pin_code: "600001",
    source: medicine.source,
    last_updated: "2026-10-01",
    is_demo: true,
    distance_km: 2.5,
  };
  const product = options().jan_aushadhi[0];

  it("warns about demo data, validates PIN and finds Kendras with no stock claim", async () => {
    mockFetch({
      "/jan-aushadhi/products": { body: { products: [product] } },
      "/jan-aushadhi/kendras?pin=600001": { body: { kendras: [kendra] } },
    });
    renderWithIntl(<JanAushadhiPage />);
    expect(await screen.findByText(/Real PMBJP data is not loaded/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("PIN code"), "12");
    await userEvent.click(screen.getByRole("button", { name: "Search by PIN" }));
    expect(screen.getByRole("alert")).toHaveTextContent("6-digit");
    await userEvent.clear(screen.getByLabelText("PIN code"));
    await userEvent.type(screen.getByLabelText("PIN code"), "600001");
    await userEvent.click(screen.getByRole("button", { name: "Search by PIN" }));
    const list = await screen.findByTestId("kendra-list");
    expect(await within(list).findByText("Kendra One")).toBeInTheDocument();
    expect(within(list).getByText("2.5 km away")).toBeInTheDocument();
    expect(document.body.textContent?.toLowerCase()).not.toMatch(/in stock|available now/);
  });

  it("searches by area, by product, and handles empty results and location failure", async () => {
    mockFetch({
      "/jan-aushadhi/products": { body: { products: [product] } },
      "/jan-aushadhi/products?q=zz": { body: { products: [] } },
      "/jan-aushadhi/kendras?area=Nowhere": { body: { kendras: [] } },
    });
    const geolocation = { getCurrentPosition: vi.fn((_ok, fail) => fail(new Error("denied"))) };
    Object.defineProperty(navigator, "geolocation", { value: geolocation, configurable: true });
    renderWithIntl(<JanAushadhiPage />);
    await screen.findByText("Metformin JA");
    await userEvent.type(screen.getByLabelText("District or state"), "Nowhere");
    await userEvent.click(screen.getByRole("button", { name: "Search by area" }));
    expect(await screen.findByText(/No Kendras found/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Generic name or product code"), "zz");
    await userEvent.click(screen.getByRole("button", { name: "Search listings" }));
    expect(await screen.findByText("No listings found.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Use my location once" }));
    expect(await screen.findByText(/could not get your location/)).toBeInTheDocument();
  });
});

describe("prescription verification", () => {
  it("shows unknown and unclear states instead of guessing", async () => {
    mockFetch({
      "/prescriptions/rx-1": { body: prescription() },
      "/pharmacists": { body: { pharmacists: [] } },
    });
    renderWithIntl(<VerificationPage id="rx-1" />);
    expect(await screen.findByText("Not found")).toBeInTheDocument();
    expect(screen.getByText("Unclear")).toBeInTheDocument();
    expect(screen.getByTestId("item-status")).toHaveTextContent("Needs your check");
    expect(screen.queryByText("See prices and options")).not.toBeInTheDocument();
  });

  it("sends the chosen medicine for server verification", async () => {
    const verified = item({
      status: "verified",
      verified_by_type: "user",
      verified_medicine_id: 1,
    });
    let current = prescription();
    const calls = mockFetch({
      "/prescriptions/rx-1": () => ({ body: current }),
      "/pharmacists": { body: { pharmacists: [] } },
      "POST /prescriptions/rx-1/items/item-1/verify": () => {
        current = prescription({ items: [verified] });
        return { body: verified };
      },
    });
    renderWithIntl(<VerificationPage id="rx-1" />);
    await userEvent.click(await screen.findByRole("button", { name: "This is my medicine" }));
    expect(await screen.findByTestId("verified-by")).toHaveTextContent("Confirmed by you");
    expect(screen.getByRole("link", { name: "See prices and options" })).toBeInTheDocument();
    const call = calls.find((entry) => entry.method === "POST");
    expect(JSON.parse(String(call?.init?.body))).toMatchObject({
      medicine_id: 1,
      lasa_acknowledged: false,
    });
  });

  it("look-alike names block confirmation until acknowledged", async () => {
    mockFetch({
      "/prescriptions/rx-1": {
        body: prescription({ items: [item({ requires_lasa_review: true })] }),
      },
      "/pharmacists": { body: { pharmacists: [] } },
    });
    renderWithIntl(<VerificationPage id="rx-1" />);
    const confirm = await screen.findByRole("button", { name: "This is my medicine" });
    expect(confirm).toBeDisabled();
    expect(screen.getByText(/looks like another medicine/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox"));
    expect(confirm).toBeEnabled();
  });

  it("no candidates: offers correction, and server errors are shown", async () => {
    mockFetch({
      "/prescriptions/rx-1": { body: prescription({ items: [item({ candidates: [] })] }) },
      "/pharmacists": { body: { pharmacists: [] } },
      "POST /prescriptions/rx-1/items/item-1/unresolved": {
        status: 500,
        body: { title: "Failed here" },
      },
      "PATCH /prescriptions/rx-1/items/item-1": { body: item() },
    });
    renderWithIntl(<VerificationPage id="rx-1" />);
    expect(await screen.findByText(/No catalogue medicine matches/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "I can't confirm this" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Failed here");
    await userEvent.click(screen.getByRole("button", { name: "Correct what we read" }));
    await userEvent.type(screen.getByLabelText("How often"), "OD");
    await userEvent.click(screen.getByRole("button", { name: "Save correction" }));
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Save correction" })).not.toBeInTheDocument(),
    );
  });

  it("verified by pharmacist is distinct, and unresolved directs to a prescriber", async () => {
    mockFetch({
      "/prescriptions/rx-1": {
        body: prescription({
          items: [
            item({
              status: "verified",
              verified_by_type: "pharmacist",
              events: [
                {
                  action: "verified",
                  verifier_type: "pharmacist",
                  diff: {},
                  note: "ok",
                  created_at: "2026-11-05T10:00:00Z",
                },
              ],
            }),
            item({ id: "item-2", status: "unresolved" }),
          ],
        }),
      },
      "/pharmacists": { body: { pharmacists: [] } },
    });
    renderWithIntl(<VerificationPage id="rx-1" />);
    expect(await screen.findByText("Confirmed by a pharmacist")).toBeInTheDocument();
    expect(screen.getByText(/ask your prescriber or pharmacist/)).toBeInTheDocument();
  });

  it.each([
    ["processing", /Reading your prescription/],
    ["unreadable", /Nothing was guessed/],
    ["failed", /could not process/],
  ] as const)("status %s has its own state", async (status, text) => {
    mockFetch({ "/prescriptions/rx-1": { body: prescription({ status, items: [] }) } });
    renderWithIntl(<VerificationPage id="rx-1" />);
    expect(await screen.findByText(text)).toBeInTheDocument();
  });

  it("raises the emergency interrupt", async () => {
    mockFetch({
      "/prescriptions/rx-1": { body: prescription({ emergency: { detected: true } }) },
      "/pharmacists": { body: { pharmacists: [] } },
    });
    renderWithIntl(<VerificationPage id="rx-1" />);
    await waitFor(() => expect(appState.raiseEmergency).toHaveBeenCalled());
  });

  it("image view marks uncertain spans", async () => {
    mockFetch({
      "/prescriptions/rx-1": {
        body: prescription({
          page_count: 1,
          source_type: "upload",
          items: [item({ ocr_quality: 0.4 })],
        }),
      },
      "/pharmacists": { body: { pharmacists: [] } },
    });
    renderWithIntl(<VerificationPage id="rx-1" />);
    const image = await screen.findByAltText("Your prescription 1");
    Object.defineProperty(image, "naturalWidth", { value: 1000 });
    Object.defineProperty(image, "naturalHeight", { value: 1000 });
    image.dispatchEvent(new Event("load", { bubbles: true }));
    expect(await screen.findByTestId("uncertain-span")).toBeInTheDocument();
  });

  it("sharing names a chosen pharmacist and can be stopped", async () => {
    const pharmacists = {
      pharmacists: [
        { id: "ph1", display_name: "P One", state_council: "TN", registration_label: "x" },
      ],
    };
    const calls = mockFetch({
      "/prescriptions/rx-1": {
        body: prescription({
          shares: [{ pharmacist_id: "ph2", status: "reviewed", note: "Fine" }],
        }),
      },
      "/pharmacists": { body: pharmacists },
      "POST /prescriptions/rx-1/shares": { body: {} },
      "DELETE /prescriptions/rx-1/shares/ph2": { status: 204 },
    });
    renderWithIntl(<VerificationPage id="rx-1" />);
    expect(await screen.findByText(/Fine/)).toBeInTheDocument();
    expect(await screen.findByText(/self-declared, checked manually by admin/)).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Choose a pharmacist"), "ph1");
    await userEvent.click(screen.getByRole("button", { name: "Share for review" }));
    await userEvent.click(screen.getByRole("button", { name: "Stop sharing" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
    const share = calls.find((c) => c.method === "POST");
    expect(JSON.parse(String(share?.init?.body))).toEqual({ pharmacist_id: "ph1" });
  });
});

describe("downstream gate in the UI", () => {
  it("shows no prices when the server refuses an unverified item", async () => {
    mockFetch({
      "/prescriptions/rx-1/items/item-1/options": {
        status: 409,
        body: { code: "item_not_verified", title: "x" },
      },
    });
    renderWithIntl(<ItemComparison id="rx-1" itemId="item-1" />);
    expect(await screen.findByTestId("gate-blocked")).toHaveTextContent(
      "Confirm this medicine first",
    );
    expect(screen.queryByTestId("price-row")).not.toBeInTheDocument();
  });

  it("shows prices once the server allows it", async () => {
    mockFetch({ "/prescriptions/rx-1/items/item-1/options": { body: options() } });
    renderWithIntl(<ItemComparison id="rx-1" itemId="item-1" />);
    expect((await screen.findAllByTestId("price-row")).length).toBeGreaterThan(0);
  });
});

describe("adding a prescription", () => {
  it("manual entry creates a guest session when signed out, then opens checking", async () => {
    const calls = mockFetch({
      "POST /auth/guest": { body: { user: {}, csrf_token: "guest-token" } },
      "POST /prescriptions/manual": { body: prescription({ id: "rx-9" }) },
    });
    renderWithIntl(<NewPrescription />);
    await userEvent.type(screen.getByLabelText("Medicine name"), "Metformin");
    await userEvent.click(screen.getByRole("button", { name: "Add another medicine" }));
    await userEvent.click(screen.getAllByRole("button", { name: "Remove" })[1]);
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/prescriptions/rx-9"));
    expect(calls.map((call) => call.path)).toEqual(["/auth/guest", "/prescriptions/manual"]);
    expect(new Headers(calls[1].init?.headers).get("X-CSRF-Token")).toBe("guest-token");
  });

  it("manual entry raises an emergency and reports errors", async () => {
    appState.user = signedIn;
    let fail = true;
    mockFetch({
      "POST /prescriptions/manual": () =>
        fail
          ? { status: 500, body: { title: "x" } }
          : { body: prescription({ emergency: { detected: true } }) },
    });
    renderWithIntl(<NewPrescription />);
    await userEvent.type(screen.getByLabelText("Medicine name"), "overdose");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() => expect(appState.raiseEmergency).toHaveBeenCalled());
  });

  it("upload needs consent and a file, and shows the notice", async () => {
    appState.user = signedIn;
    const notice = {
      what_is_processed: "Your image",
      engine: "rapidocr",
      engine_location: "Own server",
      storage: "Private",
      retention_days: 7,
      your_controls: "Delete any time",
    };
    const calls = mockFetch({
      "/prescriptions/consent-notice": { body: notice },
      "POST /prescriptions/upload": { body: prescription({ id: "rx-7" }) },
    });
    renderWithIntl(<NewPrescription />);
    await userEvent.click(screen.getByRole("button", { name: "Upload a photo or PDF" }));
    expect(await screen.findByText(/deleted automatically after 7 days/)).toBeInTheDocument();
    expect(screen.getByText(/rapidocr/)).toBeInTheDocument();
    const submit = screen.getByRole("button", { name: "Upload" });
    expect(submit).toBeDisabled();
    await userEvent.upload(
      screen.getByLabelText(/Choose a JPEG/),
      new File(["%PDF-1.7"], "rx.pdf", { type: "application/pdf" }),
    );
    expect(submit).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox"));
    expect(submit).toBeEnabled();
    await userEvent.click(submit);
    await waitFor(() => expect(push).toHaveBeenCalledWith("/prescriptions/rx-7"));
    const form = calls.find((call) => call.method === "POST")?.init?.body as FormData;
    expect(form.get("consent")).toBe("true");
  });

  it("upload shows a rejection from the server", async () => {
    appState.user = signedIn;
    mockFetch({
      "/prescriptions/consent-notice": {
        body: {
          what_is_processed: "a",
          engine: "b",
          engine_location: "c",
          storage: "d",
          retention_days: 7,
          your_controls: "e",
        },
      },
      "POST /prescriptions/upload": {
        status: 415,
        body: { code: "unsupported_type", title: "Only JPEG, PNG or PDF" },
      },
    });
    renderWithIntl(<NewPrescription />);
    await userEvent.click(screen.getByRole("button", { name: "Upload a photo or PDF" }));
    await screen.findByRole("checkbox");
    await userEvent.upload(
      screen.getByLabelText(/Choose a JPEG/),
      new File(["x"], "a.pdf", { type: "application/pdf" }),
    );
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Upload" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Only JPEG");
  });

  it("lists prescriptions with retention and supports deletion", async () => {
    appState.user = signedIn;
    const calls = mockFetch({
      "/prescriptions": { body: { prescriptions: [prescription()] } },
      "DELETE /prescriptions/rx-1": { status: 204 },
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderWithIntl(<PrescriptionList />);
    expect(await screen.findByText(/Deleted automatically on 2026-11-12/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(calls.some((call) => call.method === "DELETE")).toBe(true));
  });

  it("shows an empty list to guests", () => {
    renderWithIntl(<PrescriptionList />);
    expect(screen.getByText(/no saved prescriptions/)).toBeInTheDocument();
  });
});

describe("summaries", () => {
  const entry = {
    verified_by: "pharmacist",
    medicine: {
      ...medicine,
      regulatory_flags: [
        {
          flag_type: "prohibited_fdc",
          description: "Prohibited",
          source_name: "CDSCO",
          source_url: null,
          source_date: "2026-01-01",
          is_demo: true,
        },
      ],
    },
    prices: [price()],
    options: options().equivalents,
    jan_aushadhi: options().jan_aushadhi,
  };
  const summary = {
    generated_at: "2026-11-05T00:00:00Z",
    label: "For my pharmacist",
    medicines: [entry],
    items_not_included: 2,
    statement: "s",
    notice: "n",
    contains_demo_data: true,
  };

  it("states what is excluded, and creates an expiring link", async () => {
    mockFetch({
      "/prescriptions/rx-1/summary": { body: summary },
      "POST /prescriptions/rx-1/share-links": {
        body: { token: "tok123", expires_at: "2026-11-12T00:00:00Z" },
      },
    });
    renderWithIntl(<SummaryPage id="rx-1" />);
    expect(await screen.findByText(/2 item\(s\) not included/)).toBeInTheDocument();
    expect(
      screen.getByText(/Discuss with your doctor or pharmacist before changing/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Prohibited/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Optional label/), "note");
    await userEvent.click(screen.getByRole("button", { name: "Create share link" }));
    expect(await screen.findByTestId("share-url")).toHaveTextContent("tok123");
    expect(screen.getByText(/expires 2026-11-12/)).toBeInTheDocument();
  });

  it("shared page handles valid, expired and unknown links", async () => {
    mockFetch({
      "/shared/ok": { body: { ...summary, medicines: [], items_not_included: 0 } },
      "/shared/old": { status: 410, body: { code: "link_expired", title: "x" } },
    });
    const first = renderWithIntl(<SharedPage token="ok" />);
    expect(await screen.findByText("No confirmed medicines yet.")).toBeInTheDocument();
    first.unmount();
    const second = renderWithIntl(<SharedPage token="old" />);
    expect(await screen.findByText(/has expired/)).toBeInTheDocument();
    second.unmount();
    renderWithIntl(<SharedPage token="none" />);
    expect(await screen.findByText("We could not find this.")).toBeInTheDocument();
  });
});

describe("pharmacist portal", () => {
  it("queue shows empty, pending and items", async () => {
    mockFetch({ "/pharmacist/queue": { status: 403, body: { code: "forbidden", title: "x" } } });
    const pending = renderWithIntl(<PharmacistQueue />);
    expect(await screen.findByText(/waiting for admin approval/)).toBeInTheDocument();
    pending.unmount();
    mockFetch({ "/pharmacist/queue": { body: { queue: [] } } });
    const empty = renderWithIntl(<PharmacistQueue />);
    expect(await screen.findByText(/Nothing has been shared/)).toBeInTheDocument();
    empty.unmount();
    mockFetch({
      "/pharmacist/queue": {
        body: {
          queue: [
            {
              prescription_id: "rx-1",
              open_items: 1,
              total_items: 2,
              shared_at: "2026-11-05T00:00:00Z",
            },
          ],
        },
      },
    });
    renderWithIntl(<PharmacistQueue />);
    expect(await screen.findByText(/1 of 2 items open/)).toBeInTheDocument();
  });

  it("review verifies through the pharmacist route and can finish", async () => {
    const verified = item({ status: "verified", verified_by_type: "pharmacist" });
    let current = prescription();
    const calls = mockFetch({
      "/pharmacist/prescriptions/rx-1": () => ({ body: current }),
      "POST /pharmacist/prescriptions/rx-1/items/item-1/verify": () => {
        current = prescription({ items: [verified] });
        return { body: verified };
      },
      "POST /pharmacist/prescriptions/rx-1/complete": { body: {} },
    });
    renderWithIntl(<PharmacistReview id="rx-1" />);
    await userEvent.click(await screen.findByRole("button", { name: "This is my medicine" }));
    expect(await screen.findByText("Confirmed by a pharmacist")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Note"), "All clear");
    await userEvent.click(screen.getByRole("button", { name: "Finish review" }));
    expect(await screen.findByRole("button", { name: "Review finished" })).toBeDisabled();
    expect(
      calls.some((call) =>
        call.path.includes("/pharmacist/prescriptions/rx-1/items/item-1/verify"),
      ),
    ).toBe(true);
  });
});

describe("accounts", () => {
  it("signs in and maps failure messages", async () => {
    let status = 401;
    mockFetch({
      "POST /auth/login": () =>
        status === 200
          ? { body: { user: signedIn, csrf_token: "c" } }
          : {
              status,
              body: { code: status === 401 ? "invalid_credentials" : "account_locked", title: "x" },
            },
    });
    renderWithIntl(<LoginForm />);
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "password-123");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("incorrect");
    status = 429;
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Too many failed"));
    status = 200;
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/account"));
    expect(appState.refreshSession).toHaveBeenCalled();
  });

  it("guest entry goes straight to adding a prescription", async () => {
    mockFetch({ "POST /auth/guest": { body: { user: signedIn, csrf_token: "c" } } });
    renderWithIntl(<LoginForm />);
    await userEvent.click(screen.getByRole("button", { name: "Continue without an account" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/prescriptions/new"));
  });

  it("registers a user and reports a taken email", async () => {
    mockFetch({
      "POST /auth/register": { status: 409, body: { code: "email_taken", title: "x" } },
    });
    renderWithIntl(<RegisterForm />);
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "password-123");
    await userEvent.type(screen.getByLabelText("Name (optional)"), "A");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already exists");
  });

  it("pharmacist registration says the number is self-declared", async () => {
    const calls = mockFetch({
      "POST /auth/register-pharmacist": { status: 201, body: { user: signedIn, csrf_token: "c" } },
    });
    renderWithIntl(<RegisterForm pharmacist />);
    expect(screen.getByText(/does not verify it automatically/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Email"), "p@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "password-123");
    await userEvent.type(screen.getByLabelText("Pharmacist registration number"), "TN-1");
    await userEvent.type(screen.getByLabelText("State pharmacy council"), "TN");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/pharmacist"));
    expect(JSON.parse(String(calls[0].init?.body)).registration_number).toBe("TN-1");
  });

  it("account page offers export, lists and confirmed deletion", async () => {
    appState.user = signedIn;
    const list = { id: "l1", name: "Family", medicines: [medicine] };
    const calls = mockFetch({
      "/lists": { body: { lists: [list] } },
      "POST /lists": { body: list },
      "DELETE /lists/l1": { status: 204 },
      "DELETE /me": { status: 204 },
      "POST /auth/logout": { status: 204 },
    });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderWithIntl(<AccountPage />);
    expect(await screen.findByText("Family")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Export my data/ })).toHaveAttribute(
      "href",
      "/api/v1/me/export",
    );
    await userEvent.click(screen.getByRole("button", { name: "Delete my account" }));
    expect(calls.some((call) => call.path === "/me")).toBe(false);
    confirm.mockReturnValue(true);
    await userEvent.click(screen.getByRole("button", { name: "Delete my account" }));
    await waitFor(() => expect(calls.some((call) => call.path === "/me")).toBe(true));
    await userEvent.type(screen.getByLabelText("List name"), "New");
    await userEvent.click(screen.getByRole("button", { name: "Create list" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete list" }));
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    await waitFor(() => expect(calls.some((call) => call.path === "/auth/logout")).toBe(true));
  });

  it("account page handles guests and signed-out visitors", () => {
    const anonymous = renderWithIntl(<AccountPage />);
    expect(screen.getByText("Go to sign in")).toBeInTheDocument();
    anonymous.unmount();
    appState.user = { ...signedIn, is_guest: true, email: null };
    renderWithIntl(<AccountPage />);
    expect(screen.getByText(/temporary guest session/)).toBeInTheDocument();
  });

  it("saves a medicine to the first list", async () => {
    appState.user = signedIn;
    mockFetch({
      "/lists": { body: { lists: [{ id: "l1", name: "Family", medicines: [] }] } },
      "POST /lists/l1/items": { body: {} },
    });
    renderWithIntl(<SaveToList medicineId={1} />);
    await userEvent.click(await screen.findByRole("button", { name: "Save to list: Family" }));
    expect(await screen.findByRole("button", { name: "Saved" })).toBeDisabled();
  });
});

describe("admin", () => {
  const routes = {
    "/admin/sources": {
      body: {
        sources: [
          {
            code: "nppa",
            name: "NPPA",
            owner: "Gov",
            is_demo: false,
            is_stale: true,
            data_as_of: "2026-03-31",
            next_update_due: null,
            medicines: 1,
            prices: 1,
          },
          {
            code: "demo",
            name: "Demo",
            owner: "x",
            is_demo: true,
            is_stale: false,
            data_as_of: null,
            next_update_due: null,
            medicines: 1,
            prices: 1,
          },
        ],
      },
    },
    "/admin/imports": {
      body: {
        batches: [
          {
            id: 5,
            source: "demo",
            is_demo: true,
            kind: "catalogue",
            status: "validated",
            file_name: "a.csv",
            row_count: 3,
            valid_count: 2,
            failed_count: 1,
          },
        ],
      },
    },
    "/admin/review-queue": {
      body: {
        rows: [
          {
            id: 9,
            batch_id: 5,
            batch_status: "validated",
            row_number: 2,
            raw: { name: "x" },
            errors: ["strength: bad"],
          },
        ],
      },
    },
    "/admin/pharmacists": {
      body: {
        pharmacists: [
          {
            user_id: "p1",
            email: "p@example.com",
            display_name: null,
            registration_number: "TN-1",
            state_council: "TN",
            status: "pending",
          },
        ],
      },
    },
    "/admin/audit": {
      body: {
        events: [
          {
            id: 1,
            actor_id: null,
            action: "import_staged",
            entity_type: "import_batch",
            entity_id: "5",
            created_at: "2026-11-05T00:00:00Z",
          },
        ],
      },
    },
    "POST /admin/imports": { status: 201, body: {} },
    "POST /admin/imports/5/publish": { body: {} },
    "POST /admin/imports/5/reject": { body: {} },
    "PUT /admin/review-queue/9": { body: {} },
    "DELETE /admin/review-queue/9": { status: 204 },
    "POST /admin/pharmacists/p1/decision": { body: {} },
  };

  it("shows freshness, queue, approvals and audit, and acts on them", async () => {
    const calls = mockFetch(routes);
    renderWithIntl(<AdminPage />);
    expect(await screen.findByText("Update overdue")).toBeInTheDocument();
    expect(await screen.findByText(/strength: bad/)).toBeInTheDocument();
    expect(await screen.findByText("import_staged")).toBeInTheDocument();
    expect(screen.getByText(/2 valid, 1 failed of 3/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Publish valid rows" }));
    await userEvent.click(screen.getByRole("button", { name: "Reject batch" }));
    await userEvent.click(await screen.findByRole("button", { name: "Approve" }));
    await userEvent.click(screen.getByRole("button", { name: "Reject" }));
    await userEvent.click(screen.getByRole("button", { name: "Save corrected row (JSON)" }));
    await userEvent.click(screen.getByRole("button", { name: "Dismiss row" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
    expect(calls.some((c) => c.path === "/admin/pharmacists/p1/decision")).toBe(true);
    expect(calls.some((c) => c.method === "PUT")).toBe(true);
  });

  it("stages an import and shows errors", async () => {
    const calls = mockFetch({
      ...routes,
      "POST /admin/imports": { status: 422, body: { title: "File is not UTF-8" } },
    });
    renderWithIntl(<AdminPage />);
    await screen.findByText("Update overdue");
    await userEvent.selectOptions(screen.getByLabelText("Source"), "nppa");
    await userEvent.selectOptions(screen.getByLabelText("Import kind"), "ja_kendras");
    await userEvent.upload(
      screen.getByLabelText("CSV file"),
      new File(["a,b"], "a.csv", { type: "text/csv" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Stage and validate" }));
    expect(await screen.findByText("File is not UTF-8")).toBeInTheDocument();
    const form = calls.find((c) => c.method === "POST" && c.path === "/admin/imports")?.init
      ?.body as FormData;
    expect(form.get("kind")).toBe("ja_kendras");
  });

  it("refuses for non-admins", async () => {
    mockFetch({ "/admin/sources": { status: 403, body: { code: "forbidden", title: "x" } } });
    renderWithIntl(<AdminPage />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

describe("real data", () => {
  it("explains a notified retail price, and hides the ceiling text", () => {
    renderWithIntl(
      <PriceRow
        price={price({
          price_type: "notified_retail",
          price_type_label: "NPPA notified retail price",
        })}
      />,
    );
    expect(screen.getByText(/It is not a shop price/)).toBeInTheDocument();
    expect(screen.queryByText(/ceiling price is the legal maximum/)).not.toBeInTheDocument();
  });

  it("shows the demo notice only while demo data is loaded", async () => {
    mockFetch({ "/meta": { body: { demo_data_loaded: true } } });
    const shown = renderWithIntl(<DemoNotice />);
    expect(await screen.findByText(/Anything marked Demo data is fictional/)).toBeInTheDocument();
    shown.unmount();
    mockFetch({ "/meta": { body: { demo_data_loaded: false } } });
    const { container } = renderWithIntl(<DemoNotice />);
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("says Jan Aushadhi data is not loaded, instead of calling an empty list demo data", async () => {
    mockFetch({ "/jan-aushadhi/products": { body: { products: [] } } });
    renderWithIntl(<JanAushadhiPage />);
    expect(await screen.findByText(/No listings or Kendras can be shown/)).toBeInTheDocument();
    expect(screen.queryByText(/Everything on this page is Demo data/)).not.toBeInTheDocument();
  });
});
