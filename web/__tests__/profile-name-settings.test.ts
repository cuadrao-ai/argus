import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const root = join(import.meta.dir, "..");

function source(relativePath: string) {
  return readFileSync(join(root, relativePath), "utf-8");
}

test("the settings field is separate from display name", () => {
    // display_name is an identity field people fill with a legal name.
    // Perfil edits both names in place through ProfileNameFields.
    const dialog = source("components/sidebar/ProfileNameFields.tsx");
    const menu = source("components/sidebar/ProfileMenu.tsx");
    const en = JSON.parse(source("public/locales/en/common.json"));
    const es = JSON.parse(source("public/locales/es-419/common.json"));

    expect(dialog).toContain("settings.profile.preferred_name");
    expect(dialog).toContain("profile-preferred-name");
    expect(menu).toContain(
      "saveProfile({ preferred_name: trimmed || null }, applyPatchedProfile)",
    );
    expect(menu).toContain(
      "saveProfile({ display_name: trimmed }, applyPatchedProfile)",
    );
    // Blank clears it, which is how a user opts out after opting in.
    expect(en.settings.profile.preferred_name).toBe(
      "What should we call you?",
    );
    for (const catalog of [en, es]) {
      for (const key of [
        "preferred_name",
        "preferred_name_placeholder",
        "preferred_name_unset",
        "preferred_name_save_error",
      ]) {
        expect(typeof catalog.settings.profile[key]).toBe("string");
      }
      expect(catalog.settings.profile.preferred_name).not.toBe(
        catalog.settings.profile.display_name,
      );
    }
  });
