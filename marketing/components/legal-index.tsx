"use client";

import { useEffect, useState, type ChangeEvent } from "react";
import type { LegalSection } from "@/lib/legal-sections";
import legal from "./legal.module.css";

export function LegalIndex({ label, sections }: { label: string; sections: LegalSection[] }) {
  const [current, setCurrent] = useState<string>();

  useEffect(() => {
    const headings = sections.flatMap(({ id }) => document.getElementById(id) ?? []);
    if (!headings.length) return;
    // A heading is current once it reaches the spot an anchor jump scrolls it to.
    const line = () => parseFloat(getComputedStyle(headings[0]).scrollMarginTop) + 1;
    const update = () => {
      const passed = headings.filter((heading) => heading.getBoundingClientRect().top <= line());
      setCurrent((passed.at(-1) ?? headings[0]).id);
    };
    let observer: IntersectionObserver | undefined;
    const observe = () => {
      observer?.disconnect();
      observer = new IntersectionObserver(update, { rootMargin: `-${line()}px 0px 0px 0px` });
      headings.forEach((heading) => observer!.observe(heading));
    };
    observe();
    window.addEventListener("resize", observe);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", observe);
    };
  }, [sections]);

  const jump = (event: ChangeEvent<HTMLSelectElement>) => {
    const id = event.target.value;
    setCurrent(id);
    if (window.location.hash === `#${id}`) document.getElementById(id)?.scrollIntoView();
    else window.location.hash = id;
  };

  return (
    <aside className={legal.index}>
      <div className={legal.jump}>
        <label htmlFor="legal-index-jump">{label}</label>
        <select id="legal-index-jump" value={current ?? sections[0]?.id} onChange={jump}>
          {sections.map(({ id, title }) => <option key={id} value={id}>{title}</option>)}
        </select>
      </div>
      <nav className={legal.card} aria-labelledby="legal-index-title">
        <p id="legal-index-title" className={legal.cardTitle}>{label}</p>
        <ol>
          {sections.map(({ id, title }) => (
            <li key={id}>
              <a href={`#${id}`} aria-current={id === current ? "location" : undefined}>
                <span className={legal.dot} aria-hidden="true" />
                {title}
              </a>
            </li>
          ))}
        </ol>
      </nav>
    </aside>
  );
}
