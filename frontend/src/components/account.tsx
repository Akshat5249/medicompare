"use client";

import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { Link, useRouter } from "@/i18n/navigation";
import { ApiError, api, post, setCsrfToken, useApi } from "@/lib/api";
import type { MedicineSummary, SessionPayload } from "@/lib/types";
import { useApp } from "./shell";
import {
  Button,
  Card,
  DemoBadge,
  Empty,
  ErrorState,
  Field,
  Loading,
  Warning,
  buttonClass,
} from "./ui";

function authMessage(error: unknown, t: (key: string) => string): string {
  if (error instanceof ApiError) {
    if (error.code === "account_locked") return t("locked");
    if (error.code === "email_taken") return t("taken");
    if (error.code === "invalid_credentials") return t("failed");
    return error.message;
  }
  return t("failed");
}

function useAuthSubmit(path: string) {
  const t = useTranslations("auth");
  const router = useRouter();
  const { refreshSession } = useApp();
  const [error, setError] = useState<string | null>(null);
  const submit = async (body: Record<string, string>, target = "/account") => {
    setError(null);
    try {
      const session = await post<SessionPayload>(path, body);
      setCsrfToken(session.csrf_token);
      refreshSession();
      router.push(target);
    } catch (failure) {
      setError(authMessage(failure, t));
    }
  };
  return { error, submit };
}

function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="rounded-md border border-red-800 bg-red-50 p-3 text-red-900">
      {message}
    </p>
  );
}

export function LoginForm() {
  const t = useTranslations("auth");
  const { error, submit } = useAuthSubmit("/auth/login");
  const guest = useAuthSubmit("/auth/guest");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  return (
    <div className="mx-auto max-w-md space-y-4">
      <h1 className="text-2xl font-bold">{t("signInTitle")}</h1>
      <form
        className="space-y-3"
        onSubmit={(event: FormEvent) => {
          event.preventDefault();
          void submit({ email, password });
        }}
      >
        <Field
          id="email"
          type="email"
          autoComplete="email"
          required
          label={t("email")}
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
        <Field
          id="password"
          type="password"
          autoComplete="current-password"
          required
          label={t("password")}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        <FormError message={error ?? guest.error} />
        <button type="submit" className={buttonClass()}>
          {t("signIn")}
        </button>
      </form>
      <p>
        <Link href="/register" className="text-indigo-900 underline">
          {t("needAccount")}
        </Link>
      </p>
      <p>
        <Link href="/pharmacist/register" className="text-indigo-900 underline">
          {t("pharmacistLink")}
        </Link>
      </p>
      <div>
        <Button variant="secondary" onClick={() => void guest.submit({}, "/prescriptions/new")}>
          {t("guest")}
        </Button>
        <p className="mt-1 text-sm text-slate-700">{t("guestHelp")}</p>
      </div>
    </div>
  );
}

export function RegisterForm({ pharmacist = false }: { pharmacist?: boolean }) {
  const t = useTranslations("auth");
  const { error, submit } = useAuthSubmit(
    pharmacist ? "/auth/register-pharmacist" : "/auth/register",
  );
  const [values, setValues] = useState({
    email: "",
    password: "",
    display_name: "",
    registration_number: "",
    state_council: "",
  });
  const set = (key: keyof typeof values) => (event: React.ChangeEvent<HTMLInputElement>) =>
    setValues({ ...values, [key]: event.target.value });
  return (
    <div className="mx-auto max-w-md space-y-4">
      <h1 className="text-2xl font-bold">
        {pharmacist ? t("pharmacistTitle") : t("registerTitle")}
      </h1>
      <form
        className="space-y-3"
        onSubmit={(event) => {
          event.preventDefault();
          const body: Record<string, string> = { email: values.email, password: values.password };
          if (values.display_name) body.display_name = values.display_name;
          if (pharmacist) {
            body.registration_number = values.registration_number;
            body.state_council = values.state_council;
          }
          void submit(body, pharmacist ? "/pharmacist" : "/account");
        }}
      >
        <Field
          id="reg-email"
          type="email"
          autoComplete="email"
          required
          label={t("email")}
          value={values.email}
          onChange={set("email")}
        />
        <Field
          id="reg-password"
          type="password"
          autoComplete="new-password"
          required
          minLength={10}
          label={t("password")}
          help={t("passwordHelp")}
          value={values.password}
          onChange={set("password")}
        />
        <Field
          id="reg-name"
          autoComplete="name"
          label={t("displayName")}
          value={values.display_name}
          onChange={set("display_name")}
        />
        {pharmacist ? (
          <>
            <Field
              id="reg-number"
              required
              label={t("registration")}
              help={t("registrationHelp")}
              value={values.registration_number}
              onChange={set("registration_number")}
            />
            <Field
              id="reg-council"
              required
              label={t("council")}
              value={values.state_council}
              onChange={set("state_council")}
            />
          </>
        ) : null}
        <FormError message={error} />
        <button type="submit" className={buttonClass()}>
          {t("register")}
        </button>
      </form>
      <p>
        <Link href="/login" className="text-indigo-900 underline">
          {t("haveAccount")}
        </Link>
      </p>
    </div>
  );
}

