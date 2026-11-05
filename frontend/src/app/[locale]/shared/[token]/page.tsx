import type { Metadata } from "next";
import { use } from "react";
import { SharedPage } from "@/components/prescriptions";

export const metadata: Metadata = { robots: { index: false, follow: false } };

export default function Page({ params }: { params: Promise<{ token: string }> }) {
  return <SharedPage token={use(params).token} />;
}
