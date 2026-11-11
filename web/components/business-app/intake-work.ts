/** A queue Agregar sends through. It says whether anything of its own is unsaved, in flight or waiting for a retry. */
export type IntakeQueue = { subscribe: (listener: () => void) => () => void; readonly unfinished: boolean };

/**
 * The one reader of "is anything still being sent" across every intake queue. The leave guard reads this and
 * nothing else, so a queue added here is guarded from its first day.
 */
export function intakeWork(queues: readonly IntakeQueue[]) {
  return {
    subscribe: (listener: () => void) => {
      const stops = queues.map((queue) => queue.subscribe(listener));
      return () => { stops.forEach((stop) => stop()); };
    },
    unfinished: () => queues.some((queue) => queue.unfinished),
  };
}
