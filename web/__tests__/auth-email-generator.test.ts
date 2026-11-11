import { expect, test } from "bun:test";
import { createHash } from "node:crypto";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, unlinkSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { AUTH_TEMPLATE_SLOTS, buildDashboardAuthPaste } from "../server/emails/auth-paste";

const root = resolve(import.meta.dir, "../..");

test("registry renders environment-neutral Auth slots with only the approved copy removals", async () => {
  const before = process.env.CUADRAO_EMAIL_ASSET_ORIGIN;
  process.env.CUADRAO_EMAIL_ASSET_ORIGIN = "https://different.example.test";
  try {
    const records = await buildDashboardAuthPaste();
    expect(records.map(record => record.file)).toEqual([
      "confirmation", "magic_link", "recovery", "invite", "email_change", "reauthentication",
      "password_changed_notification", "email_changed_notification",
    ]);
    expect(records.map(record => record.file)).toEqual(Object.keys(AUTH_TEMPLATE_SLOTS));
    for (const record of records) {
      expect(record.html).toContain("https://cuadrao.ai/email/wordmark-light.png");
      expect(record.html).not.toContain("different.example.test");
      expect(record.text).not.toMatch(/synthetic|undefined|2026|example\.test/);
      expect(record.html).not.toContain("<!-- Generated");
      expect(record.html).toContain('class="card"');
      expect(record.html).toContain('background:#ffffff;border-radius:12px');
      expect(record.html).toContain('padding:24px 32px;background:#172b26;');
    }
    const greeting = '<p class="copy" style="margin:0 0 20px;color:#172b26;font-size:16px;line-height:24px">Hola,</p>';
    const signOff = '<p class="copy" style="margin:0 0 12px;color:#172b26;font-size:16px;line-height:24px">Saludos,<br>Cuadrao</p>';
    const oldSafetyCopy = "Cuadrao nunca te pedirá tu contraseña ni tus códigos.";
    const safetyCopy = "Nunca te pediremos tu contraseña ni tus códigos de acceso por correo o por teléfono. Escríbelos solo en app.cuadrao.ai.";
    const oldContactCopy = "Si no fuiste tú, escríbenos de inmediato respondiendo a este correo para recuperar tu cuenta.";
    const contactCopy = "Si no fuiste tú, escríbenos de inmediato a hola@cuadrao.ai para recuperar tu cuenta.";
    const historicalDigests = {
      "confirmation": "63843850cfcc195f328b1118d2fa14462ae320e0543474d9b1cb87fb8771736c",
      "magic_link": "8a3fd5e39edfb7cc06396cc9ee815eeec4f1ebbd5050e972177d9a4dcd9ae262",
      "recovery": "98727bc6ed3fae215cebc88bbedb9868360b661865fecaaf9007329a41d9d084",
      "invite": "0fea99344a73bcadf492dd92540a39895f4bc3ecc7d11d698230c3125ea76e6e",
      "email_change": "b64b7ce9aa2a20812dccc61016d251adbd621cbb9e6e9689ddbe587f904e9bba",
      "reauthentication": "c5e34cc0715c13ba6f90f2854ac0a90d0bb441428de353b2f4510a647f515fb6",
      "password_changed_notification": "9818bba8bab6d15a3e85d4b9aa41bca970f4b6bd4cf3554bc78ba77ce4638595",
      "email_changed_notification": "cbb21e36085499bc57c1fa5696a53aac8199ea0fd8df8742ed904f36d991084b",
    } as const;
    for (const record of records) {
      expect(record.html).not.toContain(">Hola,</p>");
      expect(record.html).not.toContain("Saludos,<br>Cuadrao");
      expect(record.text).not.toContain("Hola,");
      expect(record.text).not.toContain("Saludos,\nCuadrao");
      for (const part of [record.html, record.text]) {
        expect(part).not.toContain(oldSafetyCopy);
        expect(part).not.toContain(oldContactCopy);
        if (record.file === "email_changed_notification") expect(part).toContain(contactCopy);
        if (record.file.endsWith("_notification")) expect(part).toContain(safetyCopy);
      }
      const historicalHtml = record.html.replace(safetyCopy, oldSafetyCopy).replace(contactCopy, oldContactCopy).replace("</h1>", `</h1>${greeting}`)
        .replace('class="footer" style="padding:20px 32px 28px;background:#ffffff">', `class="footer" style="padding:20px 32px 28px;background:#ffffff">${signOff}`);
      const historicalText = record.text.replace(safetyCopy, oldSafetyCopy).replace(contactCopy, oldContactCopy).replace("\n\n", "\n\nHola,\n\n")
        .replace("\n\n¿Necesitas ayuda?", "\n\nSaludos,\nCuadrao\n\n¿Necesitas ayuda?");
      expect(createHash("sha256").update(`${record.subject}\n${historicalHtml}\n${historicalText}`).digest("hex"))
        .toBe(historicalDigests[record.file]);
      if (record.file === "confirmation") {
        expect(createHash("sha256").update(historicalHtml).digest("hex"))
          .toBe("85caa91d4d77aced00f58a6461b76c8212a45a47c702579cd4b969e5ae95fbc8");
      }
    }
    const confirmation = records.find(record => record.file === "confirmation")!;
    const digest = (value: string) => createHash("sha256").update(value).digest("hex");
    expect(digest(`${confirmation.subject}\n`)).toBe("9f6d6beb0209fe97d303d902e9a16d7dccce49715fe5df09ec7ff6dd422cfbaf");
  } finally {
    if (before === undefined) delete process.env.CUADRAO_EMAIL_ASSET_ORIGIN;
    else process.env.CUADRAO_EMAIL_ASSET_ORIGIN = before;
  }
});

