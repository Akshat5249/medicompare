"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useRouter } from "@/i18n/navigation";
import { ApiError, api, compressForUpload, post, setCsrfToken, useApi } from "@/lib/api";
import type {
  Candidate,
  FieldName,
  OptionsResponse,
  Prescription,
  RxItem,
  SessionPayload,
  Summary,
} from "@/lib/types";
import { MedicineFacts, OptionsView } from "./catalogue";
import { useApp } from "./shell";
import {
  Button,
  Card,
  DemoBadge,
  Empty,
  ErrorState,
  Field,
  Flags,
  JaProductRow,
  Loading,
  PriceList,
  Warning,
  buttonClass,
} from "./ui";

const FIELDS: FieldName[] = ["name", "strength", "form", "frequency", "duration"];

/** Prescriptions work without an account: a guest session is created on first use. */
async function ensureSession(hasUser: boolean, refresh: () => void): Promise<void> {
  if (hasUser) return;
  const session = await post<SessionPayload>("/auth/guest");
  setCsrfToken(session.csrf_token);
  refresh();
}

export function PrescriptionList() {
  const t = useTranslations("rx");
  const { user, sessionLoading } = useApp();
  const state = useApi<{ prescriptions: Prescription[] }>(user ? "/prescriptions" : null);
  const remove = async (id: string) => {
    if (!window.confirm(t("deleteConfirm"))) return;
    await api(`/prescriptions/${id}`, { method: "DELETE" });
    state.reload();
  };
  if (sessionLoading || state.loading) return <Loading />;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">{t("title")}</h1>
      <Link href="/prescriptions/new" className={buttonClass()}>
        {t("new")}
      </Link>
      {state.error ? <ErrorState error={state.error} onRetry={state.reload} /> : null}
      {!state.data?.prescriptions.length ? <Empty>{t("none")}</Empty> : null}
      <ul className="space-y-3">
        {state.data?.prescriptions.map((prescription) => (
          <li key={prescription.id}>
            <Card className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="font-medium">
                  {t("statusLabel")}: {t(`status.${prescription.status}`)}
                </p>
                <p className="text-sm text-slate-700">{prescription.created_at.slice(0, 10)}</p>
                {prescription.retention_until ? (
                  <p className="text-sm text-slate-700">
                    {t("retention", { date: prescription.retention_until.slice(0, 10) })}
                  </p>
                ) : null}
              </div>
              <div className="flex gap-2">
                <Link
                  href={`/prescriptions/${prescription.id}`}
                  className={buttonClass("secondary")}
                >
                  {t("open")}
                </Link>
                <Button variant="danger" onClick={() => void remove(prescription.id)}>
                  {t("delete")}
                </Button>
              </div>
            </Card>
          </li>
        ))}
      </ul>
    </div>
  );
}

interface ManualRow {
  name: string;
  strength: string;
  form: string;
  frequency: string;
  duration: string;
}
const EMPTY_ROW: ManualRow = { name: "", strength: "", form: "", frequency: "", duration: "" };

