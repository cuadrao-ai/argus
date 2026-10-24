"use client";

import { useEffect, useState } from "react";
import { BusinessMonthCloseView } from "@/components/business-app/BusinessMonthClosePanel";
import { createMockMonthCloseClient, type MonthCloseClient } from "@/lib/business-month-close";
import { secondaryButtonClass } from "@/components/business-app/business-ui";
import { ToastViewport } from "@/components/business-app/foundation/ToastViewport";

const now = new Date(2026, 9, 24);

export default function Preview() {
  const [client, setClient] = useState<MonthCloseClient | null>(null);
  const [run, setRun] = useState(0);
  const [addRequested, setAddRequested] = useState(false);
  useEffect(() => {
    let active = true;
    const settledReceivable = new URLSearchParams(window.location.search).get("empty") === "receivable";
    const sample = createMockMonthCloseClient({ now, failIds: settledReceivable ? [] : ["inv-taller", "inv-farmacia", "inv-luna", "rcpt-transporte"] });
    void Promise.all(["inv-colmado", "inv-caribe", "inv-aurora", "rcpt-ferreteria", "rcpt-papeleria"].map(id => sample.markPendiente(id))).then(async () => {
      if (settledReceivable) {
        const open = await sample.openItems();
        await Promise.all(open.cuentas_por_cobrar.items.map(item => sample.markCobrado(item.id)));
      }
      if (active) setClient(sample);
    });
    return () => { active = false; };
  }, [run]);
  return <main className="min-h-screen bg-[#f7f8f6] p-6 text-[#172b26] dark:bg-[#111315] dark:text-white">
    <header className="mx-auto mb-6 flex max-w-[1440px] flex-wrap items-center gap-4 border-b border-black/10 pb-4 dark:border-white/10">
      <p className="flex-1 text-sm">Design preview · Synthetic data · <a className="underline" href="?">Long lists</a> · <a className="underline" href="?empty=receivable">Receivables settled</a></p>
      {addRequested ? <p role="status" className="text-sm">Preview: Add action received. Home opens document intake here.</p> : null}
      <button className={secondaryButtonClass} onClick={() => { setClient(null); setRun(value => value + 1); }}>Reset preview</button>
    </header>
    <div className="mx-auto max-w-[1440px]">
      {client ? <BusinessMonthCloseView key={run} client={client} now={now} businessCurrency="DOP" onAdd={() => setAddRequested(true)} review={{ detail: null, count: 4, attention: 2, reading: 1, open: () => {} }} /> : null}
    </div>
    <ToastViewport />
  </main>;
}