test("Auth paste uses a validated expiry for every action", async () => {
  const records = await buildDashboardAuthPaste(60);
  for (const record of records.filter(record => !record.file.endsWith("_notification"))) {
    expect(record.text).toContain("1 minuto");
    expect(record.html).toContain("1 minuto");
  }
  for (const invalid of [0, -1, 1.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1]) {
    await expect(buildDashboardAuthPaste(invalid)).rejects.toThrow("Invalid email expiry");
  }
});

test("hosted notice slots use the real old and new email fields without a made-up send time", async () => {
  const records = await buildDashboardAuthPaste();
  const password = records.find(record => record.file === "password_changed_notification")!;
  const changed = records.find(record => record.file === "email_changed_notification")!;
  expect(password).toMatchObject({
    subjectField: "mailer_subjects_password_changed_notification",
    bodyField: "mailer_templates_password_changed_notification_content",
  });
  expect(changed).toMatchObject({
    subjectField: "mailer_subjects_email_changed_notification",
    bodyField: "mailer_templates_email_changed_notification_content",
  });
  expect(password.text).toContain("La contraseña de tu cuenta de Cuadrao se cambió.");
  for (const part of [changed.html, changed.text]) {
    expect(part).toContain("de {{ .OldEmail }} a {{ .Email }}.");
    expect(part).not.toContain("{{ .NewEmail }}");
  }
  for (const record of [password, changed]) {
    expect(record.text).not.toMatch(/2026|hora de RD|\d{1,2}:\d{2}|\*\*\*/);
    expect(record.html).not.toContain('class="button"');
  }
});

