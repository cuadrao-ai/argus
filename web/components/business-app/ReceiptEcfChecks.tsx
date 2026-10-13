"use client";

import { AlertCircle, CheckCircle2, CircleDashed, ExternalLink } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { DgiiQr, EcfCheck, EcfVerification } from "@/lib/business-dossier";
import { formatRelativeTime } from "./business-format";
import { cardClass, secondaryButtonClass } from "./business-ui";

/**
 * What the e-CF file proved by itself, as five rows: the signature, the totals,
 * the read, the certificate and DGII. Each row has a title, a caption colored
 * by its state and when it was checked. The words never overreach: a verified
 * signature says the content has not changed since it was signed, never who
 * signed; the certificate naming the issuer's RNC is not proven identity while
 * its issuer is unchecked; DGII acceptance is never claimed. A row to review
 * never blocks approval.
 */

type T = (key: string, fallback: string, options?: Record<string, unknown>) => string;
type RowState = "verified" | "failed" | "not_checked";
export type EcfRow = { key: string; title: string; caption: string; state: RowState; /** Neutral sentences after the caption: facts that carry no state of their own. */ notes?: string[] };

const UNSUPPORTED = new Set(["unsupported_algorithm", "reference_unsupported", "unsupported_transform", "unsupported_key"]);
const DGII_HOSTS = new Set(["fc.dgii.gov.do", "ecf.dgii.gov.do"]);

/** The link as the page will open it, or null: https, exactly a DGII consultation host, no userinfo, no port. The backend is not trusted for this. */
export function dgiiLink(url: string | null | undefined): string | null {
  if (!url) return null;
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return null;
  }
  if (parsed.protocol !== "https:" || !DGII_HOSTS.has(parsed.hostname) || parsed.username || parsed.password || parsed.port) return null;
  return parsed.href;
}

/** A check detail value "read=X qr=Y" as its two values; anything else reads as the whole text. */
function readAndQr(value: string | undefined): { read: string; qr: string } {
  const match = /^read=(.*) qr=(.*)$/.exec(value ?? "");
  return match ? { read: match[1], qr: match[2] } : { read: value ?? "", qr: "" };
}

function stateOf(check: EcfCheck | undefined): RowState {
  return check?.state === "verified" || check?.state === "failed" ? check.state : "not_checked";
}

function reason(code: string | null | undefined, t: T): string {
  if (code === "no_signature") return t("business.dossier.ecf_reason_no_signature", "the file carries no signature");
  if (code === "several_signatures") return t("business.dossier.ecf_reason_several_signatures", "it carries more than one signature");
  if (code && UNSUPPORTED.has(code)) return t("business.dossier.ecf_reason_unsupported", "signature form not supported");
  return t("business.dossier.ecf_reason_unreadable", "the signature could not be read");
}

function window(value: string | undefined, t: T): string {
  if (value === "valid") return t("business.dossier.ecf_window_valid", "valid");
  if (value === "expired") return t("business.dossier.ecf_window_expired", "expired");
  if (value === "not_yet_valid") return t("business.dossier.ecf_window_not_yet", "not yet valid");
  return t("business.dossier.ecf_window_unknown", "not judged");
}

