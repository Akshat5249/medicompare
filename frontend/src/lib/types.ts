export interface Source {
  code: string;
  name: string;
  owner: string;
  url: string;
  is_demo: boolean;
}

export interface MedicineSummary {
  id: number;
  display_name: string;
  generic_name: string;
  brand: string | null;
  dosage_form: string;
  release_type: string;
  route: string;
  is_demo: boolean;
}

export interface RegulatoryFlag {
  flag_type: string;
  description: string;
  source_name: string;
  source_url: string | null;
  source_date: string;
  is_demo: boolean;
}

export interface MedicineDetail extends MedicineSummary {
  ingredients: {
    name: string;
    salt_form: string | null;
    salt_form_stated: boolean;
    strength: string;
  }[];
  pack_sizes: string[];
  manufacturer: string | null;
  therapeutic_category: string | null;
  regulatory_flags: RegulatoryFlag[];
  source: Source;
  source_text: string | null;
  source_date: string | null;
}

export interface Price {
  price_type: "ceiling" | "notified_retail" | "catalogue" | "mrp" | "indicative";
  price_type_label: string;
  amount_inr: string;
  pack: string;
  pack_unit: string;
  per_unit_inr: string;
  source: Source;
  observed_at: string;
  last_updated: string;
  is_stale: boolean;
  is_demo: boolean;
}

export interface SearchResult {
  medicine: MedicineSummary;
  match_type: string;
  reason: string;
}

export interface Emergency {
  detected: boolean;
  number?: string;
  message?: string;
}

export interface SearchResponse {
  query: string;
  emergency: Emergency;
  exact_matches: SearchResult[];
  possible_matches: SearchResult[];
}

export interface JaProduct {
  drug_code: string;
  generic_name: string;
  group_name: string | null;
  unit_size: string;
  mrp_inr: string;
  price_type_label: string;
  source: Source;
  last_updated: string;
  is_stale: boolean;
  is_demo: boolean;
  medicine_id: number | null;
}

export interface Kendra {
  kendra_code: string;
  name: string;
  address: string;
  district: string;
  state: string;
  pin_code: string;
  source: Source;
  last_updated: string;
  is_demo: boolean;
  distance_km?: number;
}

export interface EquivalentOption {
  medicine: MedicineSummary;
  prices: Price[];
  differences: { code: string; detail: string }[];
  savings: { statement: string; price_type: string }[];
  regulatory_flags: RegulatoryFlag[];
}

export interface NotEquivalentOption {
  medicine: MedicineSummary;
  reasons: string[];
  difference_codes: string[];
  regulatory_flags: RegulatoryFlag[];
}

export interface OptionsResponse {
  reference: { medicine: MedicineDetail; prices: Price[] };
  equivalents: EquivalentOption[];
  not_equivalent: NotEquivalentOption[];
  jan_aushadhi: JaProduct[];
  disclaimer: string;
}

export type FieldName = "name" | "strength" | "form" | "frequency" | "duration";

export interface Candidate {
  medicine: MedicineSummary;
  rank: number;
  score: number;
  reasons: string[];
  is_lasa: boolean;
}

export interface VerificationEvent {
  action: string;
  verifier_type: "user" | "pharmacist";
  diff: Record<string, unknown>;
  note: string | null;
  created_at: string;
}

export interface RxItem {
  id: string;
  position: number;
  page: number;
  source_text: string;
  bbox: number[] | null;
  fields: Record<FieldName, { value: string | null; state: "visible" | "unclear" | "unknown" }>;
  ocr_quality: number | null;
  match_quality: number | null;
  confidence_level: "uncalibrated" | "no_match" | "low_confidence" | "suggested";
  status: "needs_verification" | "verified" | "rejected" | "unresolved";
  requires_lasa_review: boolean;
  verified_medicine_id: number | null;
  verified_by_type: "user" | "pharmacist" | null;
  candidates: Candidate[];
  events: VerificationEvent[];
}

export interface Prescription {
  id: string;
  source_type: "upload" | "manual";
  status: "received" | "processing" | "needs_verification" | "verified" | "unreadable" | "failed";
  page_count: number;
  created_at: string;
  retention_until: string | null;
  emergency: Emergency;
  items: RxItem[];
  shares: { pharmacist_id: string; status: string; note: string | null }[];
}

export interface SessionUser {
  id: string;
  email: string | null;
  role: "user" | "pharmacist" | "admin";
  display_name: string | null;
  is_guest: boolean;
  pharmacist_status: "pending" | "approved" | "rejected" | null;
}

export interface SessionPayload {
  user: SessionUser | null;
  csrf_token: string | null;
}

export interface SummaryEntry {
  verified_by: string;
  medicine: MedicineDetail;
  prices: Price[];
  options: EquivalentOption[];
  jan_aushadhi: JaProduct[];
}

export interface Summary {
  generated_at: string;
  label: string | null;
  medicines: SummaryEntry[];
  items_not_included: number;
  statement: string;
  notice: string;
  contains_demo_data: boolean;
}
