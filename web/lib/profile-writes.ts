import type { i18n as I18n } from "i18next";

import { getMe, patchMe, type ApiUser, type ProfilePatch } from "./argus-api";
import {
  localeForLanguage,
  normalizeEnabledLanguage,
  type ArgusLanguage,
} from "./language-features";

/*
 * The one way a profile field reaches the server.
 *
 * Every read and write of the profile queues here, one at a time for the whole
 * tab. `PATCH /me` rewrites the row from a read, so two in flight can undo each
 * other on the server, and a response that lands late replaces a newer copy.
 */
let profileRequestChain: Promise<unknown> = Promise.resolve();

export function serializeProfileRequest<T>(
  request: () => Promise<T>,
): Promise<T> {
  const queued = profileRequestChain.then(request, request);
  profileRequestChain = queued.then(
    () => undefined,
    () => undefined,
  );
  return queued;
}

export function readProfile() {
  return serializeProfileRequest(() => getMe());
}

/**
 * A failed reply is not proof the account refused: the write can commit before
 * the error. Called inside a queue slot, so the account is asked before anything
 * else can change it.
 */
async function patchProfile(patch: ProfilePatch): Promise<ApiUser> {
  try {
    const { user } = await patchMe(patch);
    return user;
  } catch (error) {
    const account = await getMe().catch(() => null);
    if (account?.user && holdsPatch(account.user, patch)) return account.user;
    throw error;
  }
}

function holdsPatch(user: ApiUser, patch: ProfilePatch): boolean {
  const saved: Record<string, unknown> = user;
  return Object.entries(patch)
    .filter(([, value]) => value !== undefined)
    .every(([field, value]) => saved[field] === value);
}

/** Rejects when the account does not hold the patch; `onSaved` hears every save it does. */
export async function saveProfile(
  patch: ProfilePatch,
  onSaved: (user: ApiUser) => void,
): Promise<void> {
  const user = await serializeProfileRequest(() => patchProfile(patch));
  onSaved(user);
}

type LanguageTarget = Pick<I18n, "language" | "changeLanguage">;

/**
 * Shows the language when its turn in the queue comes and, if the account does
 * not hold it, puts back the language the page showed. Resolves with whether
 * the account holds it.
 */
export async function saveProfileLanguage(
  i18n: LanguageTarget,
  code: string,
  {
    onShown,
    onSaved,
  }: {
    onShown?: (language: ArgusLanguage) => void;
    onSaved: (user: ApiUser) => void;
  },
): Promise<boolean> {
  const language = normalizeEnabledLanguage(code);
  // The whole step holds the slot, so it starts from a page that matches the
  // account and an earlier refusal cannot undo a newer choice.
  const user = await serializeProfileRequest(async () => {
    const shownLanguage = i18n.language;
    await i18n.changeLanguage(language);
    onShown?.(language);
    try {
      return await patchProfile({
        language,
        locale: localeForLanguage(language),
      });
    } catch (error) {
      console.error("Failed to update language", error);
      await i18n.changeLanguage(shownLanguage);
      onShown?.(normalizeEnabledLanguage(shownLanguage));
      return null;
    }
  });
  if (!user) return false;
  onSaved(user);
  return true;
}
