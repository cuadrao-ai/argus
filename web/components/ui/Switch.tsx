"use client";

import { useLayoutEffect, useRef, useState, type PointerEvent } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useSwitchLabelsShown } from "@/lib/switch-labels";
import { createSpringDriver, LEAD, TRAIL } from "./spring";

/** Knob diameter, the rail's padding, and how much a press widens the knob. */
const KNOB = 22;
const PAD = 3;
const PRESS_GROW = 6;
/** The rail is two knobs wide plus its padding, so the knob travels exactly one diameter. */
const RAIL_W = KNOB * 2 + PAD * 2;
const RAIL_H = KNOB + PAD * 2;

/**
 * The one on/off switch. It flips first and asks the server after: while
 * `onChange` is pending the knob holds a spinner, and if it rejects the switch
 * rolls back (the caller says why, in a toast). The rail colour, the knob's
 * slide, its shadow and the label morph together in 250ms; the knob itself
 * moves on springs, widening while pressed and stretching as it travels.
 */
export function Switch({ checked, onChange, label, stateLabels, disabled = false, testId }: {
  checked: boolean;
  onChange: (next: boolean) => void | Promise<unknown>;
  /** The switch's name for assistive tech and, when shown, beside it. */
  label: string;
  /** The words for each side, crossfaded inside the rail: "Sí" and "No" unless named here, and none when the person turned switch words off. */
  stateLabels?: { on: string; off: string };
  disabled?: boolean;
  testId?: string;
}) {
  const [optimistic, setOptimistic] = useState<boolean | null>(null);
  const [pending, setPending] = useState(false);
  const on = optimistic ?? checked;
  const { t } = useTranslation();
  const words = useSwitchLabelsShown() ? stateLabels ?? { on: t("common.yes", "Yes"), off: t("common.no", "No") } : null;
  const knob = useRef<HTMLSpanElement>(null);
  const driver = useRef<ReturnType<typeof createSpringDriver<"l" | "r">> | null>(null);
  const placed = useRef(false);

  const restFor = (value: boolean) => (value ? { l: PAD + KNOB, r: PAD + KNOB * 2 } : { l: PAD, r: PAD + KNOB });

  useLayoutEffect(() => {
    driver.current = createSpringDriver<"l" | "r">(
      restFor(on),
      (key, from, to) => ((key === "r") === (to > from) ? LEAD : TRAIL),
      ({ l, r }) => {
        if (!knob.current) return;
        knob.current.style.transform = `translateX(${l}px)`;
        knob.current.style.width = `${Math.max(KNOB, r - l)}px`;
      },
    );
    return () => driver.current?.stop();
    // The driver is made once; `on` places it below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useLayoutEffect(() => {
    if (!driver.current) return;
    if (placed.current) driver.current.set(restFor(on));
    else driver.current.jump(restFor(on));
    placed.current = true;
  }, [on]);

  const press = (event: PointerEvent<HTMLButtonElement>) => {
    if (event.button !== 0 || disabled || pending) return;
    // The knob widens toward where it is going; the release carries it there.
    const rest = restFor(on);
    driver.current?.set(on ? { l: rest.l - PRESS_GROW } : { r: rest.r + PRESS_GROW });
  };
  const release = () => driver.current?.set(restFor(on));

  const flip = () => {
    if (disabled || pending) return;
    const next = !on;
    setOptimistic(next);
    let result: void | Promise<unknown>;
    try {
      result = onChange(next);
    } catch {
      setOptimistic(null);
      return;
    }
    if (!result || typeof (result as Promise<unknown>).then !== "function") {
      setOptimistic(null);
      return;
    }
    setPending(true);
    (result as Promise<unknown>).then(
      () => { setPending(false); setOptimistic(null); },
      () => { setPending(false); setOptimistic(null); },
    );
  };

  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      aria-busy={pending || undefined}
      disabled={disabled}
      data-testid={testId}
      // No pointerup handler: the click that follows a press flips the switch, and the flip lands the knob.
      onPointerDown={press}
      onPointerCancel={release}
      onPointerLeave={(event) => { if (event.pointerType === "mouse" && event.buttons === 1) release(); }}
      onClick={flip}
      className="group relative inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-full focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-40"
    >
      <span
        aria-hidden="true"
        style={{ width: RAIL_W, height: RAIL_H, borderRadius: RAIL_H / 2 }}
        className={`relative block overflow-hidden transition-[background-color,box-shadow] duration-[250ms] ease-out group-focus-visible:shadow-[0_0_0_2px_#FFFEFA,0_0_0_4px_#2f5a49] motion-reduce:transition-none ${on ? "bg-[#2f5a49] dark:bg-[#8fcbb0]" : "bg-[#c9cec9] dark:bg-white/20"}`}
      >
        {words ? <>
          <span className={`absolute inset-y-0 left-0 flex items-center pl-2 text-[11px] font-medium text-[#FFFEFA] transition-opacity duration-[250ms] ease-out dark:text-[#172b26] ${on ? "opacity-100" : "opacity-0"}`}>{words.on}</span>
          <span className={`absolute inset-y-0 right-0 flex items-center pr-2 text-[11px] font-medium text-[#56635e] dark:text-white/80 transition-opacity duration-[250ms] ease-out ${on ? "opacity-0" : "opacity-100"}`}>{words.off}</span>
        </> : null}
        <span
          ref={knob}
          data-switch-knob
          style={{ top: PAD, height: KNOB, borderRadius: KNOB / 2, width: KNOB }}
          className={`absolute left-0 flex items-center justify-center bg-white transition-shadow duration-[250ms] ease-out will-change-transform motion-reduce:transition-none ${on ? "shadow-[0_1px_3px_rgba(23,43,38,0.35)]" : "shadow-[0_1px_2px_rgba(23,43,38,0.2)]"}`}
        >
          {pending ? <Loader2 className="h-3.5 w-3.5 animate-spin text-[#2f5a49] motion-reduce:animate-none" aria-hidden="true" /> : null}
        </span>
      </span>
    </button>
  );
}
