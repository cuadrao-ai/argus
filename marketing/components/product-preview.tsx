"use client";

import { useRef, useState, type KeyboardEvent } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  CircleDashed,
  FileText,
  Link2,
  Receipt,
  RotateCcw,
  X,
} from "lucide-react";
import { siteCopy } from "./site-copy";
import type { BusinessLocale } from "./content";
import { formatSampleMoney, sampleInvoiceStory } from "./sample-data";
import styles from "./business.module.css";

const example = sampleInvoiceStory;
type StoryStep = 0 | 1 | 2;
const storySteps: StoryStep[] = [0, 1, 2];

export function ProductPreview({ locale }: { locale: BusinessLocale }) {
  const c = siteCopy[locale];
  const [step, setStep] = useState<StoryStep>(0);
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const document = useRef<HTMLDialogElement>(null);
  const documentTrigger = useRef<HTMLButtonElement>(null);
  const money = (value: number) => formatSampleMoney(value, locale);
  const paid = step > 0 ? example.payment : 0;
  const remaining = example.invoice.amount - paid;

  function onKey(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const next =
      event.key === "ArrowDown" || event.key === "ArrowRight"
        ? (index + 1) % 3
        : event.key === "ArrowUp" || event.key === "ArrowLeft"
          ? (index + 2) % 3
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? 2
              : null;
    if (next === null) return;
    event.preventDefault();
    setStep(next as StoryStep);
    buttons.current[next]?.focus();
  }

  return (
    <>
    <section
      className={styles.story}
      id="la-idea"
      aria-labelledby="story-title"
    >
      <div className={styles.storyIntro}>
        <p className={styles.sectionIndex}>
          04 / {c.replayLabel}
        </p>
        <h2 id="story-title">{c.storyTitle}</h2>
        <p>{c.replayBody}</p>
      </div>
      <div className={styles.storyTabs} role="tablist" aria-label={c.explore}>
        {storySteps.map((index) => (
          <button
            key={c.storySteps[index].title}
            type="button"
            role="tab"
            id={`record-tab-${index}`}
            aria-selected={step === index}
            aria-controls="record-panel"
            tabIndex={step === index ? 0 : -1}
            ref={(node) => {
              buttons.current[index] = node;
            }}
            onKeyDown={(event) => onKey(event, index)}
            onClick={() => setStep(index)}
          >
            <span className={styles.tabNumber}>
              {String(index + 1).padStart(2, "0")}
            </span>
            <span>
              <strong>{c.storySteps[index].title}</strong>
              <span className={styles.tabDescription}>{c.storySteps[index].body}</span>
            </span>
            <ArrowUpRight size={20} aria-hidden="true" />
          </button>
        ))}
      </div>
      <div className={styles.recordStage}>
        <div
          className={styles.record}
          id="record-panel"
          role="tabpanel"
          aria-labelledby={`record-tab-${step}`}
          tabIndex={0}
          data-step={step}
        >
          <div className={styles.recordTop}>
            <div className={styles.recordIdentity}>
              <span>cuadrao</span>
              <span>{c.invoice} {example.invoice.id}</span>
            </div>
            <span className={styles.recordStatus}>
              {step === 0 ? (
                <CircleDashed size={13} aria-hidden="true" />
              ) : (
                <Check size={13} aria-hidden="true" />
              )}{" "}
              {c.status[step]}
            </span>
          </div>
          <div className={styles.invoiceIdentity}>
            <div className={styles.recordTitle}>
              <span>{example.customerName}</span>
              <span>{c.customer}</span>
            </div>
            <p className={styles.recordAmount}>{money(example.invoice.amount)}</p>
            <p className={styles.recordTotalLabel}>{c.total}</p>
            <div className={styles.invoiceItem}>
              <span>{c.item}</span>
              <span>{c.invoice} {example.invoice.id}</span>
            </div>
          </div>
          <div className={styles.paymentPocket}>
            <div className={styles.paymentPlaceholder} aria-hidden={step !== 0}>
              <Receipt size={20} aria-hidden="true" />
              <span>{c.noPayment}</span>
            </div>
            <div className={styles.paymentSlip} aria-hidden={step === 0}>
              <div className={styles.receiptTop}>
                <span><Receipt size={15} aria-hidden="true" />{c.receipt}</span>
                <Check size={15} aria-hidden="true" />
              </div>
              <div className={styles.paymentRow}>
                <span>{c.payment}</span>
                <strong>{money(paid)}</strong>
              </div>
              <div className={styles.receiptLink}>
                <Link2 size={13} aria-hidden="true" />
                <span>{c.linkedTo} {c.invoice.toLocaleLowerCase()} {example.invoice.id}</span>
              </div>
            </div>
          </div>
          <div className={styles.balanceBlock}>
            <div className={styles.balanceHeading}>
              <span>{c.pending}</span>
              <strong>{money(remaining)}</strong>
            </div>
            <div className={styles.progressTrack}>
              <span
                style={{
                  transform: `scaleX(${paid / example.invoice.amount})`,
                }}
              />
            </div>
            <div className={styles.balanceLegend}>
              <span>
                {c.received} ·{" "}
                {new Intl.NumberFormat(locale === "es" ? "es-DO" : "en-US", {
                  maximumFractionDigits: 1,
                }).format((paid / example.invoice.amount) * 100)}
                %
              </span>
              <span>{c.calculation}</span>
            </div>
            <p className={styles.balanceEquation} aria-hidden={step !== 2}>
              {money(example.invoice.amount)} − {money(paid)} = {money(remaining)}
            </p>
          </div>
          <button
            ref={documentTrigger}
            type="button"
            className={styles.documentLink}
            onClick={() => document.current?.showModal()}
          >
            <FileText size={17} aria-hidden="true" />
            <span>
              {c.source}
              <small>factura-{example.invoice.id}.pdf</small>
            </span>
            <span>{c.document}</span>
            <ArrowUpRight size={16} aria-hidden="true" />
          </button>
        </div>
        <div className={styles.recordCaption}>
          <p aria-live="polite" aria-atomic="true">
            {c.explanation[step]}
          </p>
          <button
            type="button"
            onClick={() => setStep(((step + 1) % 3) as StoryStep)}
          >
            <span>{c.nextActions[step]}</span>
            {step === 2 ? <RotateCcw size={17} aria-hidden="true" /> : <ArrowRight size={17} aria-hidden="true" />}
          </button>
        </div>
        <p className={styles.illustrationNote}>{c.note}</p>
      </div>
      <dialog
        aria-labelledby="sample-document-title"
        ref={document}
        className={styles.documentDialog}
        onClose={() => documentTrigger.current?.focus()}
        onClick={(event) => {
          if (event.target === event.currentTarget) document.current?.close();
        }}
      >
        <div className={styles.documentSheet}>
          <button
            type="button"
            className={styles.dialogClose}
            onClick={() => document.current?.close()}
            aria-label={c.closeDocument}
          >
            <X size={22} />
          </button>
          <p className={styles.wordmark}>cuadrao</p>
          <p className={styles.documentDisclaimer}>{c.sampleDocument}</p>
          <h3 id="sample-document-title">
            {c.invoice} {example.invoice.id}
          </h3>
          <p>{example.customerName}</p>
          <p className={styles.documentDisclaimer}>{c.customer}</p>
          <div className={styles.documentItem}>
            <span>{c.item}</span>
            <strong>{money(example.invoice.amount)}</strong>
          </div>
          <div className={styles.documentItem}>
            <span>{c.total}</span>
            <strong>{money(example.invoice.amount)}</strong>
          </div>
          <p className={styles.documentDisclaimer}>{c.note}</p>
        </div>
      </dialog>
    </section>
    </>
  );
}
