// Operator tool for Cuadrao early-access signups.
//   bun run scripts/signups.ts summary
//   bun run scripts/signups.ts remove someone@example.com
//   bun run scripts/signups.ts notice --template notice.json            (dry run)
//   bun run scripts/signups.ts notice --template notice.json --only a@x.com,b@y.com --send
//   bun run scripts/signups.ts notice --template notice.json --send --expect 42
// Needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY; notice also needs
// RESEND_API_KEY and CUADRAO_NOTICE_FROM. Nothing here prints an address.
import { readFileSync } from "node:fs";
import { readFormsConfig } from "../lib/forms/config";
import {
  pendingSignups,
  planNotice,
  removeSignup,
  sendNotice,
  signupCounts,
  validateTemplate,
  type NoticeTemplate,
  type OpsConfig,
} from "../lib/ops/signups";

function option(args: string[], name: string): string | null {
  const index = args.indexOf(`--${name}`);
  return index >= 0 ? (args[index + 1] ?? null) : null;
}

function fail(message: string): never {
  console.error(message);
  process.exit(1);
}

const [command, ...args] = process.argv.slice(2);
const config: OpsConfig = {
  ...readFormsConfig(process.env),
  noticeFrom: process.env.CUADRAO_NOTICE_FROM?.trim() || null,
};
if (!config.supabaseUrl || !config.supabaseServiceKey) {
  fail("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required.");
}

if (command === "summary") {
  console.log(JSON.stringify(await signupCounts(config, fetch)));
} else if (command === "remove") {
  const email = args[0];
  if (!email) fail("Usage: remove <email>");
  console.log(`Signup ${await removeSignup(config, email, fetch)}.`);
} else if (command === "notice") {
  const path = option(args, "template");
  if (!path) fail("--template <file.json> is required.");
  const template = JSON.parse(readFileSync(path, "utf8")) as NoticeTemplate;
  const problems = validateTemplate(template);
  if (problems.length) fail(`Template problems:\n- ${problems.join("\n- ")}`);
  const only = option(args, "only")?.split(",").map((value) => value.trim()).filter(Boolean) ?? null;
  const plan = planNotice(await pendingSignups(config, fetch), only);
  const byLanguage = { es: 0, en: 0 };
  for (const row of plan.recipients) byLanguage[row.language] += 1;
  console.log(
    JSON.stringify({ template: template.id, recipients: plan.recipients.length, byLanguage, stamps: plan.stamp }),
  );
  if (!args.includes("--send")) {
    console.log("Dry run. Nothing was sent. Add --send to send.");
  } else {
    const expected = option(args, "expect");
    if (!only && Number(expected) !== plan.recipients.length) {
      fail(`A full send needs --expect ${plan.recipients.length} to confirm the recipient count.`);
    }
    if (!config.resendApiKey || !config.noticeFrom) fail("RESEND_API_KEY and CUADRAO_NOTICE_FROM are required to send.");
    const result = await sendNotice(config, template, plan, fetch);
    console.log(JSON.stringify(result));
    if (result.unknownOutcome.length > 0) {
      const prefix = plan.stamp ? "notice" : "notice-test";
      console.error(
        (plan.stamp
          ? "These rows stay claimed and may or may not have been mailed. "
          : "Test send, nothing was claimed. These addresses may or may not have been mailed. ") +
          `Check each in Resend by its idempotency key (${prefix}-<template id>-<digest>) before anything else:\n` +
          result.unknownOutcome.join("\n"),
      );
    }
    if (result.claimUncertain.length > 0) {
      console.error(
        "A claim got no usable answer, so each of these rows is either claimed (notified_at set, never mailed) or not claimed (notified_at empty). Check notified_at for each digest. If it is empty, the claim did not save: do NOT send by hand, a rerun will send it. If it is set, the row is claimed and may be unsent: check Resend by the idempotency key (notice-<template id>-<digest>) first, because a second notice run may already have mailed it, then send it by hand if it was not; a rerun will skip it. Run only one notice at a time:\n" +
          result.claimUncertain.join("\n"),
      );
    }
    if (result.releaseFailed.length > 0) {
      console.error(
        "The provider refused these rows (nothing was sent) but the claim could not be released, so they stay claimed and a rerun will skip them. First check notified_at for each digest. If it is empty, the release did save: a rerun will send it, so do not send by hand. If it is set, clear it to try again, or send by hand and leave it set:\n" +
          result.releaseFailed.join("\n"),
      );
    }
    if (result.stoppedEarly) {
      console.error(
        result.claimUncertain.length > 0
          ? "Stopped: the database did not confirm a claim, so nothing further was sent. Fix the database and rerun; claimed rows are not repeated."
          : plan.stamp
            ? "Stopped: a send had no usable answer, so nothing further was sent. Check the unknown-outcome row printed above in Resend, fix the cause and rerun; claimed rows are not repeated."
            : "Stopped: a test send had no usable answer, so nothing further was sent. A test send claims nothing, so a rerun mails every test address again; Resend's key blocks a duplicate only for 24 hours. Check the unknown-outcome address printed above in Resend first.",
      );
    }
    if (result.failed > 0 || result.unknownOutcome.length > 0 || result.releaseFailed.length > 0 || result.claimUncertain.length > 0 || result.stoppedEarly) process.exit(1);
  }
} else {
  fail("Commands: summary | remove <email> | notice --template <file> [--only a,b] [--send] [--expect N]");
}