/** The window words are lowercase mid-sentence; the first one opens the sentence. */
function sentence(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** The five rows, from whatever checks the record carries; a missing check reads as not checked. */
export function ecfRows(verification: EcfVerification, t: T): EcfRow[] {
  const by = new Map<string, EcfCheck>();
  const checks = Array.isArray(verification.checks) ? verification.checks : [];
  for (const check of checks) if (check && typeof check.name === "string") by.set(check.name, { ...check, detail: check.detail ?? {} });
  const integrity = by.get("signature_integrity");
  const totals = by.get("totals_arithmetic");
  const read = by.get("read_matches_xml");
  const validity = by.get("certificate_validity");
  const issuer = by.get("certificate_issuer");
  const subject = by.get("subject_rnc");
  const security = by.get("security_code");

  const signature: EcfRow = { key: "signature", title: t("business.dossier.ecf_row_signature", "Signature"), state: stateOf(integrity), caption: "" };
  if (signature.state === "verified") signature.caption = t("business.dossier.ecf_integrity_verified", "Content unchanged since it was signed");
  else if (signature.state === "failed") signature.caption = t("business.dossier.ecf_integrity_failed", "Review: the content changed after it was signed");
  else signature.caption = t("business.dossier.ecf_integrity_not_checked", "Signature not checked: {{reason}}", { reason: reason(integrity?.code, t) });

  const sums: EcfRow = { key: "totals", title: t("business.dossier.ecf_row_totals", "Totals"), state: stateOf(totals), caption: "" };
  if (sums.state === "verified") sums.caption = t("business.dossier.ecf_totals_verified", "The totals add up");
  else if (sums.state === "failed" && totals?.code === "items_mismatch") sums.caption = t("business.dossier.ecf_totals_items_failed", "Review: the lines do not add up to the base (lines {{items}})", { items: totals.detail.sum_of_items ?? "" });
  else if (sums.state === "failed") sums.caption = t("business.dossier.ecf_totals_failed", "Review: the totals do not add up (total {{total}}, sum {{sum}})", { total: totals?.detail.monto_total ?? "", sum: totals?.detail.sum_of_parts ?? "" });
  else sums.caption = t("business.dossier.ecf_totals_not_checked", "Totals not checked");

  const reading: EcfRow = { key: "read", title: t("business.dossier.ecf_row_read", "Read"), state: stateOf(read), caption: "" };
  if (reading.state === "verified") reading.caption = t("business.dossier.ecf_read_verified", "The read matches the XML");
  else if (reading.state === "failed") reading.caption = t("business.dossier.ecf_read_failed", "Review: the read differs from the XML in {{fields}}", { fields: Object.keys(read?.detail ?? {}).map((field) => t(`business.dossier.ecf_field_${field}`, field)).join(", ") });
  else reading.caption = t("business.dossier.ecf_read_not_checked", "Read not compared with the XML");

  // Two facts about the window, the issuer named as unchecked, and the RNC the
  // certificate names, which is not proven identity while its issuer is unchecked.
  // The window is judged only when both facts are there; a verified check
  // without them stays neutral rather than green.
  const judged = (validity?.state === "verified" || validity?.state === "failed") && Boolean(validity.detail.at_signature) && Boolean(validity.detail.today);
  const certificateState: RowState = stateOf(subject) === "failed" ? "failed" : judged ? stateOf(validity) : "not_checked";
  const caption: string[] = [];
  if (judged && validity) {
    const signedAt = validity.detail.signed_at ? ` (${validity.detail.signed_at})` : "";
    caption.push(
      sentence(
        t("business.dossier.ecf_validity_facts", "{{at}} on the date the document declares{{when}}; {{today}} today. Revocation not checked.", {
          at: window(validity.detail.at_signature, t),
          when: signedAt,
          today: window(validity.detail.today, t),
        }),
      ),
    );
  } else {
    caption.push(t("business.dossier.ecf_validity_not_checked", "Certificate validity not checked."));
  }
  if (subject?.state === "failed") caption.push(t("business.dossier.ecf_subject_failed", "Review: the certificate does not name the issuer's RNC ({{serial}}).", { serial: subject.detail.subject_serial ?? "" }));
  // Neutral facts, in a neutral color: no authority is trusted by name, and a
  // named RNC is not proven identity.
  const notes: string[] = [issuer?.detail.issuer ? t("business.dossier.ecf_issuer_not_checked", "Certificate issuer not checked ({{issuer}}).", { issuer: issuer.detail.issuer }) : t("business.dossier.ecf_issuer_unknown", "Certificate issuer not checked.")];
  if (subject?.state === "verified") notes.push(t("business.dossier.ecf_subject_named", "The certificate names the issuer's RNC; that does not prove its identity."));
  const certificate: EcfRow = { key: "certificate", title: t("business.dossier.ecf_row_certificate", "Certificate"), state: certificateState, caption: caption.join(" "), notes };

  const dgii: EcfRow = {
    key: "dgii",
    title: t("business.dossier.ecf_row_dgii", "DGII"),
    state: "not_checked",
    caption: [
      t("business.dossier.ecf_dgii_not_checked", "DGII acceptance not looked up."),
      security?.detail.expected ? t("business.dossier.ecf_security_expected", "Expected security code: {{code}}.", { code: security.detail.expected }) : t("business.dossier.ecf_security_unavailable", "Security code not available."),
    ].join(" "),
  };
  const rows = [signature, sums, reading, certificate, dgii];
  // The QR row exists only for a record whose verification looked for one.
  const present = by.get("qr_present");
  const match = by.get("qr_matches_read");
  if (present || match) {
    const qr: EcfRow = { key: "qr", title: t("business.dossier.ecf_row_qr", "QR code"), state: "not_checked", caption: "" };
    if (stateOf(present) !== "verified") {
      qr.caption = t("business.dossier.ecf_qr_missing", "No readable QR code");
    } else if (stateOf(match) === "verified") {
      qr.state = "verified";
      qr.caption = t("business.dossier.ecf_qr_match", "The QR code matches what was read");
    } else if (stateOf(match) === "failed") {
      qr.state = "failed";
      // Both values, so the person sees what differs without opening anything.
      const pairs = Object.entries(match?.detail ?? {}).map(([field, value]) => {
        const { read, qr: stated } = readAndQr(value);
        return t("business.dossier.ecf_qr_pair", "{{field}}: read {{read}}, QR {{qr}}", { field: t(`business.dossier.ecf_field_${field}`, field), read, qr: stated });
      });
      qr.caption = t("business.dossier.ecf_qr_differs", "Review: the QR code does not match what was read. {{pairs}}", { pairs: pairs.join("; ") });
    } else {
      qr.caption = t("business.dossier.ecf_qr_no_read", "QR code read; nothing read from the receipt to compare it with");
    }
    rows.push(qr);
  }
  return rows;
}

const STATE_STYLE: Record<RowState, { Icon: typeof CheckCircle2; className: string }> = {
  verified: { Icon: CheckCircle2, className: "text-[var(--rui-color-teal)]" },
  failed: { Icon: AlertCircle, className: "text-[var(--rui-color-danger)]" },
  not_checked: { Icon: CircleDashed, className: "text-black/45 dark:text-white/45" },
};

export default function ReceiptEcfChecks({ verification, qr = null }: { verification: EcfVerification | null | undefined; qr?: DgiiQr | null }) {
  const { t, i18n } = useTranslation();
  if (!verification) return null;
  const locale = i18n.resolvedLanguage ?? "en";
  const typeLabel = verification.tipo_ecf ? t(`business.dossier.ecf_type_${verification.tipo_ecf}`, "") : "";
  const document = verification.encf
    ? typeLabel
      ? t("business.dossier.ecf_document", "e-CF {{encf}} · type {{tipo}}, {{label}}", { encf: verification.encf, tipo: verification.tipo_ecf, label: typeLabel })
      : t("business.dossier.ecf_document_untyped", "e-CF {{encf}} · type {{tipo}}", { encf: verification.encf, tipo: verification.tipo_ecf ?? "" })
    : null;
  const when = formatRelativeTime(verification.checked_at ?? null, locale);
  const checkedAt = when ? t("business.dossier.ecf_checked_ago", "checked {{when}}", { when }) : "";
  const link = dgiiLink(qr?.url);
  return (
    <section className={cardClass} aria-labelledby="receipt-ecf-checks-title" data-testid="receipt-ecf-checks">
      <h3 id="receipt-ecf-checks-title" className="text-[14px] font-medium text-black dark:text-white">{t("business.dossier.ecf_title", "Electronic invoice verification")}</h3>
      {document ? <p className="mt-1 text-[13px] text-black/60 dark:text-white/60">{document}</p> : null}
      <ul className="mt-4 divide-y divide-black/[0.05] dark:divide-white/[0.05]">
        {ecfRows(verification, t).map((row) => {
          const { Icon, className } = STATE_STYLE[row.state];
          return (
            <li key={row.key} data-row={row.key} data-state={row.state} className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
              <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${className}`} aria-hidden="true" />
              <span className="min-w-0 flex-1">
                <span className="block text-[14px] font-medium text-black dark:text-white">{row.title}</span>
                <span className={`block text-[13px] ${className}`}>{row.caption}</span>
                {row.notes?.length ? <span className="block text-[13px] text-black/55 dark:text-white/55">{row.notes.join(" ")}</span> : null}
                {checkedAt ? <span className="block text-[12px] text-black/45 dark:text-white/45">{checkedAt}</span> : null}
              </span>
            </li>
          );
        })}
      </ul>
      {link ? (
        <div className="mt-4">
          <a href={link} target="_blank" rel="noopener noreferrer" data-testid="receipt-dgii-verify" className={secondaryButtonClass}>
            <ExternalLink className="h-4 w-4" aria-hidden="true" />
            {t("business.dossier.ecf_qr_verify", "Check on DGII")}
          </a>
          <p className="mt-2 text-[12px] text-black/55 dark:text-white/55">{t("business.dossier.ecf_qr_verify_note", "Opens DGII's official consultation page in a new tab. Cuadrao sends nothing.")}</p>
        </div>
      ) : null}
      <p className="mt-4 text-[12px] text-black/55 dark:text-white/55">{t("business.dossier.ecf_note", "What the file proves by itself. Nothing here confirms DGII accepted the invoice; a row marked Review does not block approval.")}</p>
    </section>
  );
}
