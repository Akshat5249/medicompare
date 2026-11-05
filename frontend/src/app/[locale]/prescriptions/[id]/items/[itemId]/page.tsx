import { use } from "react";
import { ItemComparison } from "@/components/prescriptions";

export default function Page({ params }: { params: Promise<{ id: string; itemId: string }> }) {
  const { id, itemId } = use(params);
  return <ItemComparison id={id} itemId={itemId} />;
}
