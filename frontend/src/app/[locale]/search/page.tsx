import { useTranslations } from "next-intl";
import { use } from "react";
import { SearchBox, SearchResults } from "@/components/catalogue";

export default function SearchPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const t = useTranslations("search");
  const query = use(searchParams).q ?? "";
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">{query ? t("resultsFor", { query }) : t("title")}</h1>
      <SearchBox initial={query} />
      <SearchResults query={query} />
    </div>
  );
}