export function ManualEntry() {
  const t = useTranslations("rx");
  const router = useRouter();
  const { user, refreshSession, raiseEmergency } = useApp();
  const [rows, setRows] = useState<ManualRow[]>([{ ...EMPTY_ROW }]);
  const [error, setError] = useState<ApiError | null>(null);
  const update = (index: number, key: keyof ManualRow, value: string) =>
    setRows((current) =>
      current.map((row, position) => (position === index ? { ...row, [key]: value } : row)),
    );
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    const filled = rows.filter((row) => Object.values(row).some((value) => value.trim()));
    if (filled.length === 0) return;
    try {
      await ensureSession(Boolean(user), refreshSession);
      const created = await post<Prescription>("/prescriptions/manual", { items: filled });
      if (created.emergency.detected) raiseEmergency();
      router.push(`/prescriptions/${created.id}`);
    } catch (failure) {
      setError(failure instanceof ApiError ? failure : new ApiError(0, "network", "error"));
    }
  };
  return (
    <form onSubmit={submit} className="space-y-4">
      <p>{t("manualHelp")}</p>
      {rows.map((row, index) => (
        <fieldset key={index} className="rounded-md border border-slate-400 p-3">
          <legend className="px-1 font-medium">{t("itemHeading", { number: index + 1 })}</legend>
          <div className="grid gap-3 sm:grid-cols-2">
            {(Object.keys(EMPTY_ROW) as (keyof ManualRow)[]).map((key) => (
              <Field
                key={key}
                id={`${key}-${index}`}
                label={t(key)}
                value={row[key]}
                maxLength={key === "name" ? 255 : 80}
                onChange={(event) => update(index, key, event.target.value)}
              />
            ))}
          </div>
          {rows.length > 1 ? (
            <Button
              variant="secondary"
              className="mt-3"
              onClick={() =>
                setRows((current) => current.filter((_, position) => position !== index))
              }
            >
              {t("removeRow")}
            </Button>
          ) : null}
        </fieldset>
      ))}
      {error ? <ErrorState error={error} /> : null}
      <div className="flex flex-wrap gap-2">
        <Button
          variant="secondary"
          onClick={() => setRows((current) => [...current, { ...EMPTY_ROW }])}
        >
          {t("addRow")}
        </Button>
        <button type="submit" className={buttonClass()}>
          {t("submit")}
        </button>
      </div>
    </form>
  );
}

interface ConsentNotice {
  what_is_processed: string;
  engine: string;
  engine_location: string;
  storage: string;
  retention_days: number;
  your_controls: string;
}

export function UploadForm() {
  const t = useTranslations("rx");
  const router = useRouter();
  const { user, refreshSession } = useApp();
  const notice = useApi<ConsentNotice>("/prescriptions/consent-notice");
  const [file, setFile] = useState<File | null>(null);
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!file || !agreed) return;
    setBusy(true);
    setError(null);
    try {
      await ensureSession(Boolean(user), refreshSession);
      const form = new FormData();
      form.append("file", await compressForUpload(file));
      form.append("consent", "true");
      const created = await api<Prescription>("/prescriptions/upload", {
        method: "POST",
        body: form,
      });
      router.push(`/prescriptions/${created.id}`);
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : t("failed"));
      setBusy(false);
    }
  };
  if (notice.loading) return <Loading />;
  if (notice.error) return <ErrorState error={notice.error} onRetry={notice.reload} />;
  const data = notice.data;
  if (!data) return null;
  return (
    <form onSubmit={submit} className="space-y-4">
      <Card>
        <h3 className="mb-2 font-semibold">{t("consentTitle")}</h3>
        <ul className="list-disc space-y-1 ps-5">
          <li>{t("consentWhat", { value: data.what_is_processed })}</li>
          <li>{t("consentEngine", { value: data.engine })}</li>
          <li>{t("consentWhere", { value: data.engine_location })}</li>
          <li>{t("consentStorage", { value: data.storage })}</li>
          <li>{t("consentRetention", { days: data.retention_days })}</li>
          <li>{t("consentControls", { value: data.your_controls })}</li>
        </ul>
        <p className="mt-2 text-sm">{t("realDataWarning")}</p>
        <label className="mt-3 flex min-h-11 items-center gap-2 font-medium">
          <input
            type="checkbox"
            className="h-5 w-5"
            checked={agreed}
            onChange={(event) => setAgreed(event.target.checked)}
          />
          {t("consentAgree")}
        </label>
      </Card>
      <div className="flex flex-col gap-1">
        <label htmlFor="rx-file" className="font-medium">
          {t("chooseFile")}
        </label>
        <input
          id="rx-file"
          type="file"
          accept="image/jpeg,image/png,application/pdf"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          className="min-h-11"
        />
      </div>
      {error ? (
        <p role="alert" className="rounded-md border border-red-800 bg-red-50 p-3 text-red-900">
          {error}
        </p>
      ) : null}
      <button type="submit" disabled={!file || !agreed || busy} className={buttonClass()}>
        {busy ? t("uploading") : t("upload")}
      </button>
    </form>
  );
}

