"use client";

import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { browserAuthGeneration, requireBrowserAuthGeneration } from "@/lib/browser-auth-generation";
import { getBusinessName, type BusinessNamingState } from "@/lib/business-naming-api";
import BusinessNameDialog from "./BusinessNameDialog";
import { useBusiness } from "./BusinessWorkspace";

type Naming = { canEdit: boolean; requireName: () => Promise<boolean> };
const NamingContext = createContext<Naming | null>(null);
export const useBusinessNaming = () => useContext(NamingContext);
type Prompt = { business: BusinessNamingState; resolve: (ready: boolean) => void };

/**
 * The name a step needs before it can go on (an invitation, an export). It asks only then: a new Business gets
 * no prompt of its own, because Inicio's setup guide holds its first steps.
 */
export default function BusinessNamingProvider({ children }: { children: ReactNode }) {
  const { chosen, source, reload } = useBusiness();
  const [prompt, setPrompt] = useState<Prompt | null>(null);
  const pending = useRef<Prompt | null>(null);
  const ownerId = chosen?.role === "owner" && source.mode === "live" ? chosen.space_id : null;
  const current = useRef(ownerId);
  useLayoutEffect(() => {
    current.current = ownerId;
    return () => { current.current = null; };
  }, [ownerId]);

  // Another Business answers no question asked for this one.
  useEffect(() => () => { pending.current?.resolve(false); pending.current = null; setPrompt(null); }, [ownerId]);

  const requireName = useCallback(async () => {
    if (!ownerId) return true;
    const generation = browserAuthGeneration();
    const state = await getBusinessName();
    requireBrowserAuthGeneration(generation);
    if (current.current !== ownerId || state.id !== ownerId) return false;
    if (!state.name_required) return true;
    return new Promise<boolean>(resolve => {
      pending.current?.resolve(false);
      const next = { business: state, resolve };
      pending.current = next;
      setPrompt(next);
    });
  }, [ownerId]);

  return <NamingContext.Provider value={{ canEdit: !!ownerId, requireName }}>
    {children}
    {prompt && prompt.business.id === ownerId ? <BusinessNameDialog key={prompt.business.id} business={prompt.business} required onClose={() => setPrompt(null)} onSaved={next => {
      if (current.current !== next.id) return;
      setPrompt(null);
      pending.current = null;
      reload();
      prompt.resolve(true);
    }} /> : null}
  </NamingContext.Provider>;
}
