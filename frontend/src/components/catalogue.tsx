"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useRouter } from "@/i18n/navigation";
import { post, useApi } from "@/lib/api";
import type {
  Emergency,
  JaProduct,
  Kendra,
  MedicineDetail,
  MedicineSummary,
  OptionsResponse,
  SearchResponse,
  SearchResult,
} from "@/lib/types";
import { SaveToList } from "./account";
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

export function SearchBox({ initial = "" }: { initial?: string }) {
  const t = useTranslations("home");
  const router = useRouter();
  const { raiseEmergency } = useApp();
  const [query, setQuery] = useState(initial);
  useEffect(() => setQuery(initial), [initial]);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const text = query.trim();
    if (text.length < 2) return;
    // Checked before navigating, so an emergency interrupts even a slow search.
    const check = await post<Emergency>("/safety/check", { text }).catch(() => null);
    if (check?.detected) {
      raiseEmergency();
      return;
    }
    router.push(`/search?q=${encodeURIComponent(text)}`);
  };
  return (
    <form role="search" onSubmit={submit} className="flex flex-col gap-2 sm:flex-row sm:items-end">
      <div className="flex-1">
        <Field
          id="search-input"
          label={t("searchLabel")}
          placeholder={t("searchPlaceholder")}
          value={query}
          maxLength={120}
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>
      <button type="submit" className={buttonClass()}>
        {t("searchButton")}
      </button>
    </form>
  );
}

function ResultCard({ result }: { result: SearchResult }) {
  const t = useTranslations("search");
  const { medicine } = result;
  return (
    <li>
      <Card>
        <h3 className="text-lg font-semibold">
          <Link href={`/medicines/${medicine.id}`} className="text-indigo-900 underline">
            {medicine.display_name}
          </Link>
          <DemoBadge show={medicine.is_demo} />
        </h3>
        <p className="text-slate-800">
          {medicine.dosage_form} · {medicine.release_type} · {medicine.route}
        </p>
        <p className="mt-1 text-sm text-slate-700">
          <span className="font-medium">{t("why")}:</span> {result.reason}
        </p>
      </Card>
    </li>
  );
}

