"use client";

import { useCallback, useRef, useState, type CSSProperties } from "react";
import { CHAT_DONE, CHAT_SHARE, activeStep, chatAt, chatStage } from "@/lib/landing-timeline";
import { NARROW_WIDTH, clamp } from "@/lib/scene-timeline";
import styles from "./how-it-works.module.css";
import { landingCopy, type LandingLocale } from "./landing-copy";
import { PhoneChat } from "./phone-chat";
import { STEPS_TRACK, scrollToStep } from "./scroll-to-step";
import { useDemoDates } from "./use-demo-dates";
import { useScrollFrame, type ScrollFrame } from "./use-scroll-frame";

const PHONE_WIDTH = 420;
const PHONE_HEIGHT = 880;

const reveal = (order: number) => ({ "--i": order }) as CSSProperties;

export function HowItWorks({ locale }: { locale: LandingLocale }) {
  const copy = landingCopy[locale].how;
  const dates = useDemoDates(locale);
  const track = useRef<HTMLDivElement>(null);
  const steps = useRef<HTMLDivElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const phoneFit = useRef<HTMLDivElement>(null);
  const [step, setStep] = useState(0);
  const [chat, setChat] = useState(CHAT_DONE);

  const paint = useCallback(({ width, height, reduced }: ScrollFrame) => {
    const fit = phoneFit.current;
    const box = track.current?.getBoundingClientRect();
    if (!fit || !box || !stage.current) return;
    const narrow = width <= NARROW_WIDTH;
    const room = narrow
      ? (fit.parentElement?.clientWidth ?? width) - 40
      : stage.current.clientHeight - 40;
    const scale = narrow ? Math.min(1, room / PHONE_WIDTH) : Math.min(0.92, room / PHONE_HEIGHT);
    fit.style.setProperty("--pk", String(scale));
    fit.style.setProperty("--ph", `${Math.round(PHONE_HEIGHT * scale)}px`);

    if (narrow) {
      const phone = fit.getBoundingClientRect();
      setChat(chatStage(reduced ? 1 : clamp((height * 0.92 - phone.top) / (phone.height * 0.9))));
      return;
    }
    const travel = box.height - height;
    const share = travel > 0 ? clamp(-box.top / travel) : 1;
    steps.current?.style.setProperty("--t", String(share));
    setStep(activeStep(share));
    setChat(chatStage(reduced ? 1 : clamp(share / CHAT_SHARE)));
  }, []);
  useScrollFrame(paint);

  const panel = (index: number) => `${styles.panel} ${step === index ? styles.on : ""}`;

  return (
    <section className={styles.how} id="como" aria-labelledby="how-title">
      <div className={styles.wrap}>
        <h2 id="how-title">{copy.title}</h2>
        <div ref={track} className={styles.track} {...{ [STEPS_TRACK]: "" }}>
          <div className={styles.pin}>
            <div ref={steps} className={styles.steps}>
              {copy.steps.map((item, index) => (
                <div key={item.title} className={`${styles.step} ${step === index ? styles.stepOn : ""}`}>
                  <h3>
                    <button
                      type="button"
                      aria-current={step === index ? "step" : undefined}
                      onClick={() => scrollToStep(index)}
                    >
                      {item.title}
                    </button>
                  </h3>
                  <p>{item.body}</p>
                </div>
              ))}
            </div>
            <div ref={stage} className={styles.stage}>
              <div className={`${panel(0)} ${styles.phonePanel}`} data-step-panel="0">
                <div ref={phoneFit} className={styles.phoneFit}>
                  <PhoneChat chat={chatAt(chat)} copy={copy.chat} dates={dates} />
                </div>
              </div>

              <div className={panel(1)} aria-hidden={step !== 1} data-step-panel="1">
                <div className={`${styles.sheet} ${styles.reveal}`} style={reveal(0)}>
                  <table>
                    <thead>
                      <tr>
                        {copy.square.columns.map((column) => (
                          <th key={column}>{column}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td>{copy.square.materials[0]}</td>
                        <td>{copy.square.materials[1]}</td>
                        <td>
                          <span className={`${styles.chip} ${styles.chipDone}`}>{copy.square.ready}</span>
                        </td>
                      </tr>
                      <tr>
                        <td>{copy.square.supplier[0]}</td>
                        <td>{copy.square.supplier[1]}</td>
                        <td>
                          <span className={styles.flip}>
                            <span className={`${styles.chip} ${styles.flipOut}`}>
                              <i className={styles.spin} />
                              {copy.square.reading}
                            </span>
                            <span className={`${styles.chip} ${styles.chipDone} ${styles.flipIn}`}>
                              {copy.square.ready}
                            </span>
                          </span>
                        </td>
                      </tr>
                      <tr>
                        <td>{copy.square.fuel[0]}</td>
                        <td>{copy.square.fuel[1]}</td>
                        <td>
                          <span className={`${styles.chip} ${styles.chipAlert}`}>{copy.square.duplicate}</span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div className={`${styles.pay} ${styles.reveal}`} style={reveal(2)}>
                  <div className={styles.payRow}>
                    <b>{copy.square.invoice}</b>
                    <span>{copy.square.invoiceTotal}</span>
                  </div>
                  <div className={styles.payBar}>
                    <i />
                  </div>
                  <div className={`${styles.payRow} ${styles.payNote}`}>
                    <span>{copy.square.collected}</span>
                    <span>{copy.square.pending}</span>
                  </div>
                </div>
              </div>

              <div className={panel(2)} aria-hidden={step !== 2} data-step-panel="2">
                <div className={`${styles.sheet} ${styles.reveal}`} style={reveal(0)}>
                  <table>
                    <thead>
                      <tr>
                        <th>{copy.exporting.columns[0]}</th>
                        <th>{copy.exporting.columns[1]}</th>
                        <th className={styles.num}>{copy.exporting.columns[2]}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {copy.exporting.rows.map(([rnc, ncf, amount], index) => (
                        <tr key={ncf} className={styles.reveal} style={reveal(index + 1)}>
                          <td>{rnc}</td>
                          <td>{ncf}</td>
                          <td className={styles.num}>{amount}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div className={`${styles.exportRow} ${styles.reveal}`} style={reveal(4)}>
                    <span>
                      {dates.month} · {copy.exporting.form}
                    </span>
                    <span className={styles.exportButton}>{copy.exporting.action}</span>
                  </div>
                </div>
              </div>

              <div className={panel(3)} aria-hidden={step !== 3} data-step-panel="3">
                <div className={`${styles.sheet} ${styles.reveal}`} style={reveal(0)}>
                  <span className={`${styles.chip} ${styles.chipWait} ${styles.later}`}>{copy.billing.status}</span>
                  <table>
                    <tbody>
                      {copy.billing.rows.map(([name, value]) => (
                        <tr key={name}>
                          <td>{name}</td>
                          <td className={styles.num}>
                            <b>{value}</b>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className={styles.billingNote}>{copy.billing.note}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
