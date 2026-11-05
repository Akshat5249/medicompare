import { use } from "react";
import { VerificationPage } from "@/components/prescriptions";

export default function Page({ params }: { params: Promise<{ id: string }> }) {
  return <VerificationPage id={use(params).id} />;
}
