import { describe, expect, test } from "bun:test";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import {
  applyProfileUpdate,
  greetingNameFor,
} from "../lib/account-profile";
import {
  DISPLAY_NAME_MAX_LENGTH,
  PREFERRED_NAME_MAX_LENGTH,
  normalizeProfileName,
  profileNameExceeds,
  profileNameLength,
} from "../lib/profile-names";
import type { ApiUser, UserResponse } from "../lib/guest-account";

const root = join(import.meta.dir, "..");
const source = (relativePath: string) =>
  readFileSync(join(root, relativePath), "utf-8");

const WRITE_PATH = "lib/profile-writes.ts";
const MENU = "components/sidebar/ProfileMenu.tsx";

/** Every file that could send a profile request, not only the menu. */
function sourcesUnder(dir: string): Array<{ path: string; text: string }> {
  return readdirSync(join(root, dir)).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(join(root, path)).isDirectory()) return sourcesUnder(path);
    return /\.tsx?$/.test(entry) ? [{ path, text: source(path) }] : [];
  });
}
const SOURCES = ["app", "components", "lib"].flatMap(sourcesUnder);

/** Each save call's arguments, however the call wraps. */
function saveCalls(text: string): Array<{ awaited: boolean; args: string }> {
  return [...text.matchAll(/\b(?:saveProfile|saveProfileLanguage)\(/g)].map(
    (match) => {
      const start = match.index + match[0].length;
      let end = start;
      for (let depth = 1; depth > 0; end += 1) {
        if (text[end] === "(") depth += 1;
        if (text[end] === ")") depth -= 1;
      }
      return {
        awaited: /await\s+$/.test(text.slice(0, match.index)),
        args: text.slice(start, end - 1),
      };
    },
  );
}
/** The auth page saves the language chosen before sign-in once, then leaves
 * for the workspace: it holds no profile copy to hand the result to and no
 * edit session a late answer could reach, so those two rules do not apply. */
const AUTH_PAGE = "app/page.tsx";
const WRITERS = SOURCES.filter(
  (file) => file.path !== WRITE_PATH && file.path !== AUTH_PAGE && saveCalls(file.text).length > 0,
);

const user = (overrides: Partial<ApiUser> = {}): ApiUser => ({
  id: "user-1",
  email: "a@b.c",
  username: "alex",
  display_name: "Alexandra",
  preferred_name: null,
  language: "en",
  locale: "en-US",
  onboarding: {
    completed: false,
    stage: "language_selection",
    language_confirmed: false,
    primary_goal: null,
  },
  ...overrides,
});

const account = (overrides: Partial<ApiUser> = {}): UserResponse => ({
  user: user(overrides),
  account_kind: "registered",
  guest: null,
  capabilities: {
    can_create_additional_conversation: true,
    can_manage_conversation: true,
    can_save_decision: true,
    can_manage_account: true,
    can_use_omnisearch: true,
    can_search_current_workspace: true,
    can_use_grounded_discovery: true,
    can_submit_feedback: true,
  },
  public_account_access_enabled: false,
});

describe("a saved profile reaches the greeting", () => {
  test("the greeting's name changes on save, with no refetch and no reload", () => {
    // The exact defect: the menu saved, its own copy updated, and the shell went
    // on rendering the name the page had loaded with.
    const loaded = account({ preferred_name: null });
    expect(greetingNameFor(loaded)).toBeNull();

    const saved = applyProfileUpdate(loaded, user({ preferred_name: "Alex" }));

    expect(greetingNameFor(saved)).toBe("Alex");
    // Same snapshot the surface reads, not a second request.
    expect(saved).not.toBe(loaded);
    expect(saved?.account_kind).toBe("registered");
    expect(saved?.capabilities.can_manage_account).toBe(true);
  });

  test("clearing the name reaches the greeting the same way", () => {
    const named = account({ preferred_name: "Alex" });
    expect(greetingNameFor(named)).toBe("Alex");

    const cleared = applyProfileUpdate(named, user({ preferred_name: null }));

    expect(greetingNameFor(cleared)).toBeNull();
  });

  test("a save that is not the name still refreshes the shell's copy", () => {
    // Propagation is per patch, not per field, so a surface added later cannot
    // go stale by omission.
    const loaded = account({ display_name: "Alexandra" });

    const saved = applyProfileUpdate(
      loaded,
      user({ display_name: "A. Rivera", preferred_name: "Alex" }),
    );

    expect(saved?.user.display_name).toBe("A. Rivera");
    expect(greetingNameFor(saved)).toBe("Alex");
  });

  test("a guest with no profile resolves to the nameless pool", () => {
    expect(greetingNameFor(null)).toBeNull();
    expect(greetingNameFor(account({ preferred_name: undefined }))).toBeNull();
  });

  test("nothing to apply to is left alone rather than invented", () => {
    expect(applyProfileUpdate(null, user({ preferred_name: "Alex" }))).toBeNull();
  });

  test("a profile field has one way to the server", () => {
    // A patch sent from anywhere else skips the queue, the rollback and the
    // hand-off together, and the menu was the only file this used to read.
    const senders = SOURCES.filter((file) =>
      /(?<!function )\bpatchMe\(/.test(file.text),
    ).map((file) => file.path);
    expect(senders).toEqual([WRITE_PATH]);

    // The scan reaches every surface that saves today.
    const writers = WRITERS.map((file) => file.path);
    expect(writers).toContain(MENU);
    expect(writers).toContain("components/settings/LanguageModal.tsx");
    // The account holds no theme, so the appearance panel has nothing to save.
    expect(writers).not.toContain("components/settings/AppearanceModal.tsx");
    // The auth page's one save still goes through the write path and leaves at once.
    const authPage = source(AUTH_PAGE);
    expect(saveCalls(authPage).length).toBe(1);
    expect(authPage).toContain("router.replace(postAuthPath());");
  });

  test("every save hands the saved profile on, wherever it is made", () => {
    for (const file of WRITERS) {
      for (const call of saveCalls(file.text)) {
        expect(call.args).toMatch(/\b(?:applyPatchedProfile|onProfileSaved)\b/);
      }
    }
    // A hand-off is only ever the menu's own, passed down unchanged.
    for (const file of SOURCES) {
      for (const [, bound] of file.text.matchAll(/onProfileSaved=\{(\w+)\}/g)) {
        expect(["applyPatchedProfile", "onProfileSaved"]).toContain(bound);
      }
    }
    const menu = source(MENU);
    expect(menu).toContain("onProfileSaved={applyPatchedProfile}");
    // The menu's own copy is no longer set directly from a patch response.
    const afterHelper = menu.slice(menu.indexOf("const applyPatchedProfile"));
    expect(afterHelper).not.toContain("      setProfile(user);\n      setEditing");
  });

  test("the shell owns the propagation and the greeting reads one place", () => {
    const chat = source("components/chat/ChatInterface.tsx");
    const sidebar = source("components/sidebar/ChatSidebar.tsx");

    const hook = source("components/chat/useProfileUpdates.ts");
    expect(chat).toContain("useProfileUpdates(account, setAccount)");
    expect(chat).toContain("onProfileUpdated={onProfileUpdated}");
    expect(chat).toContain("preferredName={greetingName}");
    expect(hook).toContain("applyProfileUpdate(current, user)");
    expect(hook).toContain("greetingNameFor(account)");
    // No second reader of the raw field, which is how the two copies drifted.
    expect(chat).not.toContain("account?.user.preferred_name");
    expect(sidebar).toContain("onProfileUpdated={onProfileUpdated}");
  });
});

describe("a name is measured after it is normalized", () => {
  test("a bound is never applied to what was typed around the name", () => {
    // The exact defect: one leading space in front of a full-length name.
    const padded = ` ${"x".repeat(PREFERRED_NAME_MAX_LENGTH)}`;
    expect(padded.length).toBe(PREFERRED_NAME_MAX_LENGTH + 1);

    expect(normalizeProfileName(padded).length).toBe(PREFERRED_NAME_MAX_LENGTH);
    expect(profileNameExceeds(padded, PREFERRED_NAME_MAX_LENGTH)).toBe(false);
  });

  test("a genuinely over-long name is still refused", () => {
    const tooLong = "x".repeat(PREFERRED_NAME_MAX_LENGTH + 1);
    expect(profileNameExceeds(tooLong, PREFERRED_NAME_MAX_LENGTH)).toBe(true);
    expect(profileNameExceeds(`  ${tooLong}  `, PREFERRED_NAME_MAX_LENGTH)).toBe(
      true,
    );
  });

  test("both name fields use the one rule", () => {
    const padded = ` ${"x".repeat(DISPLAY_NAME_MAX_LENGTH)}`;
    expect(profileNameExceeds(padded, DISPLAY_NAME_MAX_LENGTH)).toBe(false);
  });

  test("a name is measured in the units the bound is stated in", () => {
    // String.length counts UTF-16 code units, so anything outside the BMP counts
    // twice and the browser refused names the API and the database both take.
    const emoji = "👍".repeat(21);
    expect(emoji.length).toBe(42);
    expect(profileNameLength(emoji)).toBe(21);
    expect(profileNameExceeds(emoji, PREFERRED_NAME_MAX_LENGTH)).toBe(false);

    // And it is still a bound: code points past it are refused.
    const tooMany = "👍".repeat(PREFERRED_NAME_MAX_LENGTH + 1);
    expect(profileNameExceeds(tooMany, PREFERRED_NAME_MAX_LENGTH)).toBe(true);
    // Exactly at the bound is allowed, padded or not.
    const exact = "👍".repeat(PREFERRED_NAME_MAX_LENGTH);
    expect(profileNameExceeds(exact, PREFERRED_NAME_MAX_LENGTH)).toBe(false);
    expect(profileNameExceeds(`  ${exact}  `, PREFERRED_NAME_MAX_LENGTH)).toBe(
      false,
    );
  });

  test("neither input truncates what the user typed", () => {
    // Slicing the raw value to the bound dropped its last character whenever a
    // space led it, silently.
    const dialog = source("components/sidebar/ProfileDetailsDialog.tsx");
    expect(dialog).not.toContain("slice(0, 60)");
    expect(dialog).not.toContain("slice(0, PREFERRED_NAME_MAX_LENGTH)");
    expect(dialog).not.toContain("maxLength=");
  });

  test("both save paths refuse an over-long name and say so", () => {
    const menu = source(MENU);
    expect(menu).toContain(
      "profileNameExceeds(nameValue, DISPLAY_NAME_MAX_LENGTH)",
    );
    expect(menu).toContain(
      "profileNameExceeds(preferredNameValue, PREFERRED_NAME_MAX_LENGTH)",
    );
    expect(menu).toContain("settings.profile.display_name_too_long");
    expect(menu).toContain("settings.profile.preferred_name_too_long");
    expect(menu).toContain("normalizeProfileName(nameValue)");
    expect(menu).toContain("normalizeProfileName(preferredNameValue)");

    for (const locale of ["en", "es-419"]) {
      const catalog = JSON.parse(source(`public/locales/${locale}/common.json`));
      for (const key of [
        "display_name_too_long",
        "preferred_name_too_long",
      ]) {
        expect(typeof catalog.settings.profile[key]).toBe("string");
        expect(catalog.settings.profile[key]).toContain("{{count}}");
      }
    }
  });

  test("leaving an edit takes the refusal with it", () => {
    // The error renders beside the field in read mode too, so an exit that only
    // flipped the mode left "Keep this to 40 characters or fewer." pinned under
    // a value that had nothing wrong with it. On the sheet path nothing could
    // clear it for the rest of the session.
    const menu = source(MENU);
    const dialog = source("components/sidebar/ProfileDetailsDialog.tsx");

    for (const stop of ["stopEditingName", "stopEditingPreferredName"]) {
      const body = menu.slice(
        menu.indexOf(`const ${stop} = useCallback`),
        menu.indexOf("}, []);", menu.indexOf(`const ${stop} = useCallback`)),
      );
      expect(body).toContain("(false)");
      expect(body).toContain("(null)");
    }
    // No exit path sets the mode without going through the pair above.
    expect(dialog).not.toContain("setEditingName(false)");
    expect(dialog).not.toContain("setEditingPreferredName(false)");
    expect(menu).not.toContain("      setEditingName(false);\n      return;");
    expect(menu).not.toContain(
      "      setEditingPreferredName(false);\n      return;",
    );
  });

  test("closing the dialog does not leave a cleared box to confirm later", () => {
    // Clearing the box, closing with the X, then reopening showed an empty
    // input claiming the name was gone; pressing Enter there sent the clear.
    const menu = source(MENU);
    const close = menu.slice(
      menu.indexOf("const closeProfileModal = useCallback"),
      menu.indexOf("setActiveModal(null);", menu.indexOf("const closeProfileModal")),
    );

    expect(close).toContain("stopEditingName()");
    expect(close).toContain("stopEditingPreferredName()");
    expect(close).toContain('setNameValue("")');
    expect(close).toContain('setPreferredNameValue("")');
  });

  test("a save in flight cannot reach the edit that replaced it", () => {
    // Closing the dialog does not cancel a request already on the wire, and the
    // sheet keeps the menu mounted underneath. A late failure pinned an error on
    // a field nobody was editing; a late success dismissed a fresh edit.

    // Every surface that waits on a save captures the edit it belongs to, and
    // ending that edit bumps it, so those captures stop matching.
    for (const file of WRITERS) {
      const awaited = saveCalls(file.text).filter((call) => call.awaited);
      const captures =
        file.text.match(/const session = editSessionRef\.current;/g) ?? [];
      expect(captures.length).toBe(awaited.length);
      if (awaited.length > 0) {
        expect(file.text).toContain("editSessionRef.current += 1");
      }
    }

    const menu = source(MENU);
    expect(saveCalls(menu).filter((call) => call.awaited).length).toBeGreaterThanOrEqual(4);
    const close = menu.slice(
      menu.indexOf("const closeProfileModal = useCallback"),
      menu.indexOf("setActiveModal(null);", menu.indexOf("const closeProfileModal")),
    );
    expect(close).toContain("editSessionRef.current += 1");
    // Including the in-flight flags, or a reopened dialog would stay disabled.
    expect(close).toContain("setIsSavingName(false)");
    expect(close).toContain("setIsSavingPreferredName(false)");

    // Every edit-local write after an await is guarded.
    for (const guarded of [
      "if (isCurrentEditSession(session)) stopEditingName();",
      "if (isCurrentEditSession(session)) stopEditingPreferredName();",
      "if (isCurrentEditSession(session)) setIsSavingName(false);",
      "if (isCurrentEditSession(session)) setIsSavingPreferredName(false);",
    ]) {
      expect(menu).toContain(guarded);
    }

    // The propagation is not gated on the edit session: a save that outlived its
    // dialog still happened. Ordering is the next test's job.
    expect(menu).not.toContain("if (isCurrentEditSession(session)) applyPatchedProfile");
  });

  test("profile requests cannot interleave", () => {
    // Three rounds tried to reconcile the interleaving: an edit-session guard,
    // then a whole-response generation. Both reconciled after the fact and both
    // left a hole, because request issue order is not server commit order and a
    // whole-user snapshot cannot be merged field by field without a generation
    // per field. One request at a time removes the interleaving instead.
    const menu = source(MENU);
    const writePath = source(WRITE_PATH);

    // The queue belongs to the tab rather than to one component, so every
    // surface shares it. Its order is exercised in profile-writes.test.ts.
    expect(menu).not.toMatch(/\b(?:getMe|patchMe)\(/);
    expect(menu).toContain("readProfile()");
    expect(menu).not.toContain("profileRequestChainRef");

    // The chain advances past a rejection, or one failed save would wedge every
    // later one behind it.
    const chain = writePath.slice(
      writePath.indexOf("export function serializeProfileRequest"),
      writePath.indexOf("return queued;"),
    );
    expect(chain).toContain("profileRequestChain.then(request, request)");
    expect(chain).toContain("() => undefined,");

    // And the reconciliation the queue replaces is gone, not merely bypassed.
    expect(menu).not.toContain("appliedMutationRef");
    expect(menu).not.toContain("profileMutationRef");
  });

  test("the bound has one frontend home", () => {
    // Two exported copies is the shape the finding is about; only the one in
    // profile-names.ts is pinned against the backend.
    expect(source("lib/argus-api.ts")).not.toContain("PREFERRED_NAME_MAX_LENGTH");
  });

  test("the frontend bound matches the backend's", () => {
    const schemas = readFileSync(
      join(root, "../src/argus/api/schemas.py"),
      "utf-8",
    );
    expect(schemas).toContain(
      `PREFERRED_NAME_MAX_LENGTH = ${PREFERRED_NAME_MAX_LENGTH}`,
    );
    // And the backend normalizes before it measures, or the two disagree on
    // exactly the padded case above.
    expect(schemas).toContain("BeforeValidator(_blank_preferred_name_is_no_name)");
  });
});
