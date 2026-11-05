import { use } from "react";
import { PharmacistReview } from "@/components/prescriptions";

export default function Page({ params }: { params: Promise<{ id: string }> }) {
  return <PharmacistReview id={use(params).id} />;
}