export function SearchResults({ query }: { query: string }) {
  const t = useTranslations("search");
  const { raiseEmergency } = useApp();
  const valid = query.trim().length >= 2;
  const state = useApi<SearchResponse>(valid ? `/search?q=${encodeURIComponent(query)}` : null);
  const detected = state.data?.emergency.detected;
  useEffect(() => {
    if (detected) raiseEmergency();
  }, [detected, raiseEmergency]);
  if (!valid) return <Empty>{t("prompt")}</Empty>;
  if (state.loading) return <Loading />;
  if (state.error) return <ErrorState error={state.error} onRetry={state.reload} />;
  const data = state.data;
  if (!data || detected) return null;
  if (data.exact_matches.length === 0 && data.possible_matches.length === 0) {
    return <Empty>{t("none")}</Empty>;
  }
  return (
    <div className="space-y-6">
      {data.exact_matches.length > 0 ? (
        <section aria-labelledby="exact-heading">
          <h2 id="exact-heading" className="mb-2 text-xl font-semibold">
            {t("exact")}
          </h2>
          <ul className="space-y-3">
            {data.exact_matches.map((result) => (
              <ResultCard key={result.medicine.id} result={result} />
            ))}
          </ul>
        </section>
      ) : null}
      {data.possible_matches.length > 0 ? (
        <section aria-labelledby="possible-heading">
          <h2 id="possible-heading" className="mb-2 text-xl font-semibold">
            {t("possible")}
          </h2>
          <div className="mb-3">
            <Warning>{t("possibleHelp")}</Warning>
          </div>
          <ul className="space-y-3">
            {data.possible_matches.map((result) => (
              <ResultCard key={result.medicine.id} result={result} />
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

export function MedicineFacts({ medicine }: { medicine: MedicineDetail }) {
  const t = useTranslations("medicine");
  const row = (label: string, value: string) => (
    <div className="grid grid-cols-1 gap-1 border-t border-slate-200 py-2 sm:grid-cols-3">
      <dt className="font-medium">{label}</dt>
      <dd className="sm:col-span-2">{value}</dd>
    </div>
  );
  return (
    <>
      <h2 className="text-xl font-semibold">{t("composition")}</h2>
      <div className="my-2 overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr>
              <th scope="col" className="pe-3">
                {t("ingredient")}
              </th>
              <th scope="col" className="pe-3">
                {t("salt")}
              </th>
              <th scope="col">{t("strength")}</th>
            </tr>
          </thead>
          <tbody>
            {medicine.ingredients.map((ingredient) => (
              <tr key={ingredient.name} className="border-t border-slate-200">
                <td className="py-1 pe-3">{ingredient.name}</td>
                <td className="py-1 pe-3">{ingredient.salt_form ?? t("saltNotStated")}</td>
                <td className="py-1">{ingredient.strength}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <dl>
        {row(t("form"), medicine.dosage_form)}
        {row(t("route"), medicine.route)}
        {row(t("release"), medicine.release_type)}
        {row(t("pack"), medicine.pack_sizes.join(", "))}
        {row(t("maker"), medicine.manufacturer ?? t("makerNone"))}
        {medicine.therapeutic_category ? row(t("category"), medicine.therapeutic_category) : null}
        {row(t("source"), medicine.source.name)}
        {medicine.source_date ? row(t("sourceDate"), medicine.source_date) : null}
        {medicine.source_text ? row(t("sourceText"), medicine.source_text) : null}
      </dl>
      <h2 className="mt-4 text-xl font-semibold">{t("flags")}</h2>
      {medicine.regulatory_flags.length > 0 ? (
        <Flags flags={medicine.regulatory_flags} />
      ) : (
        <p className="text-slate-800">{t("noFlags")}</p>
      )}
    </>
  );
}

function OptionHeading({ medicine }: { medicine: MedicineSummary }) {
  const t = useTranslations("options");
  return (
    <h4 className="font-semibold">
      {medicine.display_name}
      <DemoBadge show={medicine.is_demo} />{" "}
      <Link
        href={`/medicines/${medicine.id}`}
        className="text-sm font-normal text-indigo-900 underline"
      >
        {t("open")}
      </Link>
    </h4>
  );
}

/** Options are neutral: never green, never "recommended". Differences are shown first. */
export function OptionsView({ data }: { data: OptionsResponse }) {
  const t = useTranslations("options");
  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">{t("title")}</h2>
      <Warning>{t("disclaimer")}</Warning>
      <section aria-labelledby="same-heading">
        <h3 id="same-heading" className="mb-2 text-lg font-semibold">
          {t("same")}
        </h3>
        {data.equivalents.length === 0 ? <Empty>{t("sameNone")}</Empty> : null}
        <ul className="space-y-3">
          {data.equivalents.map((option) => (
            <li key={option.medicine.id}>
              <Card>
                <OptionHeading medicine={option.medicine} />
                {option.differences.length > 0 ? (
                  <div className="my-2">
                    <Warning>
                      <strong>{t("differences")}:</strong>{" "}
                      {option.differences.map((difference) => difference.detail).join(" ")}
                    </Warning>
                  </div>
                ) : null}
                <Flags flags={option.regulatory_flags} />
                <PriceList prices={option.prices} />
                {option.savings.map((saving) => (
                  <p key={saving.statement} className="mt-2 rounded-md bg-slate-100 p-2 text-sm">
                    <strong>{t("saving")}:</strong> {saving.statement}
                  </p>
                ))}
              </Card>
            </li>
          ))}
        </ul>
      </section>
      {data.jan_aushadhi.length > 0 ? (
        <section aria-labelledby="ja-heading">
          <h3 id="ja-heading" className="mb-2 text-lg font-semibold">
            {t("ja")}
          </h3>
          <p className="mb-2 text-slate-800">{t("jaHelp")}</p>
          <Card>
            <ul>
              {data.jan_aushadhi.map((product: JaProduct) => (
                <JaProductRow key={product.drug_code} product={product} />
              ))}
            </ul>
          </Card>
        </section>
      ) : null}
      {data.not_equivalent.length > 0 ? (
        <section aria-labelledby="unlike-heading">
          <h3 id="unlike-heading" className="mb-2 text-lg font-semibold">
            {t("notEquivalent")}
          </h3>
          <p className="mb-2 text-slate-800">{t("notEquivalentHelp")}</p>
          <ul className="space-y-3">
            {data.not_equivalent.map((option) => (
              <li key={option.medicine.id} data-testid="not-comparable">
                <Card>
                  <OptionHeading medicine={option.medicine} />
                  <p className="mt-1 text-sm">
                    <strong>{t("reason")}:</strong> {option.reasons.join(" ")}
                  </p>
                  <Flags flags={option.regulatory_flags} />
                </Card>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

export function MedicinePage({ id }: { id: string }) {
  const prices = useTranslations("prices");
  const state = useApi<OptionsResponse>(`/medicines/${id}/options`);
  if (state.loading) return <Loading />;
  if (state.error) return <ErrorState error={state.error} onRetry={state.reload} />;
  if (!state.data) return null;
  const { medicine } = state.data.reference;
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">
        {medicine.display_name}
        <DemoBadge show={medicine.is_demo} />
      </h1>
      <SaveToList medicineId={medicine.id} />
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

export function JanAushadhiPage() {
  const t = useTranslations("ja");
  const [productQuery, setProductQuery] = useState("");
  const [productPath, setProductPath] = useState("/jan-aushadhi/products");
  const products = useApi<{ products: JaProduct[] }>(productPath);
  const [pin, setPin] = useState("");
  const [area, setArea] = useState("");
  const [pinError, setPinError] = useState(false);
  const [locationError, setLocationError] = useState(false);
  const [kendraPath, setKendraPath] = useState<string | null>(null);
  const kendras = useApi<{ kendras: Kendra[] }>(kendraPath);
  const searchPin = (event: FormEvent) => {
    event.preventDefault();
    const ok = /^[1-9]\d{5}$/.test(pin);
    setPinError(!ok);
    if (ok) setKendraPath(`/jan-aushadhi/kendras?pin=${pin}`);
  };
  const searchArea = (event: FormEvent) => {
    event.preventDefault();
    if (area.trim().length >= 2) {
      setKendraPath(`/jan-aushadhi/kendras?area=${encodeURIComponent(area.trim())}`);
    }
  };
  const useLocation = () => {
    setLocationError(false);
    navigator.geolocation.getCurrentPosition(
      (position) =>
        setKendraPath(
          `/jan-aushadhi/kendras?lat=${position.coords.latitude.toFixed(3)}&lon=${position.coords.longitude.toFixed(3)}`,
        ),
      () => setLocationError(true),
      { maximumAge: 0, timeout: 10000 },
    );
  };
  const allDemo = products.data?.products.every((product) => product.is_demo) ?? false;
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">{t("title")}</h1>
      <p>{t("intro")}</p>
      {allDemo ? <Warning>{t("demoWarning")}</Warning> : null}
      <section aria-labelledby="kendra-heading" className="space-y-3">
        <h2 id="kendra-heading" className="text-xl font-semibold">
          {t("kendraTitle")}
        </h2>
        <p>{t("contact")}</p>
        <form onSubmit={searchPin} className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <Field
            id="pin"
            label={t("pinLabel")}
            inputMode="numeric"
            maxLength={6}
            value={pin}
            onChange={(event) => setPin(event.target.value)}
            aria-invalid={pinError}
          />
          <button type="submit" className={buttonClass()}>
            {t("findPin")}
          </button>
        </form>
        {pinError ? (
          <p role="alert" className="text-red-800">
            {t("pinInvalid")}
          </p>
        ) : null}
        <form onSubmit={searchArea} className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <Field
            id="area"
            label={t("areaLabel")}
            value={area}
            maxLength={80}
            onChange={(event) => setArea(event.target.value)}
          />
          <button type="submit" className={buttonClass("secondary")}>
            {t("findArea")}
          </button>
        </form>
        <div>
          <Button variant="secondary" onClick={useLocation}>
            {t("useLocation")}
          </Button>
          <p className="mt-1 text-sm text-slate-700">{t("locationNote")}</p>
          {locationError ? (
            <p role="alert" className="text-red-800">
              {t("locationFailed")}
            </p>
          ) : null}
        </div>
        {kendras.loading ? <Loading /> : null}
        {kendras.error ? <ErrorState error={kendras.error} /> : null}
        {kendras.data?.kendras.length === 0 ? <Empty>{t("noKendras")}</Empty> : null}
        <ul className="space-y-3" data-testid="kendra-list">
          {kendras.data?.kendras.map((kendra) => (
            <li key={kendra.kendra_code}>
              <Card>
                <h3 className="font-semibold">
                  {kendra.name}
                  <DemoBadge show={kendra.is_demo} />
                </h3>
                <p>{kendra.address}</p>
                <p>
                  {kendra.district}, {kendra.state} {kendra.pin_code}
                </p>
                {kendra.distance_km !== undefined ? (
                  <p>{t("distance", { km: kendra.distance_km })}</p>
                ) : null}
                <p className="text-sm text-slate-700">
                  {kendra.source.name}, {kendra.last_updated}
                </p>
              </Card>
            </li>
          ))}
        </ul>
      </section>
      <section aria-labelledby="products-heading" className="space-y-3">
        <h2 id="products-heading" className="text-xl font-semibold">
          {t("productsTitle")}
        </h2>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            const value = productQuery.trim();
            setProductPath(
              value
                ? `/jan-aushadhi/products?q=${encodeURIComponent(value)}`
                : "/jan-aushadhi/products",
            );
          }}
          className="flex flex-col gap-2 sm:flex-row sm:items-end"
        >
          <Field
            id="product-query"
            label={t("productLabel")}
            value={productQuery}
            maxLength={120}
            onChange={(event) => setProductQuery(event.target.value)}
          />
          <button type="submit" className={buttonClass("secondary")}>
            {t("productSearch")}
          </button>
        </form>
        {products.loading ? <Loading /> : null}
        {products.error ? <ErrorState error={products.error} onRetry={products.reload} /> : null}
        {products.data?.products.length === 0 ? <Empty>{t("noProducts")}</Empty> : null}
        {products.data?.products.length ? (
          <Card>
            <ul>
              {products.data.products.map((product) => (
                <JaProductRow key={product.drug_code} product={product} />
              ))}
            </ul>
          </Card>
        ) : null}
      </section>
    </div>
  );
}
