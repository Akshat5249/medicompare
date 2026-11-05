import { useTranslations } from "next-intl";

export default function Page() {
  const t = useTranslations("privacy");
  return (
    <div className="max-w-2xl space-y-3">
      <h1 className="text-2xl font-bold">{t("title")}</h1>
      <p>{t("minimal")}</p>
      <p>{t("images")}</p>
      <p>{t("rights")}</p>
      <p>{t("ai")}</p>
    </div>
  );
}
