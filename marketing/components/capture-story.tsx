"use client";

import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
} from "react";
import { FileText, Check, Search } from "lucide-react";
import type { BusinessLocale } from "./content";
import { touchupCopy } from "./touchup-copy";
import styles from "./touchup.module.css";

type StoryMode =
  | { kind: "manual" }
  | { kind: "scroll"; top: number; height: number; segment: number; before: number; mobile: boolean };

const icons = [FileText, Search, Check];

export function CaptureStory({ locale }: { locale: BusinessLocale }) {
  const c = touchupCopy[locale];
  const [active, setActive] = useState(0);
  const [mode, setMode] = useState<StoryMode>({ kind: "manual" });
  const frame = useRef<HTMLDivElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const intro = useRef<HTMLDivElement>(null);
  const runway = useRef<HTMLDivElement>(null);
  const rail = useRef<HTMLDivElement>(null);
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const count = c.steps.length;

  useEffect(() => {
    const content = frame.current;
    const chapterStage = stage.current;
    const introduction = intro.current;
    const header = document.querySelector("header");
    if (!content || !chapterStage || !introduction || !header) return;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let pending = 0;
    let disposed = false;
    const measure = () => {
      pending = 0;
      const mobile = getComputedStyle(content).display === "contents";
      const bounds = (mobile ? chapterStage : content).getBoundingClientRect();
      const before = mobile
        ? introduction.getBoundingClientRect().height +
          parseFloat(getComputedStyle(introduction).marginBottom)
        : 0;
      const clearance =
        (parseFloat(getComputedStyle(header).top) || 0) +
        header.getBoundingClientRect().height + 16;
      const top = clearance;
      const fits = top + bounds.height <= window.innerHeight - 24;
      const next: StoryMode = reducedMotion.matches || !fits
        ? { kind: "manual" }
        : {
            kind: "scroll",
            top,
            height: bounds.height,
            segment: window.innerHeight * 0.5,
            before,
            mobile,
          };
      setMode(previous => {
        if (previous.kind === "manual" && next.kind === "manual") return previous;
        if (previous.kind === "scroll" && next.kind === "scroll" &&
            previous.top === next.top && previous.height === next.height &&
            previous.segment === next.segment && previous.before === next.before &&
            previous.mobile === next.mobile) return previous;
        return next;
      });
    };
    const schedule = () => {
      if (!disposed && !pending) pending = window.requestAnimationFrame(measure);
    };
    const observer = new ResizeObserver(schedule);
    observer.observe(content);
    observer.observe(chapterStage);
    observer.observe(introduction);
    observer.observe(header);
    window.addEventListener("resize", schedule);
    reducedMotion.addEventListener("change", schedule);
    void document.fonts.ready.then(schedule);
    schedule();
    return () => {
      disposed = true;
      observer.disconnect();
      window.cancelAnimationFrame(pending);
      window.removeEventListener("resize", schedule);
      reducedMotion.removeEventListener("change", schedule);
    };
  }, []);

  useEffect(() => {
    const track = runway.current;
    const progress = rail.current;
    if (mode.kind !== "scroll" || !track || !progress) return;
    let pending = 0;
    const update = () => {
      pending = 0;
      const distance =
        mode.top - track.getBoundingClientRect().top - mode.before;
      const chapter = Math.max(0, Math.min(count, distance / mode.segment));
      setActive(Math.min(count - 1, Math.floor(chapter)));
      progress.style.setProperty("--rail-progress", String(chapter / count));
    };
    const schedule = () => {
      if (!pending) pending = window.requestAnimationFrame(update);
    };
    schedule();
    window.addEventListener("scroll", schedule, { passive: true });
    return () => {
      window.removeEventListener("scroll", schedule);
      window.cancelAnimationFrame(pending);
      progress.style.removeProperty("--rail-progress");
    };
  }, [mode, count]);

  const select = (index: number) => {
    if (mode.kind === "manual") {
      setActive(index);
      return;
    }
    const track = runway.current!;
    window.scrollTo({
      top: track.getBoundingClientRect().top + window.scrollY + mode.before - mode.top +
        mode.segment * (index + 0.5),
      behavior: "instant",
    });
  };
  const onKeyDown = (
    event: KeyboardEvent<HTMLButtonElement>,
    index: number,
  ) => {
    const keys: Record<string, number> = {
      ArrowRight: (index + 1) % count,
      ArrowLeft: (index + count - 1) % count,
      Home: 0,
      End: count - 1,
    };
    if (!(event.key in keys)) return;
    event.preventDefault();
    const next = keys[event.key];
    select(next);
    buttons.current[next]?.focus({ preventScroll: true });
  };
  return (
    <section
      className={`${styles.section} ${styles.story}`}
      id="la-idea"
      aria-labelledby="capture-title"
      data-story-mode={mode.kind}
      style={mode.kind === "scroll" ? {
        "--story-top": `${mode.top}px`,
        "--story-height": `${mode.height}px`,
        "--story-before": `${mode.before}px`,
        "--story-travel": `${mode.segment * count}px`,
      } as CSSProperties : undefined}
    >
      <div ref={runway} className={styles.storyRunway} data-story-runway>
        <div ref={frame} className={styles.storyFrame} data-story-frame
          data-story-pin={mode.kind === "scroll" && !mode.mobile ? "" : undefined}>
          <div ref={intro} className={styles.storyIntro} data-story-intro>
            <p className={styles.eyebrow}>{c.storyLabel}</p>
            <h2 id="capture-title">{c.storyTitle}</h2>
            <p>{c.storyBody}</p>
          </div>
          <div ref={stage} className={styles.storyStage} data-story-stage
            data-story-pin={mode.kind === "scroll" && mode.mobile ? "" : undefined}>
            <div className={styles.storyControls}>
              <div
                ref={rail}
                className={styles.rail}
                role="tablist"
                aria-label={c.storyLabel}
                style={{ "--rail-selected": (active + 1) / count } as CSSProperties}
              >
                {c.steps.map((step, index) => (
                  <button
                    key={step.title}
                    type="button"
                    role="tab"
                    id={`capture-tab-${index}`}
                    aria-selected={active === index}
                    aria-controls={`capture-panel-${index}`}
                    tabIndex={active === index ? 0 : -1}
                    ref={(element) => {
                      buttons.current[index] = element;
                    }}
                    onClick={() => select(index)}
                    onKeyDown={(event) => onKeyDown(event, index)}
                  >
                    {step.title}
                  </button>
                ))}
              </div>
              <p className={styles.caption}>{c.truth}</p>
            </div>
            <div className={styles.recordPanels}>
              {c.steps.map((step, index) => {
                const Icon = icons[index];
                return (
                  <div
                    key={step.title}
                    className={styles.recordCard}
                    role="tabpanel"
                    id={`capture-panel-${index}`}
                    aria-labelledby={`capture-tab-${index}`}
                    aria-hidden={active !== index}
                    tabIndex={active === index ? 0 : -1}
                    style={{ visibility: active === index ? "visible" : "hidden" }}
                  >
                    <Icon size={26} strokeWidth={1.4} aria-hidden="true" />
                    <h3>{step.label}</h3>
                    <p>{step.body}</p>
                    <div className={styles.recordDetail}>
                      <span>{step.detail}</span>
                      <strong>{step.amount}</strong>
                      <small>{step.status}</small>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
