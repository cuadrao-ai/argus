"use client";

import { createContext, useContext, useEffect, useLayoutEffect, useRef, type ComponentProps, type ReactNode } from "react";
import AdaptivePanel from "@/components/ui/AdaptivePanel";

/* A settings panel draws through this rather than AdaptivePanel. Inside the
 * Ajustes window the window owns the frame, the title, close and back, so the
 * panel contributes only its body and footer. Anywhere else it is the sheet it
 * always was. */

const SettingsWindowContext = createContext(false);

/** A second step inside a section: the window titles it and, with onBack, draws the arrow back. */
export type SettingsStep = { title: string; onBack?: () => void };

const SettingsStepContext = createContext<(step: SettingsStep | null) => void>(() => undefined);

export function SettingsWindowSection({ children, onStep = () => undefined }: { children: ReactNode; onStep?: (step: SettingsStep | null) => void }) {
  return (
    <SettingsWindowContext.Provider value>
      <SettingsStepContext.Provider value={onStep}>{children}</SettingsStepContext.Provider>
    </SettingsWindowContext.Provider>
  );
}

/** True inside the Ajustes window, where a pick keeps the window open. */
export function useInSettingsWindow(): boolean {
  return useContext(SettingsWindowContext);
}

/** Shows a step's title in the window header while `title` is set; Escape and the arrow run onBack. */
export function useSettingsStep(title: string | null, onBack?: () => void): void {
  const show = useContext(SettingsStepContext);
  const back = useRef(onBack);
  useLayoutEffect(() => {
    back.current = onBack;
  });
  const hasBack = Boolean(onBack);
  useEffect(() => {
    if (title === null) return undefined;
    show({ title, onBack: hasBack ? () => back.current?.() : undefined });
    return () => show(null);
  }, [show, title, hasBack]);
}

export default function SettingsSurface(props: ComponentProps<typeof AdaptivePanel>) {
  const inWindow = useInSettingsWindow();
  if (!inWindow) return <AdaptivePanel {...props} />;
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="argus-thin-scrollbar min-h-0 flex-1 overflow-y-auto">{props.children}</div>
      {props.footer ? (
        <div className="shrink-0 border-t border-[#DCE0DA] px-5 py-3 dark:border-white/10">{props.footer}</div>
      ) : null}
    </div>
  );
}
