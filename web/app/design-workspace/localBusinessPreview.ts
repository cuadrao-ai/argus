import { useCallback, useMemo, useSyncExternalStore } from "react";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import type { BusinessCountry, GrantedSpace } from "@/lib/business-api";
import { getChosenGrant, LOCAL_BUSINESS_PREFIX } from "@/lib/business-grant";
import {
  identityKey,
  saveAppearance,
  type IdentityAppearance,
} from "@/lib/identity-appearance";
export { LOCAL_BUSINESS_PREFIX } from "@/lib/business-grant";
export const LOCAL_BUSINESS_KEY = "cuadrao-local-businesses-v1";
export const LOCAL_BUSINESS_EVENT = "cuadrao-local-businesses-changed";
export type LocalBusiness = {
  id: string;
  name: string;
  country: BusinessCountry;
};
type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;
export function readLocalBusinesses(
  storage: Pick<Storage, "getItem">,
): LocalBusiness[] {
  try {
    const data: unknown = JSON.parse(
      storage.getItem(LOCAL_BUSINESS_KEY) || "[]",
    );
    return Array.isArray(data)
      ? data
          .filter((item): item is LocalBusiness =>
            Boolean(
              item &&
              typeof item.id === "string" &&
              /^local-business-[a-z0-9-]{1,64}$/i.test(item.id) &&
              typeof item.name === "string" &&
              item.name.trim() &&
              item.name.length <= 80 &&
              ["DO", "US", "CA"].includes(item.country),
            ),
          )
          .slice(0, 20)
      : [];
  } catch {
    return [];
  }
}
export function useLocalBusinessDirectory(enabled: boolean) {
  const subscribe = useCallback((listener: () => void) => {
    window.addEventListener("storage", listener);
    window.addEventListener(LOCAL_BUSINESS_EVENT, listener);
    return () => {
      window.removeEventListener("storage", listener);
      window.removeEventListener(LOCAL_BUSINESS_EVENT, listener);
    };
  }, []);
  const snapshot = useCallback(() => {
    try {
      return enabled
        ? (browserStorage()?.getItem(LOCAL_BUSINESS_KEY) ?? "")
        : "";
    } catch {
      return "";
    }
  }, [enabled]);
  const raw = useSyncExternalStore(subscribe, snapshot, () => "");
  return useMemo(() => readLocalBusinesses({ getItem: () => raw }), [raw]);
}
export function localBusinessGrant(business: LocalBusiness): GrantedSpace {
  return {
    space_id: business.id,
    grant_id: business.id,
    name: business.name,
    role: "owner",
    permissions: ["read", "prepare", "approve", "manage", "download", "export", "assign_owner"],
    capabilities: ["read", "prepare", "approve"],
    access_seen: true,
  };
}
export function createLocalBusiness(
  storage: StorageLike,
  name: string,
  country: string,
  appearance: IdentityAppearance,
  id = `${LOCAL_BUSINESS_PREFIX}${crypto.randomUUID()}`,
): LocalBusiness {
  if (
    !name.trim() ||
    name.trim().length > 80 ||
    !["DO", "US", "CA"].includes(country)
  )
    throw new Error("invalid_business");
  const previous = readLocalBusinesses(storage);
  if (previous.length >= 20) throw new Error("local_limit");
  const business = {
    id,
    name: name.trim(),
    country: country as BusinessCountry,
  };
  const existing = previous.find((item) => item.id === id);
  if (existing) return existing;
  saveAppearance(storage, `business:${id}`, appearance);
  try {
    storage.setItem(
      LOCAL_BUSINESS_KEY,
      JSON.stringify([...previous, business]),
    );
  } catch (error) {
    storage.removeItem(identityKey(`business:${id}`));
    throw error;
  }
  return business;
}
function browserStorage(): StorageLike | null {
  try {
    // eslint-disable-next-line no-restricted-syntax -- Bounded development-only identity storage; no production data.
    return window.localStorage;
  } catch {
    return null;
  }
}
export function createLocalBusinessPreviewSource(base: BusinessDataSource) {
  const sources = new Map<string | null, BusinessDataSource>();
  return (grant: string | null) => {
    let source = sources.get(grant);
    if (!source) {
      source = withLocalBusinessPreview(base, undefined, () => grant);
      sources.set(grant, source);
    }
    return source;
  };
}
export function withLocalBusinessPreview(
  base: BusinessDataSource,
  storage: () => StorageLike | null = browserStorage,
  selected: () => string | null = getChosenGrant,
): BusinessDataSource {
  const directory = () => {
    const store = storage();
    return store ? readLocalBusinesses(store) : [];
  };
  const current = () => directory().find((item) => item.id === selected());
  const blankActivity = {
    reading_count: 0,
    unread_count: 0,
    presentation: "none" as const,
    pending_review_count: 0,
    needs_attention_count: 0,
    ready_to_review_count: 0,
  };
  const emptySearch = {
    expenses: [],
    ventas: [],
    receipts: [],
    accounts: [],
    email_deliveries: [],
    email_senders: [],
    next_cursors: {},
  };
  const local: Partial<BusinessDataSource> = {
    ensureSpace: async () => ({
      id: current()!.id,
      name: current()!.name,
      country: current()!.country,
    }),
    workspace: async () => ({
      country: current()!.country,
      accounts: [],
      currencies: [],
      assistant_available: false,
      chat_available: false,
      receipt_limits: {
        max_bytes: 10 * 1024 * 1024,
        media_types: ["application/pdf", "image/jpeg", "image/png"],
      },
    }),
    overview: async (from, to) => ({
      from,
      to: to ?? new Date().toISOString().slice(0, 10),
      today: new Date().toISOString().slice(0, 10),
      country: current()!.country,
      totals: [],
      fiscal_totals: [],
      without_fiscal_totals: [],
      last_received_at: null,
      last_confirmed_at: null,
      outside_period_count: 0,
      outside_period_latest_on: null,
    }),
    receipts: async () => [],
    expenses: async () => [],
    captures: async () => ({ items: [], has_more: false }),
    receiptActivity: async () => blankActivity,
    receiptPage: async () => ({ items: [], activity: blankActivity }),
    search: async () => emptySearch,
    searchMore: async () => emptySearch,
    searchRecents: async () => [],
    emailDeliveries: async () => [],
    access: async () => ({ grants: [], invites: [] }),
    emailIntake: async () => ({
      enabled: true,
      receiving_address: `recibos-${current()!.id.slice(-12)}@recibos.cuadrao.example`,
    }),
    fiscalProfile: async () => ({
      name: current()!.name,
      tax_id: null,
      can_edit: true,
    }),
  };
  return new Proxy(base, {
    get(target, key: keyof BusinessDataSource) {
      if (key === "mode")
        return selected()?.startsWith(LOCAL_BUSINESS_PREFIX)
          ? "fixture"
          : base.mode;
      if (key === "spaces")
        return async () => [
          ...(await base.spaces()),
          ...directory().map(localBusinessGrant),
        ];
      if (key === "spaceDirectory")
        return async () => {
          const result = base.spaceDirectory
            ? await base.spaceDirectory()
            : { spaces: await base.spaces(), closed_spaces: [] };
          return {
            ...result,
            spaces: [...result.spaces, ...directory().map(localBusinessGrant)],
          };
        };
      const original = target[key];
      if (
        typeof original !== "function" &&
        !(
          selected()?.startsWith(LOCAL_BUSINESS_PREFIX) &&
          typeof local[key] === "function"
        )
      )
        return original;
      return (...args: unknown[]) => {
        if (
          !selected()?.startsWith(LOCAL_BUSINESS_PREFIX) ||
          key === "consent" ||
          key === "acceptConsent"
        )
          return (original as (...values: unknown[]) => unknown)?.(...args);
        const handler = local[key];
        if (!current() || typeof handler !== "function")
          return Promise.reject(
            Object.assign(new Error("local_action_unavailable"), {
              status: 404,
            }),
          );
        return (handler as (...values: unknown[]) => unknown)(...args);
      };
    },
  });
}