interface SavedList {
  id: string;
  name: string;
  medicines: MedicineSummary[];
}

export function AccountPage() {
  const t = useTranslations("account");
  const router = useRouter();
  const { user, sessionLoading, refreshSession } = useApp();
  const lists = useApi<{ lists: SavedList[] }>(user && !user.is_guest ? "/lists" : null);
  const [name, setName] = useState("");
  if (sessionLoading) return <Loading />;
  if (!user) return <ErrorState error={new ApiError(401, "unauthenticated", "")} />;
  const signOut = async () => {
    await post("/auth/logout");
    setCsrfToken(null);
    refreshSession();
    router.push("/");
  };
  const deleteAccount = async () => {
    if (!window.confirm(t("deleteConfirm"))) return;
    await api("/me", { method: "DELETE" });
    setCsrfToken(null);
    refreshSession();
    router.push("/");
  };
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">{t("title")}</h1>
      {user.is_guest ? <Warning>{t("guestNotice")}</Warning> : <p>{user.email}</p>}
      {!user.is_guest ? (
        <Card>
          <h2 className="mb-2 text-lg font-semibold">{t("lists")}</h2>
          {lists.data?.lists.length === 0 ? <Empty>{t("noLists")}</Empty> : null}
          <ul className="space-y-2">
            {lists.data?.lists.map((list) => (
              <li key={list.id} className="rounded-md border border-slate-300 p-3">
                <p className="font-medium">{list.name}</p>
                <ul className="list-disc ps-5">
                  {list.medicines.map((medicine) => (
                    <li key={medicine.id}>
                      <Link
                        href={`/medicines/${medicine.id}`}
                        className="text-indigo-900 underline"
                      >
                        {medicine.display_name}
                      </Link>
                      <DemoBadge show={medicine.is_demo} />
                    </li>
                  ))}
                </ul>
                <Button
                  variant="secondary"
                  className="mt-2"
                  onClick={() =>
                    void api(`/lists/${list.id}`, { method: "DELETE" }).then(lists.reload)
                  }
                >
                  {t("deleteList")}
                </Button>
              </li>
            ))}
          </ul>
          <form
            className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-end"
            onSubmit={(event) => {
              event.preventDefault();
              if (name.trim()) {
                void post("/lists", { name }).then(() => {
                  setName("");
                  lists.reload();
                });
              }
            }}
          >
            <Field
              id="list-name"
              label={t("listName")}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
            <button type="submit" className={buttonClass("secondary")}>
              {t("createList")}
            </button>
          </form>
        </Card>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <a
          href="/api/v1/me/export"
          download="medicompare-export.json"
          className={buttonClass("secondary")}
        >
          {t("export")}
        </a>
        <Button variant="secondary" onClick={() => void signOut()}>
          {t("signOut")}
        </Button>
        <Button variant="danger" onClick={() => void deleteAccount()}>
          {t("delete")}
        </Button>
      </div>
    </div>
  );
}

export function SaveToList({ medicineId }: { medicineId: number }) {
  const t = useTranslations("account");
  const { user } = useApp();
  const lists = useApi<{ lists: SavedList[] }>(user && !user.is_guest ? "/lists" : null);
  const [saved, setSaved] = useState(false);
  const first = lists.data?.lists[0];
  if (!first) return null;
  return (
    <Button
      variant="secondary"
      disabled={saved}
      onClick={() =>
        void post(`/lists/${first.id}/items`, { medicine_id: medicineId }).then(() =>
          setSaved(true),
        )
      }
    >
      {saved ? t("saved") : `${t("addToList")}: ${first.name}`}
    </Button>
  );
}

interface SourceRow {
  code: string;
  name: string;
  owner: string;
  is_demo: boolean;
  is_stale: boolean;
  data_as_of: string | null;
  next_update_due: string | null;
  medicines: number;
  prices: number;
}
interface BatchRow {
  id: number;
  source: string;
  is_demo: boolean;
  kind: string;
  status: string;
  file_name: string;
  row_count: number;
  valid_count: number;
  failed_count: number;
}
interface QueueRow {
  id: number;
  batch_id: number;
  batch_status: string;
  row_number: number;
  raw: Record<string, unknown>;
  errors: string[];
}
interface PharmacistRow {
  user_id: string;
  email: string;
  display_name: string | null;
  registration_number: string;
  state_council: string;
  status: string;
}
interface AuditRow {
  id: number;
  actor_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  created_at: string;
}

function QueueItem({ row, onChanged }: { row: QueueRow; onChanged: () => void }) {
  const t = useTranslations("admin");
  const [text, setText] = useState(JSON.stringify(row.raw, null, 1));
  const [message, setMessage] = useState<string | null>(null);
  const open = row.batch_status === "validated";
  return (
    <li className="rounded-md border border-slate-300 p-3">
      <p className="font-medium">
        #{row.batch_id}/{row.row_number}
      </p>
      <p className="text-sm text-red-900">
        {t("errors")}: {row.errors.join("; ")}
      </p>
      {open ? (
        <>
          <label className="mt-2 block text-sm font-medium" htmlFor={`row-${row.id}`}>
            {t("fixRow")}
          </label>
          <textarea
            id={`row-${row.id}`}
            className="min-h-24 w-full rounded-md border border-slate-500 p-2 font-mono text-sm"
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
          {message ? <p role="alert">{message}</p> : null}
          <div className="mt-2 flex gap-2">
            <Button
              variant="secondary"
              onClick={() => {
                let raw: unknown;
                try {
                  raw = JSON.parse(text);
                } catch {
                  setMessage("JSON");
                  return;
                }
                void api(`/admin/review-queue/${row.id}`, {
                  method: "PUT",
                  body: JSON.stringify({ raw }),
                }).then(onChanged);
              }}
            >
              {t("fixRow")}
            </Button>
            <Button
              variant="secondary"
              onClick={() =>
                void api(`/admin/review-queue/${row.id}`, { method: "DELETE" }).then(onChanged)
              }
            >
              {t("dismissRow")}
            </Button>
          </div>
        </>
      ) : (
        <pre className="mt-1 text-xs break-all whitespace-pre-wrap">{JSON.stringify(row.raw)}</pre>
      )}
    </li>
  );
}

export function AdminPage() {
  const t = useTranslations("admin");
  const sources = useApi<{ sources: SourceRow[] }>("/admin/sources");
  const batches = useApi<{ batches: BatchRow[] }>("/admin/imports");
  const queue = useApi<{ rows: QueueRow[] }>("/admin/review-queue");
  const pharmacists = useApi<{ pharmacists: PharmacistRow[] }>("/admin/pharmacists");
  const audit = useApi<{ events: AuditRow[] }>("/admin/audit");
  const [sourceCode, setSourceCode] = useState("");
  const [kind, setKind] = useState("catalogue");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (sources.loading) return <Loading />;
  if (sources.error) return <ErrorState error={sources.error} />;
  const refreshAll = () => {
    sources.reload();
    batches.reload();
    queue.reload();
    audit.reload();
    pharmacists.reload();
  };
  const stage = async (event: FormEvent) => {
    event.preventDefault();
    if (!file || !sourceCode) return;
    setError(null);
    const form = new FormData();
    form.append("file", file);
    form.append("source_code", sourceCode);
    form.append("kind", kind);
    try {
      await api("/admin/imports", { method: "POST", body: form });
      refreshAll();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "error");
    }
  };
  const select = "min-h-11 rounded-md border border-slate-500 bg-white px-2";
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">{t("title")}</h1>
      <section aria-labelledby="fresh-heading">
        <h2 id="fresh-heading" className="mb-2 text-xl font-semibold">
          {t("sources")}
        </h2>
        <ul className="grid gap-3 sm:grid-cols-2">
          {sources.data?.sources.map((source) => (
            <li key={source.code}>
              <Card>
                <p className="font-semibold">
                  {source.name}
                  <DemoBadge show={source.is_demo} />
                </p>
                <p className="text-sm">{source.owner}</p>
                <p className="text-sm">{t("asOf", { date: source.data_as_of ?? "—" })}</p>
                <p
                  className={`mt-1 inline-block rounded border px-2 text-sm ${source.is_stale ? "border-amber-800 bg-amber-50 text-amber-950" : "border-slate-500"}`}
                >
                  {source.is_stale ? t("stale") : t("fresh")}
                </p>
              </Card>
            </li>
          ))}
        </ul>
      </section>
      <section aria-labelledby="imports-heading">
        <h2 id="imports-heading" className="mb-2 text-xl font-semibold">
          {t("imports")}
        </h2>
        <form
          onSubmit={stage}
          className="mb-3 flex flex-col gap-3 rounded-md border border-slate-300 bg-white p-3 sm:flex-row sm:items-end"
        >
          <div className="flex flex-col gap-1">
            <label htmlFor="import-source" className="font-medium">
              {t("source")}
            </label>
            <select
              id="import-source"
              className={select}
              value={sourceCode}
              onChange={(event) => setSourceCode(event.target.value)}
            >
              <option value="">—</option>
              {sources.data?.sources.map((source) => (
                <option key={source.code} value={source.code}>
                  {source.code}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="import-kind" className="font-medium">
              {t("kind")}
            </label>
            <select
              id="import-kind"
              className={select}
              value={kind}
              onChange={(event) => setKind(event.target.value)}
            >
              {[
                "catalogue",
                "nppa_ceiling",
                "nppa_retail",
                "ja_products",
                "ja_kendras",
                "regulatory_flags",
              ].map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="import-file" className="font-medium">
              {t("file")}
            </label>
            <input
              id="import-file"
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </div>
          <button type="submit" disabled={!file || !sourceCode} className={buttonClass()}>
            {t("stage")}
          </button>
        </form>
        {error ? (
          <p role="alert" className="text-red-800">
            {error}
          </p>
        ) : null}
        <ul className="space-y-2">
          {batches.data?.batches.map((batch) => (
            <li key={batch.id}>
              <Card className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="font-medium">
                    #{batch.id} {batch.file_name} ({batch.kind}): {batch.status}
                    <DemoBadge show={batch.is_demo} />
                  </p>
                  <p className="text-sm">
                    {t("rows", {
                      valid: batch.valid_count,
                      failed: batch.failed_count,
                      total: batch.row_count,
                    })}
                  </p>
                </div>
                {batch.status === "validated" ? (
                  <div className="flex gap-2">
                    <Button
                      onClick={() =>
                        void post(`/admin/imports/${batch.id}/publish`).then(refreshAll)
                      }
                    >
                      {t("publish")}
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() =>
                        void post(`/admin/imports/${batch.id}/reject`).then(refreshAll)
                      }
                    >
                      {t("reject")}
                    </Button>
                  </div>
                ) : null}
              </Card>
            </li>
          ))}
        </ul>
      </section>
      <section aria-labelledby="queue-heading">
        <h2 id="queue-heading" className="mb-2 text-xl font-semibold">
          {t("queue")}
        </h2>
        {queue.data?.rows.length === 0 ? <Empty>{t("queueEmpty")}</Empty> : null}
        <ul className="space-y-2">
          {queue.data?.rows.map((row) => (
            <QueueItem key={row.id} row={row} onChanged={refreshAll} />
          ))}
        </ul>
      </section>
      <section aria-labelledby="pharmacists-heading">
        <h2 id="pharmacists-heading" className="mb-2 text-xl font-semibold">
          {t("pharmacists")}
        </h2>
        <p className="mb-2">{t("selfDeclared")}</p>
        {pharmacists.data?.pharmacists.length === 0 ? <Empty>{t("noPharmacists")}</Empty> : null}
        <ul className="space-y-2">
          {pharmacists.data?.pharmacists.map((row) => (
            <li key={row.user_id}>
              <Card className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="font-medium">{row.display_name ?? row.email}</p>
                  <p className="text-sm">
                    {row.registration_number} · {row.state_council} · {row.status}
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button
                    onClick={() =>
                      void post(`/admin/pharmacists/${row.user_id}/decision`, {
                        status: "approved",
                      }).then(refreshAll)
                    }
                  >
                    {t("approve")}
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() =>
                      void post(`/admin/pharmacists/${row.user_id}/decision`, {
                        status: "rejected",
                      }).then(refreshAll)
                    }
                  >
                    {t("rejectUser")}
                  </Button>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      </section>
      <section aria-labelledby="audit-heading">
        <h2 id="audit-heading" className="mb-2 text-xl font-semibold">
          {t("audit")}
        </h2>
        <div
          className="overflow-x-auto rounded-md border border-slate-300 bg-white"
          tabIndex={0}
          role="region"
          aria-labelledby="audit-heading"
        >
          <table className="w-full text-left text-sm">
            <thead>
              <tr>
                <th scope="col" className="p-2">
                  {t("when")}
                </th>
                <th scope="col" className="p-2">
                  {t("action")}
                </th>
                <th scope="col" className="p-2">
                  {t("entity")}
                </th>
              </tr>
            </thead>
            <tbody>
              {audit.data?.events.map((event) => (
                <tr key={event.id} className="border-t border-slate-200">
                  <td className="p-2">{event.created_at.slice(0, 19)}</td>
                  <td className="p-2">{event.action}</td>
                  <td className="p-2">{event.entity_type}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
