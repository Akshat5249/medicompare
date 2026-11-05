import { useTranslations } from "next-intl";
import { DemoNotice, SearchBox } from "@/components/catalogue";
import { Card } from "@/components/ui";
import { Link } from "@/i18n/navigation";

export default function Home() {
  const t = useTranslations("home");
  const cards = [
    { href: "/search", title: t("cardSearchTitle"), body: t("cardSearchBody") },
    { href: "/prescriptions/new", title: t("cardRxTitle"), body: t("cardRxBody") },
    { href: "/jan-aushadhi", title: t("cardJaTitle"), body: t("cardJaBody") },
  ];
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold text-slate-950">{t("title")}</h1>
      <SearchBox />
      <DemoNotice />
      <div className="grid gap-4 sm:grid-cols-3">
        {cards.map((card) => (
          <Card key={card.href}>
            <h2 className="text-lg font-semibold">
              <Link href={card.href} className="text-indigo-900 underline">
                {card.title}
              </Link>
            </h2>
            <p className="mt-1 text-slate-800">{card.body}</p>
          </Card>
        ))}
      </div>
    </div>
  );
}
