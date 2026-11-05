"use client";

import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { Link } from "@/i18n/navigation";
import type { ApiError } from "@/lib/api";
import type { JaProduct, Price, RegulatoryFlag } from "@/lib/types";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-lg border border-slate-300 bg-white p-4 ${className}`}>{children}</div>
  );
}

const BUTTON_VARIANTS = {
  primary: "bg-indigo-800 text-white hover:bg-indigo-900",
  secondary: "border border-slate-500 bg-white text-slate-900 hover:bg-slate-100",
  danger: "border border-red-800 bg-white text-red-800 hover:bg-red-50",
};

export function buttonClass(variant: keyof typeof BUTTON_VARIANTS = "primary"): string {
  return `inline-flex min-h-11 items-center justify-center rounded-md px-4 py-2 text-base font-medium disabled:opacity-60 ${BUTTON_VARIANTS[variant]}`;
}

export function Button({
  variant = "primary",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: keyof typeof BUTTON_VARIANTS }) {
  return <button type="button" {...props} className={`${buttonClass(variant)} ${className}`} />;
}

export function Field({
  label,
  help,
  id,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & { label: string; help?: string; id: string }) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="font-medium text-slate-900">
        {label}
      </label>
      <input
        id={id}
        aria-describedby={help ? `${id}-help` : undefined}
        className="min-h-11 rounded-md border border-slate-500 bg-white px-3 py-2 text-base text-slate-900"
        {...props}
      />
      {help ? (
        <p id={`${id}-help`} className="text-sm text-slate-700">
          {help}
        </p>
      ) : null}
    </div>
  );
}

export function Loading({ label }: { label?: string }) {
  const t = useTranslations("states");
  return (
    <p role="status" aria-live="polite" className="py-6 text-slate-700">
      {label ?? t("loading")}
    </p>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="rounded-md bg-slate-100 p-4 text-slate-800">{children}</p>;
}

export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  const t = useTranslations("states");
  if (error.status === 401) {
    return (
      <div className="rounded-md border border-slate-400 bg-slate-50 p-4">
        <p className="mb-3">{t("signInRequired")}</p>
        <Link href="/login" className={buttonClass()}>
          {t("goSignIn")}
        </Link>
      </div>
    );
  }
  return (
    <div role="alert" className="rounded-md border border-red-800 bg-red-50 p-4 text-red-900">
      <p>{error.status === 404 ? t("notFound") : t("error")}</p>
      {onRetry && error.status !== 404 ? (
        <Button variant="secondary" className="mt-3" onClick={onRetry}>
          {t("retry")}
        </Button>
      ) : null}
    </div>
  );
}

export function Warning({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-md border border-amber-800 bg-amber-50 p-3 text-amber-950">{children}</p>
  );
}

export function DemoBadge({ show = true }: { show?: boolean }) {
  const t = useTranslations("demo");
  if (!show) return null;
  return (
    <span
      title={t("help")}
      className="ms-2 inline-block rounded border border-purple-800 bg-purple-50 px-2 py-0.5 text-sm font-medium text-purple-900"
    >
      {t("badge")}
    </span>
  );
}

export function StaleBadge({ show }: { show: boolean }) {
  const t = useTranslations("prices");
  if (!show) return null;
  return (
    <span
      title={t("staleHelp")}
      className="ms-2 inline-block rounded border border-amber-800 bg-amber-50 px-2 py-0.5 text-sm text-amber-950"
    >
      {t("stale")}
    </span>
  );
}

export function PriceRow({ price }: { price: Price }) {
  const t = useTranslations("prices");
  return (
    <div className="border-t border-slate-200 py-3 first:border-t-0" data-testid="price-row">
      <p className="text-sm font-medium text-slate-800">
        {price.price_type_label}
        <DemoBadge show={price.is_demo} />
        <StaleBadge show={price.is_stale} />
      </p>
      <p className="text-xl font-semibold text-slate-950">
        {t("perUnit", { amount: price.per_unit_inr, unit: price.pack_unit })}
      </p>
      <p className="text-sm text-slate-700">
        {t("forPack", { amount: price.amount_inr, pack: price.pack })}
      </p>
      <p className="text-sm text-slate-700">{t("source", { source: price.source.name })}</p>
      <p className="text-sm text-slate-700">{t("updated", { date: price.last_updated })}</p>
      {price.price_type === "ceiling" ? (
        <p className="mt-1 text-sm text-slate-700">{t("ceilingHelp")}</p>
      ) : null}
    </div>
  );
}

export function PriceList({ prices }: { prices: Price[] }) {
  const t = useTranslations("prices");
  if (prices.length === 0) return <Empty>{t("none")}</Empty>;
  return (
    <div>
      {prices.map((price) => (
        <PriceRow key={`${price.price_type}-${price.pack}`} price={price} />
      ))}
    </div>
  );
}

export function Flags({ flags }: { flags: RegulatoryFlag[] }) {
  if (flags.length === 0) return null;
  return (
    <ul className="mt-2 space-y-2">
      {flags.map((flag) => (
        <li
          key={`${flag.flag_type}-${flag.description}`}
          className="rounded-md border border-red-800 bg-red-50 p-3 text-red-950"
        >
          <p>
            <strong>{flag.flag_type.replaceAll("_", " ")}:</strong> {flag.description}
            <DemoBadge show={flag.is_demo} />
          </p>
          <p className="text-sm">
            {flag.source_name}, {flag.source_date}
          </p>
        </li>
      ))}
    </ul>
  );
}

export function JaProductRow({ product }: { product: JaProduct }) {
  const t = useTranslations("ja");
  const prices = useTranslations("prices");
  return (
    <li className="border-t border-slate-200 py-3 first:border-t-0">
      <p className="font-medium">
        {product.generic_name}
        <DemoBadge show={product.is_demo} />
        <StaleBadge show={product.is_stale} />
      </p>
      <p className="text-sm text-slate-700">
        {t("code")}: {product.drug_code} · {t("unit")}: {product.unit_size}
      </p>
      <p>
        {t("catalogueMrp")}: ₹{product.mrp_inr}
      </p>
      <p className="text-sm text-slate-700">{product.price_type_label}</p>
      <p className="text-sm text-slate-700">{prices("source", { source: product.source.name })}</p>
      <p className="text-sm text-slate-700">{prices("updated", { date: product.last_updated })}</p>
    </li>
  );
}
