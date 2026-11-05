"use client";

import { useState } from "react";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Switch } from "@/components/ui/Switch";

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// Neutral sample text: this page demonstrates the controls, not product copy.
export default function ControlsPreview() {
  const [period, setPeriod] = useState<"oct" | "sep" | "year">("oct");
  const [list, setList] = useState<"review" | "problem" | "all">("review");
  const [plain, setPlain] = useState(false);
  const [labelled, setLabelled] = useState(true);
  const [saved, setSaved] = useState(false);
  const refused = false;
  return (
    <main className="min-h-[100dvh] bg-[#F7F5EE] px-4 py-6 text-[#172b26] dark:bg-[#141517] dark:text-white">
      <div className="mx-auto flex max-w-xl flex-col gap-8">
        <h1 className="font-display text-[26px] font-medium">Controles</h1>
        <section className="space-y-3">
          <h2 className="text-[13px] font-medium text-[#56635e]">Segmentos a lo ancho</h2>
          <SegmentedControl fill label="Período" value={period} onChange={setPeriod} segments={[{ key: "oct", label: "Octubre" }, { key: "sep", label: "Septiembre" }, { key: "year", label: "2026" }]} />
        </section>
        <section className="space-y-3">
          <h2 className="text-[13px] font-medium text-[#56635e]">Segmentos a su medida, con cuentas</h2>
          <SegmentedControl label="Mostrar" value={list} onChange={setList} segments={[{ key: "review", label: "Por revisar", count: 4 }, { key: "problem", label: "Con problema", count: 3 }, { key: "all", label: "Todo" }]} />
        </section>
        <section className="space-y-4">
          <h2 className="text-[13px] font-medium text-[#56635e]">Interruptores</h2>
          <Row label="Simple"><Switch label="Simple" checked={plain} onChange={setPlain} /></Row>
          <Row label="Con palabras"><Switch label="Con palabras" checked={labelled} onChange={setLabelled} stateLabels={{ on: "Sí", off: "No" }} /></Row>
          <Row label="El servidor responde en 1 segundo"><Switch label="El servidor responde en 1 segundo" checked={saved} onChange={async (next) => { await wait(1000); setSaved(next); }} /></Row>
          <Row label="El servidor dice que no"><Switch label="El servidor dice que no" checked={refused} onChange={async () => { await wait(1000); throw new Error("refused"); }} /></Row>
          <Row label="Desactivado"><Switch label="Desactivado" checked disabled onChange={() => undefined} /></Row>
        </section>
      </div>
    </main>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="flex items-center justify-between gap-4 border-b border-[#DCE0DA] pb-3 text-[15px] dark:border-white/10"><span>{label}</span>{children}</div>;
}
