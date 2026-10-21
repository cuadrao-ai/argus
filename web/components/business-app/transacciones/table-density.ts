"use client";

import { useSyncExternalStore } from "react";
import type { ApiUser } from "@/lib/argus-api";
import { readProfile, saveProfile } from "@/lib/profile-writes";

/** Row heights in px (Lucas, October 21, 2026). Type stays 14px in every mode. */
export const DENSITY_ROW_PX = { compacto: 40, normal: 48, amplio: 56 } as const;
export type Density = keyof typeof DENSITY_ROW_PX;
export const DENSITIES = Object.keys(DENSITY_ROW_PX) as Density[];
export const DEFAULT_DENSITY: Density = "normal";

const isDensity = (value: unknown): value is Density => typeof value === "string" && value in DENSITY_ROW_PX;

/** Where the person's choice lives: `table_density` on their profile, `GET` and `PATCH /me`. */
export type DensityProfile = Readonly<{ read: () => Promise<unknown>; write: (next: Density) => Promise<void> }>;

/** The account's answer is what the screen keeps, so a later refusal puts back what the account holds. */
function onProfileSaved(user: ApiUser) {
  if (isDensity(user.table_density)) kept = user.table_density;
}

const meProfile: DensityProfile = {
  read: async () => (await readProfile()).user.table_density,
  write: (next) => saveProfile({ table_density: next }, onProfileSaved),
};

export type DensityState = Readonly<{ density: Density; saving: boolean; failed: boolean }>;

let profile = meProfile;
let state: DensityState = { density: DEFAULT_DENSITY, saving: false, failed: false };
/** The last choice the profile holds, which a refused save puts back. */
let kept: Density = DEFAULT_DENSITY;
let asked = false;
let latest = 0;
const listeners = new Set<() => void>();

function publish(next: DensityState) {
  state = next;
  listeners.forEach((listener) => listener());
}

/** Normal until the profile answers; a profile that cannot answer leaves Normal. */
function askOnce() {
  if (asked) return;
  asked = true;
  const asking = latest;
  profile.read().then((value) => {
    if (asking !== latest || !isDensity(value)) return;
    kept = value;
    publish({ ...state, density: value });
  }, () => undefined);
}

/**
 * The one owner of the person's table density on this screen. The choice
 * shows at once and is kept on the profile; a save the account refuses puts
 * the last kept choice back and says so.
 */
export async function setTableDensity(next: Density): Promise<boolean> {
  const attempt = ++latest;
  publish({ density: next, saving: true, failed: false });
  try {
    await profile.write(next);
    kept = next;
    if (attempt === latest) publish({ density: next, saving: false, failed: false });
    return true;
  } catch {
    if (attempt === latest) publish({ density: kept, saving: false, failed: true });
    return false;
  }
}

/** For tests: forget what was read and use this profile instead. */
export function resetTableDensity(next: DensityProfile = meProfile) {
  profile = next;
  listeners.clear();
  asked = false;
  latest += 1;
  kept = DEFAULT_DENSITY;
  state = { density: DEFAULT_DENSITY, saving: false, failed: false };
}

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  askOnce();
  return () => {
    listeners.delete(listener);
  };
};

const serverState: DensityState = { density: DEFAULT_DENSITY, saving: false, failed: false };

export function useTableDensity(): DensityState {
  return useSyncExternalStore(subscribe, () => state, () => serverState);
}
