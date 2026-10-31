"use client";

import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { setBusinessEmailSender } from "@/lib/business-api";
import type { BusinessEmailDelivery, BusinessEmailInboxGroup } from "@/lib/business-email";
import { useBusiness } from "./BusinessWorkspace";
import { dangerButtonClass, primaryButtonClass } from "./business-ui";
import styles from "./recepcion/reception.module.css";

/** The remitentes group when the server sent one with rows. Anything else is no group. */
export function remitentesNuevosItems(groups: readonly BusinessEmailInboxGroup[] | null | undefined): BusinessEmailDelivery[] {
  const items = groups?.find((group) => group.id === "remitentes_nuevos")?.items;
  return items && items.length > 0 ? [...items] : [];
}

/**
 * Unknown senders, above the Bandeja rows. The owner can authorize or block
 * the address. A grantee sees the same rows with no actions.
 */
export default function RemitentesNuevos({ items }: { items: readonly BusinessEmailDelivery[] }) {
  const { t } = useTranslation();
  const { chosen, source, emailInboxRefresh } = useBusiness();
  const owner = chosen?.role === "owner";
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [failedId, setFailedId] = useState<string | null>(null);
  const pending = useRef<string | null>(null);
  if (items.length === 0) return null;
  const send = source.setEmailSender ?? setBusinessEmailSender;
  const act = async (item: BusinessEmailDelivery, status: "authorized" | "blocked") => {
    if (!item.sender || pending.current) return;
    pending.current = item.id;
    setPendingId(item.id);
    setFailedId((current) => (current === item.id ? null : current));
    try {
      await send({ kind: "address", value: item.sender, status });
      await emailInboxRefresh?.refresh();
    } catch {
      setFailedId(item.id);
    } finally {
      if (pending.current === item.id) pending.current = null;
      setPendingId((current) => (current === item.id ? null : current));
    }
  };
  return (
    <section className={styles.remitentes} aria-labelledby="remitentes-nuevos-title" data-testid="remitentes-nuevos">
      <h3 id="remitentes-nuevos-title" className={styles.remitentesTitle}>{t("business.inbox.remitentes_nuevos", "New senders")}</h3>
      <ul className={styles.remitentesList}>
        {items.map((item) => {
          const busy = pendingId === item.id;
          return (
            <li key={item.id} className={styles.remitente} data-testid="remitente-nuevo-row">
              <span className={styles.remitenteIdentity}>
                <span className={styles.remitenteDot} aria-hidden="true" />
                <span className={styles.remitenteLabel}>{t("business.inbox.remitente_nuevo", "New sender")}</span>
                <span className={styles.remitenteSender}>{item.sender || t("business.email.no_sender", "Sender unavailable")}</span>
              </span>
              {item.notice ? <span className={styles.remitenteNotice}>{item.notice}</span> : null}
              {owner ? (
                <span className={styles.remitenteActions}>
                  <button type="button" className={primaryButtonClass} disabled={busy || !item.sender} onClick={() => void act(item, "authorized")}>{t("business.inbox.authorize_sender", "Authorize sender")}</button>
                  <button type="button" className={dangerButtonClass} disabled={busy || !item.sender} onClick={() => void act(item, "blocked")}>{t("business.inbox.block_sender", "Block")}</button>
                </span>
              ) : null}
              {failedId === item.id ? <p role="alert" className={styles.remitenteError}>{t("business.inbox.sender_action_failed", "We couldn't update this sender.")}</p> : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
