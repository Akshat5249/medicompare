import { useTranslations } from "next-intl";

export default function Page() {
  const t = useTranslations("about");
  return (
    <div className="max-w-2xl space-y-3">
      <h1 className="text-2xl font-bold">{t("title")}</h1>
      <p>{t("body")}</p>
      <p>{t("isNot")}</p>
      <p>{t("neutral")}</p>
      <p>{t("data")}</p>
    </div>
  );
}
