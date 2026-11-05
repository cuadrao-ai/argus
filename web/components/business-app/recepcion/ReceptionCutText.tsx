"use client";

import { useLayoutEffect, useRef, useState, type HTMLAttributes, type RefObject } from "react";
import { Tooltip } from "@/components/ui/Tooltip";

/** Whether the one-line text in the returned ref is cut off now. A phone card wraps, so there it never is. */
export function useCutOff<T extends HTMLElement>(text: string): [RefObject<T | null>, boolean] {
  const ref = useRef<T>(null);
  const [cut, setCut] = useState(false);
  // `cut` is a dependency because the Tooltip wrapper puts a new node in the ref.
  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return undefined;
    const measure = () => setCut(node.scrollWidth > node.clientWidth);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [text, cut]);
  return [ref, cut];
}

/** One line with an ellipsis. Only when it is cut off does it take keyboard focus and show the full text. */
export default function ReceptionCutText({ text, ...props }: { text: string } & HTMLAttributes<HTMLSpanElement> & { [data: `data-${string}`]: string | boolean | undefined }) {
  const [ref, cut] = useCutOff<HTMLSpanElement>(text);
  const line = <span {...props} ref={ref} tabIndex={cut ? 0 : undefined}>{text}</span>;
  return cut ? <Tooltip content={text} side="top">{line}</Tooltip> : line;
}
