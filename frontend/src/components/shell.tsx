"use client";

import { useLocale, useTranslations } from "next-intl";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Link, usePathname, useRouter } from "@/i18n/navigation";
import { setCsrfToken, useApi } from "@/lib/api";
import type { SessionPayload, SessionUser } from "@/lib/types";
import { Button, buttonClass } from "./ui";

interface AppContextValue {
  user: SessionUser | null;
  sessionLoading: boolean;
  refreshSession: () => void;
  raiseEmergency: () => void;
}

const AppContext = createContext<AppContextValue>({
  user: null,
  sessionLoading: false,
  refreshSession: () => undefined,
  raiseEmergency: () => undefined,
});

export const useApp = () => useContext(AppContext);

export function EmergencyDialog({ onDismiss }: { onDismiss: () => void }) {
  const t = useTranslations("emergency");
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.focus();
  }, []);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div
        ref={ref}
        tabIndex={-1}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="emergency-title"
        aria-describedby="emergency-body"
        className="w-full max-w-md rounded-lg border-4 border-red-800 bg-white p-6"
      >
        <h2 id="emergency-title" className="text-2xl font-bold text-red-900">
          {t("title")}
        </h2>
        <p id="emergency-body" className="my-4 text-lg text-slate-950">
          {t("body")}
        </p>
        <a
          href="tel:112"
          className="mb-3 flex min-h-14 items-center justify-center rounded-md bg-red-800 text-xl font-bold text-white"
        >
          {t("call")}
        </a>
        <Button variant="secondary" className="w-full" onClick={onDismiss}>
          {t("dismiss")}
        </Button>
      </div>
    </div>
  );
}

const LOCALES = [
  { code: "en", label: "English" },
  { code: "hi", label: "हिन्दी" },
  { code: "ta", label: "தமிழ்" },
] as const;

function LanguageSwitcher() {
  const t = useTranslations("app");
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();
  return (
    <div>
      <label htmlFor="language" className="sr-only">
        {t("language")}
      </label>
      <select
        id="language"
        value={locale}
        onChange={(event) => {
          const query = typeof window === "undefined" ? "" : window.location.search;
          router.replace(`${pathname}${query}`, { locale: event.target.value });
        }}
        className="min-h-11 rounded-md border border-slate-500 bg-white px-2 text-slate-900"
      >
        {LOCALES.map((item) => (
          <option key={item.code} value={item.code}>
            {item.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function Header({ user }: { user: SessionUser | null }) {
  const t = useTranslations("nav");
  const app = useTranslations("app");
  const link =
    "inline-flex min-h-11 items-center px-2 text-slate-900 underline-offset-4 hover:underline";
  return (
    <header className="border-b border-slate-300 bg-white">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-2 px-4 py-2">
        <Link href="/" className="text-xl font-bold text-indigo-900">
          {app("name")}
        </Link>
        <nav aria-label={t("menu")} className="flex flex-wrap items-center gap-1">
          <Link className={link} href="/search">
            {t("search")}
          </Link>
          <Link className={link} href="/jan-aushadhi">
            {t("janAushadhi")}
          </Link>
          <Link className={link} href="/prescriptions">
            {t("prescriptions")}
          </Link>
          {user?.role === "pharmacist" ? (
            <Link className={link} href="/pharmacist">
              {t("pharmacist")}
            </Link>
          ) : null}
          {user?.role === "admin" ? (
            <Link className={link} href="/admin">
              {t("admin")}
            </Link>
          ) : null}
          {user ? (
            <Link className={link} href="/account">
              {t("account")}
            </Link>
          ) : (
            <Link className={buttonClass("secondary")} href="/login">
              {t("login")}
            </Link>
          )}
          <LanguageSwitcher />
        </nav>
      </div>
    </header>
  );
}

function registerServiceWorker() {
  if (typeof window !== "undefined" && "serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  }
}

export function AppShell({ children }: { children: ReactNode }) {
  const t = useTranslations("app");
  const session = useApi<SessionPayload>("/auth/me");
  const [emergency, setEmergency] = useState(false);
  useEffect(registerServiceWorker, []);
  useEffect(() => {
    if (session.data) setCsrfToken(session.data.csrf_token);
  }, [session.data]);
  const raiseEmergency = useCallback(() => setEmergency(true), []);
  const { reload } = session;
  const value = useMemo(
    () => ({
      user: session.data?.user ?? null,
      sessionLoading: session.loading,
      refreshSession: reload,
      raiseEmergency,
    }),
    [session.data, session.loading, reload, raiseEmergency],
  );
  return (
    <AppContext.Provider value={value}>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:z-40 focus:bg-white focus:p-2"
      >
        {t("skip")}
      </a>
      <Header user={value.user} />
      <p
        role="note"
        data-testid="medical-notice"
        className="border-b border-slate-300 bg-indigo-50 px-4 py-2 text-center text-sm text-indigo-950"
      >
        {t("notice")}
      </p>
      <main id="main" className="mx-auto w-full max-w-5xl flex-1 px-4 py-6">
        {children}
      </main>
      <footer className="border-t border-slate-300 bg-white px-4 py-4 text-center text-sm text-slate-800">
        <p>{t("footer")}</p>
        <p className="mt-2 flex justify-center gap-4">
          <Link className="underline" href="/about">
            {t("about")}
          </Link>
          <Link className="underline" href="/privacy">
            {t("privacy")}
          </Link>
        </p>
      </footer>
      {emergency ? <EmergencyDialog onDismiss={() => setEmergency(false)} /> : null}
    </AppContext.Provider>
  );
}