export function NewPrescription() {
  const t = useTranslations("rx");
  const [mode, setMode] = useState<"manual" | "upload">("manual");
  const tab = (value: "manual" | "upload", label: string) => (
    <button
      type="button"
      aria-pressed={mode === value}
      onClick={() => setMode(value)}
      className={buttonClass(mode === value ? "primary" : "secondary")}
    >
      {label}
    </button>
  );
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">{t("chooseTitle")}</h1>
      <div className="flex flex-wrap gap-2">
        {tab("manual", t("manualTab"))}
        {tab("upload", t("uploadTab"))}
      </div>
      {mode === "manual" ? <ManualEntry /> : <UploadForm />}
    </div>
  );
}

function FieldValue({ item, field }: { item: RxItem; field: FieldName }) {
  const t = useTranslations("rx");
  const { value, state } = item.fields[field];
  const shown = state === "visible" ? value : state === "unclear" ? t("unclear") : t("unknown");
  return (
    <div className={state === "visible" ? "" : "rounded bg-amber-50"} data-state={state}>
      <dt className="text-sm font-medium text-slate-700">{t(field)}</dt>
      <dd className={state === "visible" ? "font-medium" : "font-medium text-amber-950"}>
        {shown}
      </dd>
    </div>
  );
}

function CorrectionForm({
  item,
  onSave,
  onCancel,
}: {
  item: RxItem;
  onSave: (changes: Record<string, string>) => Promise<void>;
  onCancel: () => void;
}) {
  const t = useTranslations("rx");
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(FIELDS.map((field) => [field, item.fields[field].value ?? ""])),
  );
  return (
    <form
      className="mt-3 grid gap-3 sm:grid-cols-2"
      onSubmit={(event) => {
        event.preventDefault();
        void onSave(values);
      }}
    >
      {FIELDS.map((field) => (
        <Field
          key={field}
          id={`fix-${item.id}-${field}`}
          label={t(field)}
          value={values[field]}
          onChange={(event) => setValues({ ...values, [field]: event.target.value })}
        />
      ))}
      <div className="flex gap-2 sm:col-span-2">
        <button type="submit" className={buttonClass()}>
          {t("saveCorrection")}
        </button>
        <Button variant="secondary" onClick={onCancel}>
          {t("cancel")}
        </Button>
      </div>
    </form>
  );
}

