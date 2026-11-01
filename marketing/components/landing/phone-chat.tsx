import type { ChatState } from "@/lib/landing-timeline";
import type { DemoDates } from "@/lib/demo-date";
import { landingCopy } from "./landing-copy";
import styles from "./phone-chat.module.css";

const MARK = "/cuadrao-site/cuadrao-mark-light.svg";

type Props = {
  chat: ChatState;
  copy: (typeof landingCopy)["es"]["how"]["chat"];
  dates: DemoDates;
};

function shown(visible: boolean): string {
  return visible ? styles.shown : "";
}

export function PhoneChat({ chat, copy, dates }: Props) {
  const reply = copy.reply;
  return (
    <div className={styles.iphone} data-phone>
      <span className={`${styles.side} ${styles.sideOne}`} />
      <span className={`${styles.side} ${styles.sideTwo}`} />
      <span className={`${styles.side} ${styles.sideThree}`} />
      <span className={styles.power} />
      <div className={styles.screen}>
        <div className={styles.island} />
        <div className={styles.status}>
          <b>{copy.time}</b>
          <span className={styles.statusIcons}>
            <svg width="18" height="12" viewBox="0 0 18 12" aria-hidden="true">
              <rect x="0" y="8" width="3" height="4" rx="1" />
              <rect x="5" y="5.5" width="3" height="6.5" rx="1" />
              <rect x="10" y="3" width="3" height="9" rx="1" />
              <rect x="15" y="0" width="3" height="12" rx="1" />
            </svg>
            <svg width="17" height="12" viewBox="0 0 17 12" aria-hidden="true">
              <path d="M8.5 2.3c2.4 0 4.6 1 6.2 2.5l1.1-1.2A10.5 10.5 0 0 0 8.5.7 10.5 10.5 0 0 0 1.2 3.6l1.1 1.2A9 9 0 0 1 8.5 2.3Zm0 3.7c1.4 0 2.7.5 3.6 1.4l1.2-1.2a6.8 6.8 0 0 0-9.6 0l1.2 1.2A5 5 0 0 1 8.5 6Zm0 3.6c-.8 0-1.4.3-1.9.8l1.9 1.9 1.9-1.9c-.5-.5-1.1-.8-1.9-.8Z" />
            </svg>
            <svg width="27" height="13" viewBox="0 0 27 13" aria-hidden="true">
              <rect x=".5" y=".5" width="23" height="12" rx="3.5" fill="none" stroke="currentColor" opacity=".4" />
              <rect x="2" y="2" width="20" height="9" rx="2.2" />
              <path d="M25 4.5c.8.3 1.4 1.1 1.4 2s-.6 1.7-1.4 2z" opacity=".5" />
            </svg>
          </span>
        </div>
        <div className={styles.head}>
          <svg width="12" height="21" viewBox="0 0 12 21" fill="none" stroke="#1c1c1e" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M10.5 1.5 2 10.5l8.5 9" />
          </svg>
          <span className={styles.avatar}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={MARK} alt="" />
          </span>
          <div className={styles.who}>
            <b>{copy.contact}</b>
            <span data-chat-status>{chat.typing ? copy.typing : copy.online}</span>
          </div>
          <svg width="28" height="21" viewBox="0 0 28 21" fill="none" stroke="#1c1c1e" strokeWidth="1.8" strokeLinejoin="round" aria-hidden="true">
            <rect x="1" y="3" width="18" height="15" rx="4" />
            <path d="m19 9 8-4.5v12L19 12z" />
          </svg>
          <svg width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="#1c1c1e" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M21 16.5v3a2 2 0 0 1-2.2 2A18 18 0 0 1 2.5 5.2 2 2 0 0 1 4.5 3h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8.5 11a15 15 0 0 0 4.5 4.5l1.4-1.2a2 2 0 0 1 2.1-.5c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2Z" />
          </svg>
        </div>
        <div className={styles.body}>
          <div className={styles.day}>{copy.today}</div>
          <div className={`${styles.message} ${styles.mine} ${shown(chat.photo)}`} data-chat-photo>
            <div className={styles.shot}>
              <div className={styles.paper}>
                <b>{copy.paper.store}</b>
                <span>{copy.paper.rnc}</span>
                {copy.paper.lines.map(([name, value]) => (
                  <span key={name} className={styles.line}>
                    <i>{name}</i>
                    <i>{value}</i>
                  </span>
                ))}
                <span className={`${styles.line} ${styles.total}`}>
                  <i>{copy.paper.total[0]}</i>
                  <i>{copy.paper.total[1]}</i>
                </span>
                <span>{copy.paper.ncf}</span>
              </div>
              <span className={styles.stamp}>
                {copy.sent} <em className={chat.read ? styles.read : ""}>{chat.delivered ? "✓✓" : "✓"}</em>
              </span>
            </div>
          </div>
          {chat.typing && (
            <div className={`${styles.message} ${styles.theirs} ${styles.typing} ${styles.shown}`}>
              <i />
              <i />
              <i />
            </div>
          )}
          {chat.reply && (
            <div className={`${styles.message} ${styles.theirs} ${styles.card} ${styles.shown}`} data-chat-reply>
              <p className={styles.cardTitle}>
                <b>{reply.title}</b>
              </p>
              <p>
                <b>{reply.fields[0][0]}:</b> {reply.fields[0][1]}
              </p>
              <p>
                <b>{reply.dateLabel}:</b> <span data-chat-date>{dates.short}</span>
              </p>
              {reply.fields.slice(1).map(([name, value]) => (
                <p key={name}>
                  <b>{name}:</b> {value}
                </p>
              ))}
              <span className={styles.cardTime}>{reply.time}</span>
              <div className={styles.quick}>
                <svg width="17" height="14" viewBox="0 0 17 14" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M6 1 1 5.5 6 10" />
                  <path d="M1 5.5h9a6 6 0 0 1 6 6V13" />
                </svg>
                {reply.open}
              </div>
            </div>
          )}
        </div>
        <div className={styles.input}>
          <svg width="22" height="22" viewBox="0 0 22 22" fill="none" stroke="#1c1c1e" strokeWidth="1.9" strokeLinecap="round" aria-hidden="true">
            <path d="M11 2v18M2 11h18" />
          </svg>
          <span className={styles.field} />
          <svg width="25" height="21" viewBox="0 0 25 21" fill="none" stroke="#1c1c1e" strokeWidth="1.7" strokeLinejoin="round" aria-hidden="true">
            <path d="M2 6.5A2.5 2.5 0 0 1 4.5 4H8l2-3h5l2 3h3.5A2.5 2.5 0 0 1 23 6.5v10a2.5 2.5 0 0 1-2.5 2.5h-16A2.5 2.5 0 0 1 2 16.5z" />
            <circle cx="12.5" cy="11" r="4.2" />
          </svg>
          <svg width="17" height="24" viewBox="0 0 17 24" fill="none" stroke="#1c1c1e" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
            <rect x="5" y="1.5" width="7" height="13" rx="3.5" />
            <path d="M1.5 11.5a7 7 0 0 0 14 0M8.5 18.5v4" />
          </svg>
        </div>
        <div className={styles.home} />
      </div>
    </div>
  );
}
