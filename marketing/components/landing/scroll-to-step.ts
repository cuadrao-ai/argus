import { NARROW_WIDTH } from "@/lib/scene-timeline";
import { STEP_JUMPS } from "@/lib/landing-timeline";

export const STEPS_TRACK = "data-steps-track";

export function scrollToStep(step: number): void {
  const track = document.querySelector(`[${STEPS_TRACK}]`);
  if (!track || window.innerWidth <= NARROW_WIDTH) return;
  const box = track.getBoundingClientRect();
  window.scrollTo({ top: window.scrollY + box.top + (box.height - window.innerHeight) * STEP_JUMPS[step] });
}