function CandidateRow({
  candidate,
  disabled,
  onConfirm,
}: {
  candidate: Candidate;
  disabled: boolean;
  onConfirm: () => void;
}) {
  const t = useTranslations("rx");
  return (
    <li className="rounded-md border border-slate-300 p-3">
      <p className="font-semibold">
        {candidate.medicine.display_name}
        <DemoBadge show={candidate.medicine.is_demo} />
      </p>
      <p className="text-sm">
        {candidate.medicine.dosage_form} · {candidate.medicine.release_type}
      </p>
      <p className="text-sm text-slate-700">
        {t("matchQuality", { value: Math.round(candidate.score * 100) })}
      </p>
      <ul className="my-1 list-disc ps-5 text-sm text-slate-800">
        {candidate.reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
      <Button variant="secondary" disabled={disabled} onClick={onConfirm}>
        {t("confirm")}
      </Button>
    </li>
  );
}

function ItemCard({
  item,
  number,
  basePath,
  viewerType,
  prescriptionId,
  onChanged,
}: {
  item: RxItem;
  number: number;
  basePath: string;
  viewerType: "user" | "pharmacist";
  prescriptionId: string;
  onChanged: () => void;
}) {
  const t = useTranslations("rx");
  const [editing, setEditing] = useState(false);
  const [lasaAck, setLasaAck] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const run = async (action: () => Promise<unknown>) => {
    setError(null);
    try {
      await action();
      setEditing(false);
      onChanged();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure : new ApiError(0, "network", "error"));
    }
  };
  const itemPath = `${basePath}/items/${item.id}`;
  const needsLasa = item.requires_lasa_review && !lasaAck;
  return (
    <li>
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-lg font-semibold">{t("itemHeading", { number })}</h3>
          <span
            className="rounded border border-slate-500 px-2 py-0.5 text-sm"
            data-testid="item-status"
          >
            {t(`statusItem.${item.status}`)}
          </span>
        </div>
        {item.source_text ? (
          <p className="my-1 text-sm text-slate-700">
            {t("readAs")}: <q>{item.source_text}</q>
          </p>
        ) : null}
        <dl className="my-2 grid grid-cols-2 gap-2 sm:grid-cols-5">
          {FIELDS.map((field) => (
            <FieldValue key={field} item={item} field={field} />
          ))}
        </dl>
        {item.ocr_quality !== null ? (
          <p className="text-sm text-slate-700">
            {t("ocrQuality", { value: Math.round(item.ocr_quality * 100) })}
          </p>
        ) : null}
        {item.status === "needs_verification" ? (
          <p className="text-sm font-medium text-slate-900">
            {t(`level.${item.confidence_level}`)}
          </p>
        ) : null}
        {item.status === "verified" ? (
          <p
            className="mt-2 rounded-md border border-slate-500 bg-slate-100 p-2 font-medium"
            data-testid="verified-by"
          >
            {item.verified_by_type === "pharmacist"
              ? t("verifiedByPharmacist")
              : t("verifiedByUser")}
          </p>
        ) : null}
        {item.status === "unresolved" ? <Warning>{t("unresolvedHelp")}</Warning> : null}
        {item.status === "needs_verification" ? (
          <div className="mt-3 space-y-3">
            <h4 className="font-semibold">{t("candidates")}</h4>
            {item.candidates.length === 0 ? <Warning>{t("noCandidates")}</Warning> : null}
            {item.requires_lasa_review ? (
              <div className="rounded-md border-2 border-amber-800 bg-amber-50 p-3 text-amber-950">
                <p className="font-semibold">{t("lasaWarning")}</p>
                <label className="mt-2 flex min-h-11 items-center gap-2">
                  <input
                    type="checkbox"
                    className="h-5 w-5"
                    checked={lasaAck}
                    onChange={(event) => setLasaAck(event.target.checked)}
                  />
                  {t("lasaAck")}
                </label>
              </div>
            ) : null}
            <ul className="space-y-2">
              {item.candidates.map((candidate) => (
                <CandidateRow
                  key={candidate.medicine.id}
                  candidate={candidate}
                  disabled={needsLasa}
                  onConfirm={() =>
                    void run(() =>
                      post(`${itemPath}/verify`, {
                        medicine_id: candidate.medicine.id,
                        lasa_acknowledged: lasaAck,
                        note: note || undefined,
                      }),
                    )
                  }
                />
              ))}
            </ul>
            {viewerType === "pharmacist" ? (
              <Field
                id={`note-${item.id}`}
                label={t("pharmacistNote", { note: "" })}
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
            ) : null}
          </div>
        ) : null}
        {error ? (
          <p
            role="alert"
            className="mt-2 rounded-md border border-red-800 bg-red-50 p-2 text-red-900"
          >
            {error.message}
          </p>
        ) : null}
        <div className="mt-3 flex flex-wrap gap-2">
          {item.status === "verified" && viewerType === "user" ? (
            <Link
              href={`/prescriptions/${prescriptionId}/items/${item.id}`}
              className={buttonClass()}
            >
              {t("viewPrices")}
            </Link>
          ) : null}
          <Button variant="secondary" onClick={() => setEditing((value) => !value)}>
            {t("correct")}
          </Button>
          {item.status === "needs_verification" && viewerType === "user" ? (
            <Button
              variant="secondary"
              onClick={() => void run(() => post(`${itemPath}/reject`, {}))}
            >
              {t("notOnRx")}
            </Button>
          ) : null}
          {item.status === "needs_verification" ? (
            <Button
              variant="secondary"
              onClick={() =>
                void run(() => post(`${itemPath}/unresolved`, { note: note || undefined }))
              }
            >
              {t("cantConfirm")}
            </Button>
          ) : null}
        </div>
        {editing ? (
          <CorrectionForm
            item={item}
            onCancel={() => setEditing(false)}
            onSave={(changes) =>
              run(() => api(itemPath, { method: "PATCH", body: JSON.stringify(changes) }))
            }
          />
        ) : null}
        {item.events.length > 0 ? (
          <details className="mt-3 text-sm">
            <summary className="cursor-pointer">{t("history")}</summary>
            <ul className="mt-1 list-disc ps-5">
              {item.events.map((event) => (
                <li key={`${event.created_at}-${event.action}`}>
                  {event.created_at.slice(0, 16)}: {event.action} ({event.verifier_type})
                  {event.note ? `: ${event.note}` : ""}
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </Card>
    </li>
  );
}

function PageImages({
  prescription,
  pagePath,
}: {
  prescription: Prescription;
  pagePath: (page: number) => string;
}) {
  const t = useTranslations("rx");
  const [sizes, setSizes] = useState<Record<number, { width: number; height: number }>>({});
  if (prescription.page_count === 0) return null;
  return (
    <section aria-labelledby="original-heading" className="lg:sticky lg:top-4 lg:self-start">
      <h2 id="original-heading" className="mb-2 text-lg font-semibold">
        {t("original")}
      </h2>
      {Array.from({ length: prescription.page_count }, (_, page) => {
        const size = sizes[page];
        return (
          <div key={page} className="relative mb-3 border border-slate-400">
            {/* eslint-disable-next-line @next/next/no-img-element -- private, authenticated bytes */}
            <img
              src={`/api/v1${pagePath(page)}`}
              alt={`${t("original")} ${page + 1}`}
              className="block h-auto w-full"
              onLoad={(event) =>
                setSizes((current) => ({
                  ...current,
                  [page]: {
                    width: event.currentTarget.naturalWidth,
                    height: event.currentTarget.naturalHeight,
                  },
                }))
              }
            />
            {size
              ? prescription.items
                  .filter(
                    (item) =>
                      item.page === page &&
                      item.bbox &&
                      (item.fields.name.state !== "visible" ||
                        (item.ocr_quality !== null && item.ocr_quality < 0.7)),
                  )
                  .map((item) => {
                    const [left, top, right, bottom] = item.bbox as number[];
                    return (
                      <span
                        key={item.id}
                        aria-hidden="true"
                        data-testid="uncertain-span"
                        className="absolute border-2 border-amber-600 bg-amber-300/30"
                        style={{
                          left: `${(left / size.width) * 100}%`,
                          top: `${(top / size.height) * 100}%`,
                          width: `${((right - left) / size.width) * 100}%`,
                          height: `${((bottom - top) / size.height) * 100}%`,
                        }}
                      />
                    );
                  })
              : null}
          </div>
        );
      })}
    </section>
  );
}

function SharePanel({
  prescription,
  onChanged,
}: {
  prescription: Prescription;
  onChanged: () => void;
}) {
  const t = useTranslations("rx");
  const pharmacists = useApi<{
    pharmacists: {
      id: string;
      display_name: string;
      state_council: string;
      registration_label: string;
    }[];
  }>("/pharmacists");
  const [choice, setChoice] = useState("");
  const list = pharmacists.data?.pharmacists ?? [];
  return (
    <Card>
      <h2 className="text-lg font-semibold">{t("shareTitle")}</h2>
      <p className="mb-2">{t("shareHelp")}</p>
      {prescription.shares.map((share) => (
        <div key={share.pharmacist_id} className="mb-2 rounded-md bg-slate-100 p-2">
          <p>{t("sharedWith", { status: share.status })}</p>
          {share.note ? <p>{t("pharmacistNote", { note: share.note })}</p> : null}
          <Button
            variant="secondary"
            className="mt-2"
            onClick={() =>
              void api(`/prescriptions/${prescription.id}/shares/${share.pharmacist_id}`, {
                method: "DELETE",
              }).then(onChanged)
            }
          >
            {t("shareRevoke")}
          </Button>
        </div>
      ))}
      {pharmacists.loading ? <Loading /> : null}
      {!pharmacists.loading && list.length === 0 ? <Empty>{t("shareNone")}</Empty> : null}
      {list.length > 0 ? (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <div className="flex flex-col gap-1">
            <label htmlFor="pharmacist-select" className="font-medium">
              {t("sharePick")}
            </label>
            <select
              id="pharmacist-select"
              className="min-h-11 rounded-md border border-slate-500 bg-white px-2"
              value={choice}
              onChange={(event) => setChoice(event.target.value)}
            >
              <option value="">—</option>
              {list.map((pharmacist) => (
                <option key={pharmacist.id} value={pharmacist.id}>
                  {pharmacist.display_name} ({pharmacist.state_council})
                </option>
              ))}
            </select>
            <p className="text-sm text-slate-700">{t("selfDeclared")}</p>
          </div>
          <Button
            disabled={!choice}
            onClick={() =>
              void post(`/prescriptions/${prescription.id}/shares`, { pharmacist_id: choice }).then(
                onChanged,
              )
            }
          >
            {t("shareButton")}
          </Button>
        </div>
      ) : null}
    </Card>
  );
}

export function VerificationPage({ id }: { id: string }) {
  const t = useTranslations("rx");
  const { raiseEmergency } = useApp();
  const state = useApi<Prescription>(`/prescriptions/${id}`);
  const { reload } = state;
  const status = state.data?.status;
  useEffect(() => {
    if (status !== "received" && status !== "processing") return;
    const timer = window.setInterval(reload, 2500);
    return () => window.clearInterval(timer);
  }, [status, reload]);
  const emergency = state.data?.emergency.detected;
  useEffect(() => {
    if (emergency) raiseEmergency();
  }, [emergency, raiseEmergency]);
  if (!state.data && state.loading) return <Loading />;
  if (state.error) return <ErrorState error={state.error} onRetry={reload} />;
  const prescription = state.data;
  if (!prescription) return null;
  if (prescription.status === "received" || prescription.status === "processing") {
    return <Loading label={t("processing")} />;
  }
  if (prescription.status === "failed" || prescription.status === "unreadable") {
    return (
      <div className="space-y-3">
        <Warning>{prescription.status === "failed" ? t("failed") : t("unreadable")}</Warning>
        <Link href="/prescriptions/new" className={buttonClass()}>
          {t("typeInstead")}
        </Link>
      </div>
    );
  }
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">{t("verifyTitle")}</h1>
      <p>{t("verifyHelp")}</p>
      <div className={prescription.page_count ? "grid gap-4 lg:grid-cols-2" : ""}>
        <PageImages
          prescription={prescription}
          pagePath={(page) => `/prescriptions/${id}/pages/${page}`}
        />
        <ul className="space-y-4">
          {prescription.items.map((item, index) => (
            <ItemCard
              key={item.id}
              item={item}
              number={index + 1}
              basePath={`/prescriptions/${id}`}
              viewerType="user"
              prescriptionId={id}
              onChanged={reload}
            />
          ))}
        </ul>
      </div>
      <Link href={`/prescriptions/${id}/summary`} className={buttonClass("secondary")}>
        {t("summary")}
      </Link>
      <SharePanel prescription={prescription} onChanged={reload} />
    </div>
  );
}

export function ItemComparison({ id, itemId }: { id: string; itemId: string }) {
  const t = useTranslations("rx");
  const prices = useTranslations("prices");
  const state = useApi<OptionsResponse>(`/prescriptions/${id}/items/${itemId}/options`);
  const back = (
    <Link href={`/prescriptions/${id}`} className={buttonClass("secondary")}>
      {t("backToCheck")}
    </Link>
  );
  if (state.loading) return <Loading />;
  if (state.error?.code === "item_not_verified") {
    return (
      <div className="space-y-3" data-testid="gate-blocked">
        <Warning>{t("blocked")}</Warning>
        {back}
      </div>
    );
  }
  if (state.error) return <ErrorState error={state.error} onRetry={state.reload} />;
  if (!state.data) return null;
  const { medicine } = state.data.reference;
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">
        {t("comparisonTitle")}: {medicine.display_name}
        <DemoBadge show={medicine.is_demo} />
      </h1>
      {back}
      <Card>
        <MedicineFacts medicine={medicine} />
      </Card>
      <Card>
        <h2 className="text-xl font-semibold">{prices("title")}</h2>
        <PriceList prices={state.data.reference.prices} />
      </Card>
      <OptionsView data={state.data} />
    </div>
  );
}

export function SummaryView({ summary }: { summary: Summary }) {
  const t = useTranslations("summary");
  return (
    <div className="space-y-4">
      {summary.label ? <p className="font-medium">{summary.label}</p> : null}
      <p className="rounded-md border-2 border-indigo-900 bg-indigo-50 p-3 text-lg font-semibold text-indigo-950">
        {t("statement")}
      </p>
      <p>{t("onlyVerified")}</p>
      {summary.items_not_included > 0 ? (
        <Warning>{t("notIncluded", { count: summary.items_not_included })}</Warning>
      ) : null}
      {summary.medicines.length === 0 ? <Empty>{t("none")}</Empty> : null}
      {summary.medicines.map((entry) => (
        <Card key={entry.medicine.id}>
          <h2 className="text-xl font-semibold">
            {entry.medicine.display_name}
            <DemoBadge show={entry.medicine.is_demo} />
          </h2>
          <p className="text-sm text-slate-700">{t("verifiedBy", { by: entry.verified_by })}</p>
          <Flags flags={entry.medicine.regulatory_flags} />
          <PriceList prices={entry.prices} />
          {entry.options.map((option) => (
            <div key={option.medicine.id} className="mt-3 border-t border-slate-300 pt-2">
              <h3 className="font-semibold">
                {option.medicine.display_name}
                <DemoBadge show={option.medicine.is_demo} />
              </h3>
              {option.differences.map((difference) => (
                <p key={difference.detail}>{difference.detail}</p>
              ))}
              <PriceList prices={option.prices} />
            </div>
          ))}
          {entry.jan_aushadhi.length > 0 ? (
            <ul className="mt-3 border-t border-slate-300 pt-2">
              {entry.jan_aushadhi.map((product) => (
                <JaProductRow key={product.drug_code} product={product} />
              ))}
            </ul>
          ) : null}
        </Card>
      ))}
    </div>
  );
}

export function SummaryPage({ id }: { id: string }) {
  const t = useTranslations("summary");
  const state = useApi<Summary>(`/prescriptions/${id}/summary`);
  const [label, setLabel] = useState("");
  const [link, setLink] = useState<{ url: string; expires: string } | null>(null);
  const [copied, setCopied] = useState(false);
  if (state.loading) return <Loading />;
  if (state.error) return <ErrorState error={state.error} onRetry={state.reload} />;
  if (!state.data) return null;
  const createLink = async () => {
    const created = await post<{ token: string; expires_at: string }>(
      `/prescriptions/${id}/share-links`,
      {
        label: label || undefined,
      },
    );
    const locale = window.location.pathname.split("/")[1];
    setLink({
      url: `${window.location.origin}/${locale}/shared/${created.token}`,
      expires: created.expires_at.slice(0, 10),
    });
  };
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">{t("title")}</h1>
      <SummaryView summary={state.data} />
      <div className="flex flex-wrap gap-2 print:hidden">
        <a href={`/api/v1/prescriptions/${id}/summary.pdf`} className={buttonClass()}>
          {t("pdf")}
        </a>
        <Button variant="secondary" onClick={() => window.print()}>
          {t("print")}
        </Button>
      </div>
      {state.data.medicines.length > 0 ? (
        <Card className="print:hidden">
          <Field
            id="link-label"
            label={t("labelField")}
            value={label}
            maxLength={120}
            onChange={(event) => setLabel(event.target.value)}
          />
          <Button variant="secondary" className="mt-3" onClick={() => void createLink()}>
            {t("createLink")}
          </Button>
          {link ? (
            <div className="mt-3">
              <p className="font-medium">{t("linkReady", { date: link.expires })}</p>
              <p className="break-all" data-testid="share-url">
                {link.url}
              </p>
              <Button
                variant="secondary"
                className="mt-2"
                onClick={() =>
                  void navigator.clipboard.writeText(link.url).then(() => setCopied(true))
                }
              >
                {copied ? t("copied") : t("copy")}
              </Button>
            </div>
          ) : null}
        </Card>
      ) : null}
    </div>
  );
}

export function SharedPage({ token }: { token: string }) {
  const t = useTranslations("summary");
  const state = useApi<Summary>(`/shared/${token}`);
  if (state.loading) return <Loading />;
  if (state.error?.status === 410) return <Warning>{t("expired")}</Warning>;
  if (state.error) return <ErrorState error={state.error} />;
  if (!state.data) return null;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">{t("title")}</h1>
      <SummaryView summary={state.data} />
      <a href={`/api/v1/shared/${token}/pdf`} className={`${buttonClass()} print:hidden`}>
        {t("pdf")}
      </a>
    </div>
  );
}

export function PharmacistQueue() {
  const t = useTranslations("pharmacist");
  const auth = useTranslations("auth");
  const state = useApi<{
    queue: {
      prescription_id: string;
      open_items: number;
      total_items: number;
      shared_at: string;
    }[];
  }>("/pharmacist/queue");
  if (state.loading) return <Loading />;
  if (state.error?.code === "forbidden" || state.error?.code === "pharmacist_not_approved") {
    return <Warning>{auth("pending")}</Warning>;
  }
  if (state.error) return <ErrorState error={state.error} onRetry={state.reload} />;
  const queue = state.data?.queue ?? [];
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">{t("title")}</h1>
      {queue.length === 0 ? <Empty>{t("empty")}</Empty> : null}
      <ul className="space-y-3">
        {queue.map((row) => (
          <li key={row.prescription_id}>
            <Card className="flex flex-wrap items-center justify-between gap-2">
              <p>
                {t("openItems", { open: row.open_items, total: row.total_items })} ·{" "}
                {row.shared_at.slice(0, 10)}
              </p>
              <Link
                href={`/pharmacist/${row.prescription_id}`}
                className={buttonClass("secondary")}
              >
                {t("open")}
              </Link>
            </Card>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function PharmacistReview({ id }: { id: string }) {
  const t = useTranslations("pharmacist");
  const state = useApi<Prescription>(`/pharmacist/prescriptions/${id}`);
  const [note, setNote] = useState("");
  const [done, setDone] = useState(false);
  if (!state.data && state.loading) return <Loading />;
  if (state.error) return <ErrorState error={state.error} onRetry={state.reload} />;
  const prescription = state.data;
  if (!prescription) return null;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">{t("reviewTitle")}</h1>
      <p>{t("scope")}</p>
      <div className={prescription.page_count ? "grid gap-4 lg:grid-cols-2" : ""}>
        <PageImages
          prescription={prescription}
          pagePath={(page) => `/pharmacist/prescriptions/${id}/pages/${page}`}
        />
        <ul className="space-y-4">
          {prescription.items.map((item, index) => (
            <ItemCard
              key={item.id}
              item={item}
              number={index + 1}
              basePath={`/pharmacist/prescriptions/${id}`}
              viewerType="pharmacist"
              prescriptionId={id}
              onChanged={state.reload}
            />
          ))}
        </ul>
      </div>
      <Card>
        <Field
          id="review-note"
          label={t("note")}
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />
        <Button
          className="mt-3"
          disabled={done}
          onClick={() =>
            void post(`/pharmacist/prescriptions/${id}/complete`, { note: note || undefined }).then(
              () => setDone(true),
            )
          }
        >
          {done ? t("completed") : t("complete")}
        </Button>
      </Card>
    </div>
  );
}
