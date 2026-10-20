"use client";

import { BusinessClosedNotice } from "@/components/status/BusinessClosedNotice";
import { OfflineBanner } from "@/components/status/OfflineBanner";
import { RemovedMemberScreen } from "@/components/status/RemovedMemberScreen";
import { ServerErrorScreen } from "@/components/status/ServerErrorScreen";

export default function ErrorScreenPreview({ screen }: { screen: string }) {
  if (screen === "removed") return <RemovedMemberScreen onReturn={() => undefined} />;
  if (screen === "offline") {
    return (
      <main className="flex min-h-dvh items-center justify-center bg-[#F7F5EE] p-6">
        <div className="w-full max-w-md">
          <p className="mb-3 font-sans text-sm text-[#2f5a49]">factura.pdf</p>
          <OfflineBanner onRetry={() => undefined} />
        </div>
      </main>
    );
  }
  if (screen === "closed") {
    return (
      <main className="flex min-h-dvh items-center justify-center bg-[#fafbf8] p-6">
        <BusinessClosedNotice />
      </main>
    );
  }
  return <ServerErrorScreen onRetry={() => undefined} reference="c0ffee00" homeHref="/?auth=login" />;
}
