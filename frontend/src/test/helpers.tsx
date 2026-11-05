import { render } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { vi } from "vitest";
import messages from "../../messages/en.json";
import type { MedicineDetail, Price, Prescription, RxItem } from "@/lib/types";

export const push = vi.fn();

export function renderWithIntl(node: ReactNode, locale = "en", catalogue: object = messages) {
  return render(
    <NextIntlClientProvider locale={locale} messages={catalogue as typeof messages}>
      {node}
    </NextIntlClientProvider>,
  );
}

export type Route = { status?: number; body?: unknown; type?: string };
export type Routes = Record<string, Route | ((init?: RequestInit) => Route)>;

/** Fake backend. Keys are "METHOD /path" or "/path" for GET; unmatched calls return 404. */
export function mockFetch(routes: Routes) {
  const calls: { method: string; path: string; init?: RequestInit }[] = [];
  const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).replace("/api/v1", "");
    const method = (init?.method ?? "GET").toUpperCase();
    calls.push({ method, path, init });
    const entry = routes[`${method} ${path}`] ?? (method === "GET" ? routes[path] : undefined);
    const route = typeof entry === "function" ? entry(init) : entry;
    const status = route?.status ?? (route ? 200 : 404);
    const body =
      status === 204
        ? null
        : JSON.stringify(route?.body ?? { code: "not_found", title: "Not found" });
    return new Response(body, {
      status,
      headers: { "content-type": route?.type ?? "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetcher);
  return calls;
}

export const source = {
  code: "s",
  name: "Test source",
  owner: "Owner",
  url: "https://x",
  is_demo: false,
};

export const price = (overrides: Partial<Price> = {}): Price => ({
  price_type: "mrp",
  price_type_label: "MRP (printed maximum retail price)",
  amount_inr: "20.00",
  pack: "10 tablet",
  pack_unit: "tablet",
  per_unit_inr: "2.00",
  source,
  observed_at: "2026-10-01",
  last_updated: "2026-10-01",
  is_stale: false,
  is_demo: false,
  ...overrides,
});

export const medicine: MedicineDetail = {
  id: 1,
  display_name: "Metformin 500mg Tablet",
  generic_name: "Metformin",
  brand: null,
  dosage_form: "Tablet",
  release_type: "Conventional",
  route: "Oral",
  is_demo: false,
  ingredients: [{ name: "Metformin", salt_form: null, salt_form_stated: false, strength: "500mg" }],
  pack_sizes: ["1 tablet"],
  manufacturer: null,
  therapeutic_category: "anti-diabetes",
  regulatory_flags: [],
  source,
  source_text: "Metformin | Tablet | 500mg",
  source_date: "2026-03-31",
};

export const item = (overrides: Partial<RxItem> = {}): RxItem => ({
  id: "item-1",
  position: 0,
  page: 0,
  source_text: "Tab Metformin 500 mg",
  bbox: [10, 10, 100, 40],
  fields: {
    name: { value: "Metformin", state: "visible" },
    strength: { value: "500 mg", state: "visible" },
    form: { value: "Tab", state: "visible" },
    frequency: { value: null, state: "unknown" },
    duration: { value: null, state: "unclear" },
  },
  ocr_quality: 0.9,
  match_quality: 0.95,
  confidence_level: "uncalibrated",
  status: "needs_verification",
  requires_lasa_review: false,
  verified_medicine_id: null,
  verified_by_type: null,
  candidates: [
    {
      medicine,
      rank: 1,
      score: 0.95,
      reasons: ["All active ingredients match exactly."],
      is_lasa: false,
    },
  ],
  events: [],
  ...overrides,
});

export const prescription = (overrides: Partial<Prescription> = {}): Prescription => ({
  id: "rx-1",
  source_type: "manual",
  status: "needs_verification",
  page_count: 0,
  created_at: "2026-11-05T10:00:00Z",
  retention_until: "2026-11-12T10:00:00Z",
  emergency: { detected: false },
  items: [item()],
  shares: [],
  ...overrides,
});
