import { use } from "react";
import { MedicinePage } from "@/components/catalogue";

export default function Page({ params }: { params: Promise<{ id: string }> }) {
  return <MedicinePage id={use(params).id} />;
}
