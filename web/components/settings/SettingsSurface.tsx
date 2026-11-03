"use client";

import { createContext, useContext, type ComponentProps, type ReactNode } from "react";
import AdaptivePanel from "@/components/ui/AdaptivePanel";

/* A settings panel draws through this rather than AdaptivePanel. Inside the
 * Ajustes window the window owns the frame, the title, close and back, so the
 * panel contributes only its body and footer. Anywhere else it is the sheet it
 * always was. */

const SettingsWindowContext = createContext(false);

export function SettingsWindowSection({ children }: { children: ReactNode }) {
  return <SettingsWindowContext.Provider value>{children}</SettingsWindowContext.Provider>;
}

/** True inside the Ajustes window, where a pick keeps the window open. */
export function useInSettingsWindow(): boolean {
  return useContext(SettingsWindowContext);
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
