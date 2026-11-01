"use client";

import { useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { CAMPAIGN_DAY, demoDates, demoDayKey, localDayKey } from "@/lib/demo-date";
import { NARROW_WIDTH, beatAt, beatPoint, sceneVars, scrollProgress } from "@/lib/scene-timeline";
import { Icon } from "./icon";
import { landingCopy, type LandingLocale } from "./landing-copy";
import styles from "./scene.module.css";

const MARK = "/cuadrao-site/cuadrao-mark-light.svg";
const FINAL_POINT = 1;

const subscribeToNothing = () => () => {};
const visitorDay = () => demoDayKey(localDayKey(new Date()));
const campaignDay = () => CAMPAIGN_DAY;

const TONE = {
  new: styles.tagNew,
  alert: styles.tagAlert,
  done: styles.tagDone,
} as const;

const INVOICE_TONE = {
  reading: styles.tagWait,
  ready: styles.tagNew,
  approved: styles.tagDone,
} as const;

function Mark({ className }: { className?: string }) {
  // eslint-disable-next-line @next/next/no-img-element
  return <img className={className} src={MARK} alt="" />;
}

export function ProductScene({ locale }: { locale: LandingLocale }) {
  const copy = landingCopy[locale].scene;
  const section = useRef<HTMLElement>(null);
  const frame = useRef<HTMLDivElement>(null);
  const [point, setPoint] = useState(FINAL_POINT);
  const dayKey = useSyncExternalStore(subscribeToNothing, visitorDay, campaignDay);
  const dates = useMemo(() => demoDates(dayKey, locale), [dayKey, locale]);
  const beat = beatAt(point);

  useLayoutEffect(() => {
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let request = 0;
    const paint = () => {
      request = 0;
      const box = section.current?.getBoundingClientRect();
      const stage = frame.current;
      if (!box || !stage) return;
      const { innerWidth: width, innerHeight: height } = window;
      const still = motion.matches || width <= NARROW_WIDTH;
      const p = still ? FINAL_POINT : scrollProgress(box.top, box.height, height);
      for (const [name, value] of Object.entries(sceneVars(p, width, height))) {
        stage.style.setProperty(name, value);
      }
      setPoint(beatPoint(p));
    };
    const schedule = () => {
      if (!request) request = window.requestAnimationFrame(paint);
    };
    paint();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    motion.addEventListener("change", schedule);
    return () => {
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      motion.removeEventListener("change", schedule);
      window.cancelAnimationFrame(request);
    };
  }, []);

  const dock = [
    { icon: "whatsapp", label: copy.dock.receive, stage: 0 },
    { icon: "check", label: copy.dock.square, stage: 1 },
    { icon: null, label: copy.dock.how, stage: -1 },
    { icon: "fileText", label: copy.dock.exportLabel, stage: 2 },
    { icon: "receipt", label: copy.dock.bill, stage: -1 },
  ] as const;

  return (
    <section ref={section} className={styles.scene} aria-label={copy.dock.how}>
      <div className={styles.pin}>
        <div ref={frame} className={styles.frame} data-scene-frame>
          <div className={styles.glow} />
          <div className={styles.board} role="img" aria-label={copy.label}>
            <div className={styles.menubar}>
              <span className={styles.menuBrand}>
                <Mark />
                cuadrao
              </span>
              <span>
                {dates.bar} {copy.time}
              </span>
            </div>
            <div className={styles.island}>
              <span className={styles.islandDot} />
              <span data-scene-island>{copy.island[beat.island]}</span>
            </div>

            <div className={`${styles.win} ${styles.app}`}>
              <div className={styles.side}>
                <div className={styles.biz}>
                  <span className={styles.bizIcon}>
                    <Icon name="briefcase" />
                  </span>
                  {copy.nav.business}
                </div>
                <div className={`${styles.nav} ${styles.navOn}`}>{copy.nav.home}</div>
                <div className={styles.nav}>
                  <span>{copy.nav.inbox}</span>
                  <span
                    className={`${styles.count} ${beat.arrived && beat.invoice === "reading" ? styles.countBump : ""}`}
                    data-scene-count
                  >
                    {beat.arrived ? 5 : 4}
                  </span>
                </div>
                <div className={styles.nav}>{copy.nav.records}</div>
                <div className={styles.nav}>{copy.nav.billing}</div>
                <div className={styles.nav}>{copy.nav.activity}</div>
              </div>
              <div className={styles.main}>
                <div className={styles.tools}>
                  <span className={styles.search}>
                    <Icon name="search" />
                    {copy.search}
                    <kbd>⌘K</kbd>
                  </span>
                  <span className={styles.add}>
                    <span>
                      <Icon name="plus" />
                      {copy.add}
                    </span>
                    <i>
                      <Icon name="caretDown" />
                    </i>
                  </span>
                  <span className={styles.bell}>
                    <Icon name="bell" />
                  </span>
                  <span className={styles.user}>
                    <Icon name="user" />
                  </span>
                </div>
                <p className={styles.date} data-scene-date>
                  {dates.long} · {copy.nav.business}
                </p>
                <p className={styles.title}>{copy.greeting}</p>
                <p className={styles.section}>{copy.summary}</p>
                <div className={styles.grid}>
                  <div className={styles.card}>
                    <div className={styles.cardHead}>
                      <b>{copy.attention}</b>
                      <span className={styles.pill}>5</span>
                      <span className={styles.dim}>{copy.showing(beat.arrived ? 4 : 3)}</span>
                      <span className={styles.link}>{copy.seeAll}</span>
                    </div>
                    <div className={styles.rows}>
                      {copy.attentionRows.map((row, index) => (
                        <div
                          key={row.name}
                          className={`${styles.row} ${index === 0 ? styles.newRow : ""}`}
                        >
                          <span className={styles.rowIcon}>
                            <Icon name={row.icon} />
                          </span>
                          <b>{row.name}</b>
                          <span className={`${styles.tag} ${TONE[row.tone]}`}>
                            {row.tag}
                          </span>
                          <span className={styles.when}>{row.when}</span>
                          <span className={styles.rowLink}>{row.action} ›</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className={styles.card}>
                    <div className={styles.cardHead}>
                      <b>{copy.closeMonth(dates.monthLower)}</b>
                      <span className={`${styles.link} ${styles.dimLink}`}>{copy.missing}</span>
                    </div>
                    <div className={styles.close}>
                      <span className={`${styles.tag} ${styles.tagWait}`}>{copy.stillReading}</span>
                      <p>{copy.seeWhich}</p>
                    </div>
                  </div>
                </div>
                <p className={styles.month}>{dates.month}</p>
                <div className={styles.stats}>
                  {copy.stats.map(([name, value]) => (
                    <div key={name}>
                      <span>{name}</span>
                      <b>{value}</b>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className={styles.device}>
              <span className={`${styles.deviceButton} ${styles.deviceLeft}`} />
              <span className={`${styles.deviceButton} ${styles.deviceRight}`} />
              <div className={styles.lock}>
                <span className={styles.lockIsland} />
                <span className={styles.lockStatus}>
                  <svg width="15" height="11" viewBox="0 0 17 12" aria-hidden="true">
                    <path d="M8.5 2.3c2.4 0 4.6 1 6.2 2.5l1.1-1.2A10.5 10.5 0 0 0 8.5.7 10.5 10.5 0 0 0 1.2 3.6l1.1 1.2A9 9 0 0 1 8.5 2.3Zm0 3.7c1.4 0 2.7.5 3.6 1.4l1.2-1.2a6.8 6.8 0 0 0-9.6 0l1.2 1.2A5 5 0 0 1 8.5 6Zm0 3.6c-.8 0-1.4.3-1.9.8l1.9 1.9 1.9-1.9c-.5-.5-1.1-.8-1.9-.8Z" />
                  </svg>
                  <svg width="22" height="11" viewBox="0 0 27 13" aria-hidden="true">
                    <rect x=".5" y=".5" width="23" height="12" rx="3.5" fill="none" stroke="currentColor" opacity=".5" />
                    <rect x="2" y="2" width="20" height="9" rx="2.2" />
                    <path d="M25 4.5c.8.3 1.4 1.1 1.4 2s-.6 1.7-1.4 2z" opacity=".6" />
                  </svg>
                </span>
                <p className={styles.lockDate}>{dates.long}</p>
                <p className={styles.lockTime}>{copy.lockTime}</p>
                <div className={styles.note}>
                  <span className={styles.noteApp}>
                    <Mark />
                  </span>
                  <span className={styles.noteText}>
                    <span className={styles.noteLine}>
                      <b>{copy.note.app}</b>
                      <time>{copy.note.when}</time>
                    </span>
                    <span>{copy.note.body}</span>
                  </span>
                </div>
                <span className={styles.lockHome} />
              </div>
            </div>

            <div className={styles.flying}>
              <span className={`${styles.tag} ${styles.tagNew}`}>{copy.flying.tag}</span>
              <b>{copy.flying.amount}</b>
              <span>{copy.flying.about}</span>
            </div>

            <div className={`${styles.win} ${styles.inbox}`}>
              <p className={styles.title}>{copy.inbox.title}</p>
              <div className={styles.tabs}>
                <b>{copy.inbox.tabs.all}</b>
                <span>
                  {copy.inbox.tabs.review} <i>4</i>
                </span>
                <span>
                  {copy.inbox.tabs.attention} <i>5</i>
                </span>
              </div>
              <div className={styles.table}>
                {copy.inbox.columns.map((column, index) => (
                  <span key={column} className={`${styles.head} ${index === 3 ? styles.right : ""}`}>
                    {column}
                  </span>
                ))}
                <span className={styles.head} />
                <b className={styles.marked}>{copy.inbox.invoice.name}</b>
                <span className={styles.marked}>{copy.inbox.invoice.channel}</span>
                <span className={styles.marked}>
                  <span className={`${styles.tag} ${INVOICE_TONE[beat.invoice]}`} data-scene-invoice>
                    {copy.inbox.states[beat.invoice]}
                  </span>
                </span>
                <span className={`${styles.marked} ${styles.right}`}>{copy.inbox.invoice.amount}</span>
                <span className={`${styles.marked} ${styles.right}`}>
                  <span className={styles.action}>
                    {beat.invoice === "approved" ? copy.inbox.view : copy.inbox.approve}
                  </span>
                </span>
                {copy.inbox.rows.flatMap((row) => [
                  <span key={`${row.name}-name`}>{row.name}</span>,
                  <span key={`${row.name}-channel`}>{row.channel}</span>,
                  <span key={`${row.name}-tag`}>
                    <span className={`${styles.tag} ${TONE[row.tone]}`}>{row.tag}</span>
                  </span>,
                  <span key={`${row.name}-amount`} className={styles.right}>
                    {row.amount}
                  </span>,
                  <span key={`${row.name}-action`} className={styles.right}>
                    <span className={styles.action}>{row.action}</span>
                  </span>,
                ])}
              </div>
            </div>

            <div className={`${styles.win} ${styles.accountant}`}>
              <div className={styles.accountantBar}>
                <Icon name="users" />
                <span>{copy.accountant.title}</span>
              </div>
              <div className={styles.accountantBody}>
                <p className={styles.accountantHead}>
                  {copy.accountant.client} · {dates.month}
                </p>
                {copy.accountant.checks.map((check, index) => (
                  <p
                    key={check}
                    className={`${styles.check} ${index < beat.checks ? styles.checkOn : ""}`}
                  >
                    <em>✓</em> {check}
                  </p>
                ))}
                <span
                  className={`${styles.export} ${beat.exported ? styles.exportOn : ""}`}
                  data-scene-export
                >
                  {beat.exported ? copy.accountant.exported : copy.accountant.exportLabel}
                </span>
              </div>
            </div>

            <div className={styles.cursor}>
              <svg width="22" height="24" viewBox="0 0 22 24" aria-hidden="true">
                <path
                  d="M2 2 19 12l-7.5 1.8L7.5 21z"
                  fill="#172b26"
                  stroke="#fff"
                  strokeWidth="1.8"
                  strokeLinejoin="round"
                />
              </svg>
              <span>{copy.cursor}</span>
            </div>
          </div>

          <div className={styles.dockBoard}>
            <div className={styles.dock}>
              {dock.map(({ icon, label, stage }) => (
                <a
                  key={label}
                  href="#como"
                  aria-label={label}
                  data-tip={label}
                  className={[
                    styles.dockItem,
                    icon ? "" : styles.dockBrand,
                    icon === "receipt" ? styles.dockSoon : "",
                    stage === beat.dock ? styles.dockOn : "",
                  ].join(" ")}
                >
                  {icon ? <Icon name={icon} /> : <Mark />}
                  {icon ? <i className={styles.dockRun} /> : null}
                </a>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
