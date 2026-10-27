"use client";
import { useCallback, useMemo, useSyncExternalStore } from "react";
import { BriefcaseBusiness, UserRound } from "lucide-react";
import { initialsOf } from "@/components/ui/Avatar";
import { avatarThemeClassName, avatarThemeStyle } from "@/lib/avatar-theme";
import {
  DEFAULT_APPEARANCE,
  IDENTITY_EVENT,
  identityKey,
  identityPreviewEnabled,
  parseAppearance,
  type IdentityAppearance,
} from "@/lib/identity-appearance";
import { businessAppearanceSnapshot, businessAppearanceState, subscribeBusinessAppearance } from "@/lib/business-profile-api";
export function useIdentityAppearance(scope: string): IdentityAppearance | null {
  const businessId=scope.startsWith("business:")?scope.slice(9):null;
  const savedBusiness=useSyncExternalStore(subscribeBusinessAppearance,()=>businessId?businessAppearanceSnapshot(businessId):null,()=>null);
  const subscribe = useCallback((listener: () => void) => {
    window.addEventListener("storage", listener);
    window.addEventListener(IDENTITY_EVENT, listener);
    return () => {
      window.removeEventListener("storage", listener);
      window.removeEventListener(IDENTITY_EVENT, listener);
    };
  }, []);
  const snapshot = useCallback(() => {
    if (!identityPreviewEnabled() || !scope) return "";
    try {
      // eslint-disable-next-line no-restricted-syntax -- Bounded development-only identity storage; no production data.
      return window.localStorage.getItem(identityKey(scope)) || "";
    } catch {
      return "";
    }
  }, [scope]);
  const raw = useSyncExternalStore(subscribe, snapshot, () => "");
  const preview=useMemo(() => {
    try {
      return parseAppearance(JSON.parse(raw));
    } catch {
      return null;
    }
  }, [raw]);
  return businessId && /^[0-9a-f-]{36}$/i.test(businessId) ? savedBusiness : preview;
}
export function IdentityMark({
  appearance,
  name,
  business = false,
  size = 40,
}: {
  appearance: IdentityAppearance;
  name?: string;
  business?: boolean;
  size?: number;
}) {
  const shape = business ? "rounded-mark" : "rounded-full";
  const base = `inline-flex shrink-0 items-center justify-center overflow-hidden ${shape}`;
  if (appearance.kind === "image")
    return (
      <span
        aria-hidden="true"
        className={base}
        style={{ width: size, height: size }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={appearance.rendered}
          alt=""
          className="h-full w-full object-contain"
        />
      </span>
    );
  const Icon = business ? BriefcaseBusiness : UserRound;
  return (
    <span
      aria-hidden="true"
      className={`${base} ${appearance.kind === "avatar" ? avatarThemeClassName(appearance.token) : "bg-black/[0.05] dark:bg-white/[0.08]"}`}
      style={{
        width: size,
        height: size,
        fontSize: Math.max(14, size / 3),
        ...(appearance.kind === "avatar"
          ? avatarThemeStyle(appearance.token)
          : {}),
      }}
    >
      {appearance.kind === "avatar" && appearance.mark === "initials" ? (
        initialsOf(name)
      ) : (
        <Icon style={{ width: size / 2, height: size / 2 }} strokeWidth={2} />
      )}
    </span>
  );
}
export function SavedIdentityMark({
  scope,
  name,
  business = false,
  size = 40,
  fallback,
}: {
  scope: string;
  name?: string;
  business?: boolean;
  size?: number;
  fallback?: React.ReactNode;
}) {
  const appearance = useIdentityAppearance(scope);
  const state=useSyncExternalStore(subscribeBusinessAppearance,()=>business&&scope.startsWith("business:")?businessAppearanceState(scope.slice(9)):null,()=>null);
  if(business&&state==="loading"&&!appearance)return <span aria-busy="true" className="inline-flex shrink-0 animate-pulse rounded-mark bg-black/5 dark:bg-white/10" style={{width:size,height:size}}/>;
  if(business&&state==="failed")return <span aria-hidden="true" className="inline-flex shrink-0 items-center justify-center rounded-mark bg-black/5 dark:bg-white/10" style={{width:size,height:size}}>-</span>;
  return !appearance && fallback ? (
    <>{fallback}</>
  ) : (
    <IdentityMark
      appearance={appearance ?? DEFAULT_APPEARANCE}
      name={name}
      business={business}
      size={size}
    />
  );
}