test("one command syncs sources, renders a manifest and detects artifact drift without writing", () => {
  const sync = Bun.spawnSync([process.execPath, "scripts/emails/sync-layout.mjs", "--check"], { cwd: root });
  expect(sync.stderr.toString()).toBe("");
  expect(sync.exitCode).toBe(0);

  const fixture = mkdtempSync(resolve(root, "temp/auth-generator-test-"));
  const destination = resolve(fixture, "output");
  const run = (...extra: string[]) => Bun.spawnSync([process.execPath, "scripts/emails/render-staging-auth.ts", "--output", destination, ...extra], { cwd: fixture });
  try {
    for (const directory of ["scripts/emails", "marketing/lib/email", "web/server/emails", "web/lib", "web/public/locales", "web/argus_display_contract"]) {
      const target = resolve(fixture, directory);
      mkdirSync(dirname(target), { recursive: true });
      cpSync(resolve(root, directory), target, { recursive: true });
    }
    symlinkSync(resolve(root, "web/node_modules"), resolve(fixture, "web/node_modules"), "dir");
    for (const options of [
      ["--expiry-seconds"], ["--expiry-seconds", "NaN"], ["--expiry-seconds", "Infinity"],
      ["--expiry-seconds", "1.5"], ["--expiry-seconds", "0"], ["--expiry-seconds", "-1"],
      ["--expiry-seconds", "abc"], ["--expiry-seconds", "9007199254740992"],
      ["--expiry-seconds", "0x3c"], ["--expiry-seconds", ""],
      ["--unknown"], ["unexpected"], ["--output"], ["--check=maybe"],
    ]) {
      expect(run(...options).exitCode).not.toBe(0);
      expect(existsSync(destination)).toBe(false);
    }
    expect(run().exitCode).toBe(0);
    const manifest = JSON.parse(readFileSync(resolve(destination, "manifest.json"), "utf8"));
    expect(manifest.expirySeconds).toBe(3600);
    expect(manifest.generated).toContain("Do not edit");
    expect(manifest.templates).toHaveLength(Object.keys(AUTH_TEMPLATE_SLOTS).length);
    for (const entry of manifest.templates) {
      for (const artifact of [entry.html, entry.subject, entry.text]) expect(readFileSync(resolve(destination, artifact), "utf8").length).toBeGreaterThan(0);
    }
    expect(run("--check").exitCode).toBe(0);
    expect(run("--expiry-seconds", "60").exitCode).toBe(0);
    expect(JSON.parse(readFileSync(resolve(destination, "manifest.json"), "utf8")).expirySeconds).toBe(60);
    expect(readFileSync(resolve(destination, "confirmation.html"), "utf8")).toContain("1 minuto");
    expect(run("--expiry-seconds", "60", "--check").exitCode).toBe(0);
    expect(run("--check").exitCode).not.toBe(0);
    expect(readFileSync(resolve(destination, "confirmation.html"), "utf8")).toContain("1 minuto");
    expect(run().exitCode).toBe(0);
    const path = resolve(destination, "confirmation.subject.txt");
    writeFileSync(path, "stale\n");
    const stale = run("--check");
    expect(stale.exitCode).not.toBe(0);
    expect(stale.stderr.toString()).toContain("confirmation.subject.txt");
    expect(readFileSync(path, "utf8")).toBe("stale\n");

    unlinkSync(path);
    const missing = run("--check");
    expect(missing.exitCode).not.toBe(0);
    expect(missing.stderr.toString()).toContain("confirmation.subject.txt");
    expect(existsSync(path)).toBe(false);

    expect(run().exitCode).toBe(0);
    const generated = resolve(fixture, "web/server/emails/account-layout.generated.ts");
    writeFileSync(generated, "stale source\n");
    const staleSource = run("--check");
    expect(staleSource.exitCode).not.toBe(0);
    expect(staleSource.stderr.toString()).toContain("Shared email layout copy is stale");
    expect(readFileSync(generated, "utf8")).toBe("stale source\n");
  } finally { rmSync(fixture, { recursive: true, force: true }); }
});

test("hosted settings contain the versioned sender, rate and pilot notice values only", () => {
  const settings = JSON.parse(readFileSync(resolve(root, "scripts/emails/auth-hosted-settings.json"), "utf8"));
  const config = Bun.TOML.parse(readFileSync(resolve(root, "supabase/config.toml"), "utf8")) as { auth: { email: { notification: Record<string, { enabled: boolean }> } } };
  for (const notice of ["password_changed", "email_changed", "phone_changed"]) {
    expect(settings[`mailer_notifications_${notice}_enabled`]).toBe(config.auth.email.notification[notice].enabled);
  }
  expect(settings).toEqual({
    smtp_sender_name: "Cuadrao",
    rate_limit_email_sent: 30,
    mailer_notifications_password_changed_enabled: true,
    mailer_notifications_email_changed_enabled: true,
    mailer_notifications_phone_changed_enabled: false,
  });
});
