"use client";

import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { browserAuthGeneration, requireBrowserAuthGeneration } from "@/lib/browser-auth-generation";
import { claimBusinessNamePrompt, getBusinessName, type BusinessNamePrompt, type BusinessNamingState } from "@/lib/business-naming-api";
import BusinessNameDialog from "./BusinessNameDialog";
import { useBusiness } from "./BusinessWorkspace";

type Naming = { canEdit: boolean; requireName: () => Promise<boolean> };
const NamingContext = createContext<Naming | null>(null);
export const useBusinessNaming = () => useContext(NamingContext);
type Prompt = { business: BusinessNamingState; required: boolean; resolve?: (ready: boolean) => void };

export default function BusinessNamingProvider({ children }: { children: ReactNode }) {
  const { chosen, source, reload } = useBusiness();
  const [prompt, setPrompt] = useState<Prompt | null>(null);
  const pending = useRef<Prompt | null>(null);
  const claims = useRef(new Map<string, Promise<BusinessNamePrompt>>());
  const ownerId = chosen?.role === "owner" && source.mode === "live" ? chosen.space_id : null;
  const current = useRef(ownerId);
  useLayoutEffect(() => {
    current.current = ownerId;
    return () => { current.current = null; };
  }, [ownerId]);

  useEffect(() => {
    let active = true;
    pending.current?.resolve?.(false);
    pending.current = null;
    setPrompt(null);
    if (!ownerId) return;
    const generation = browserAuthGeneration();
    let claim = claims.current.get(ownerId);
    if (!claim) {
      claim = claimBusinessNamePrompt(ownerId);
      claims.current.set(ownerId, claim);
    }
    void claim.then(result => {
      requireBrowserAuthGeneration(generation);
      if (active && current.current === result.id) {
        claims.current.set(ownerId, Promise.resolve({ ...result, show_prompt: false }));
        if (result.show_prompt && !pending.current) setPrompt({ business: result, required: false });
      }
    }).catch(() => undefined);
    return () => { active = false; pending.current?.resolve?.(false); pending.current = null; };
  }, [ownerId]);

  const requireName = useCallback(async () => {
    if (!ownerId) return true;
    const generation = browserAuthGeneration();
    const state = await getBusinessName();
    requireBrowserAuthGeneration(generation);
    if (current.current !== ownerId || state.id !== ownerId) return false;
    if (!state.name_required) return true;
    return new Promise<boolean>(resolve => {
      pending.current?.resolve?.(false);
      const next = { business: state, required: true, resolve };
      pending.current = next;
      setPrompt(next);
    });
  }, [ownerId]);

  return <NamingContext.Provider value={{ canEdit: !!ownerId, requireName }}>
    {children}
    {prompt && prompt.business.id === ownerId ? <BusinessNameDialog key={prompt.business.id + String(prompt.required)} business={prompt.business} required={prompt.required} onClose={() => setPrompt(null)} onSaved={next => {
      if (current.current !== next.id) return;
      setPrompt(null);
      pending.current = null;
      reload();
      prompt.resolve?.(true);
    }} /> : null}
  </NamingContext.Provider>;
}
