import { use } from "react";
import { SummaryPage } from "@/components/prescriptions";

export default function Page({ params }: { params: Promise<{ id: string }> }) {
  return <SummaryPage id={use(params).id} />;
}
