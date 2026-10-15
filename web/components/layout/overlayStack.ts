"use client";

import { useEffect, useLayoutEffect, useRef, type RefObject } from "react";
import { focusableWithin, nextFocusIndex } from "./overlayFocus";

/**
 * One registry for every open overlay, and one place that routes input to them.
 *
 * The old shape gave every overlay its own document-level listener and asked it
 * to work out whether it should stay quiet. That is the wrong default: a
 * listener that exists will run, so correctness depended on each surface
 * remembering to check the stack, and every combination we had not thought of
 * was a bug. It produced the same failure five times, in five different
 * surfaces, each fix teaching one more component to stand down.
 *
 * So the layers are the state and the routing is central. A surface says it is
 * open and what it wants to do; it never listens. Escape, Tab containment, and
 * outside-dismiss go to the topmost layer and stop there. A new overlay cannot
 * reintroduce this class of bug by forgetting a guard, because there is no
 * guard for it to forget.
 *
 * This is the shape Radix and Headless UI settled on for the same problem.
 */

export type OverlayLayer = {
  id: string;
  /** The element focus is kept inside, and that outside-dismiss measures against. */
  containerRef: RefObject<HTMLElement | null>;
  /** Whether Tab is contained while this layer is topmost. */
  trapFocus: boolean;
  /** Escape, for the common case. */
  onEscape?: () => void;
  /**
   * Full keydown, for layers that own more than Escape.
   *
   * When present it replaces `onEscape`, and it still only runs while this
   * layer is topmost. Tab containment happens first so a layer cannot
   * accidentally take Tab away from itself.
   */
  onKeyDown?: (event: KeyboardEvent) => void;
  /** A press that landed outside the container, while this layer is topmost. */
  onOutsidePointerDown?: (event: PointerEvent) => void;
};

/** `useLayoutEffect` warns during SSR, where there is nothing to sync anyway. */
const useIsomorphicLayoutEffect =
  typeof window === "undefined" ? useEffect : useLayoutEffect;

let layers: OverlayLayer[] = [];
let listening = false;

function topLayer(): OverlayLayer | null {
  return layers.length > 0 ? layers[layers.length - 1] : null;
}

/**
 * The layer Tab is contained by, which is not always the topmost one.
 *
 * A menu is not modal and opts out of containment, but a menu opened inside a
 * drawer must not let Tab walk out of the drawer: the drawer promised
 * `aria-modal`. So a non-trapping top layer delegates downward to the nearest
 * layer that does trap, rather than turning containment off for the stack.
 */
function trappingLayer(): OverlayLayer | null {
  for (let index = layers.length - 1; index >= 0; index -= 1) {
    if (layers[index].trapFocus) return layers[index];
  }
  return null;
}

function handleKeyDown(event: KeyboardEvent): void {
  const layer = topLayer();
  if (!layer) return;

  if (event.key === "Tab") {
    const trap = trappingLayer();
    if (trap) {
      /*
       * Containment is decided by there being a trap, not by its contents.
       * Guarding on a non-empty list let Tab through whenever a modal
       * momentarily had nothing enabled to hold it, and a busy confirmation is
       * exactly that: both of its buttons are disabled while the request is in
       * flight, so Tab walked out of a surface still claiming `aria-modal` and
       * into the drawer or page underneath.
       */
      event.preventDefault();
      const container = trap.containerRef.current;
      const elements = focusableWithin(container);
      if (elements.length === 0) {
        // Park focus on the panel rather than leaving it on a disabled control
        // or on the body, so the next press has somewhere inside to start from.
        // A panel is a div and cannot take focus without this, and it is set
        // here rather than on every surface so no surface has to remember; the
        // opt-out value keeps it out of the tab order it is standing in for.
        if (container && !container.hasAttribute("tabindex")) {
          container.setAttribute("tabindex", "-1");
        }
        container?.focus();
        return;
      }
      const index = nextFocusIndex({
        count: elements.length,
        currentIndex: elements.indexOf(document.activeElement as HTMLElement),
        direction: event.shiftKey ? "focus-previous" : "focus-next",
      });
      elements[index]?.focus();
      return;
    }
  }

  if (layer.onKeyDown) {
    layer.onKeyDown(event);
    return;
  }

  if (event.key === "Escape" && layer.onEscape) {
    event.preventDefault();
    event.stopPropagation();
    layer.onEscape();
  }
}

function handlePointerDown(event: PointerEvent): void {
  const layer = topLayer();
  if (!layer?.onOutsidePointerDown) return;
  const container = layer.containerRef.current;
  // `contains` rather than an instanceof check, which needs a DOM global to
  // exist and throws where one does not.
  if (container?.contains(event.target as Node)) return;
  layer.onOutsidePointerDown(event);
}

/** Listen only while something is open, so a closed app adds no handlers. */
function syncListeners(): void {
  const shouldListen = layers.length > 0;
  if (shouldListen === listening || typeof document === "undefined") return;
  listening = shouldListen;
  if (shouldListen) {
    document.addEventListener("keydown", handleKeyDown, true);
    document.addEventListener("pointerdown", handlePointerDown, true);
  } else {
    document.removeEventListener("keydown", handleKeyDown, true);
    document.removeEventListener("pointerdown", handlePointerDown, true);
  }
}

export function registerOverlayLayer(layer: OverlayLayer): void {
  layers = [...layers.filter((open) => open.id !== layer.id), layer];
  syncListeners();
}

export function unregisterOverlayLayer(overlayId: string): void {
  layers = layers.filter((open) => open.id !== overlayId);
  syncListeners();
}

/** True when something opened on top of this overlay and should answer first. */
export function hasOverlayAbove(overlayId: string): boolean {
  const index = layers.findIndex((open) => open.id === overlayId);
  return index >= 0 && index < layers.length - 1;
}

export function isTopOverlay(overlayId: string): boolean {
  return topLayer()?.id === overlayId;
}

/**
 * Whether any layer currently owns input.
 *
 * For shortcuts that open a surface. A shortcut that fires while a dialog is up
 * mounts its surface as the new topmost layer, which takes focus and the next
 * keys away from whatever the user is actually looking at, and at a lower
 * z-index it does that invisibly.
 */
export function hasOpenOverlay(): boolean {
  return layers.length > 0;
}

export function overlayStackIds(): readonly string[] {
  return layers.map((open) => open.id);
}

/**
 * Test seam: reset between cases.
 *
 * `listening` is cleared even when there is no `document` to detach from.
 * `syncListeners` returns early in that case, so a file that tore its DOM down
 * with a layer still open left `listening` true, and the next file's stub
 * document never received a listener.
 */
export function resetOverlayStack(): void {
  layers = [];
  syncListeners();
  listening = false;
}

/**
 * Registers a layer for as long as it is open.
 *
 * Callbacks are refreshed in place rather than by re-registering, because
 * re-registering would move the layer to the top of the stack on every render
 * and a parent would start outranking the dialog above it.
 */
export function useOverlayLayer({
  isOpen,
  overlayId,
  containerRef,
  trapFocus = false,
  onEscape,
  onKeyDown,
  onOutsidePointerDown,
}: {
  isOpen: boolean;
  overlayId: string;
  containerRef: RefObject<HTMLElement | null>;
  trapFocus?: boolean;
  onEscape?: () => void;
  onKeyDown?: (event: KeyboardEvent) => void;
  onOutsidePointerDown?: (event: PointerEvent) => void;
}): void {
  const handlers = useRef({ onEscape, onKeyDown, onOutsidePointerDown });
  /*
   * Layout timing, not passive. A passive effect runs after paint, so a key
   * arriving between commit and flush reached the previous render's callback:
   * a second Escape still saw the submenu it had just closed, and an Enter
   * landing just after a confirmation went busy reached the pre-busy handler.
   * Never a dependency of the registration below, which would resubscribe and
   * reorder the stack.
   */
  useIsomorphicLayoutEffect(() => {
    handlers.current = { onEscape, onKeyDown, onOutsidePointerDown };
  });

  /*
   * Layout timing for the same reason, applied to membership rather than to
   * callbacks. A passive effect leaves the registry a commit behind the screen:
   * a dialog that has rendered above the drawer is not the input owner yet, so
   * Escape in that window closes the drawer underneath it, and after the dialog
   * closes its stale entry is still on top, so the next press finds nothing.
   * The visible layer and the layer that owns input have to change together.
   */
  useIsomorphicLayoutEffect(() => {
    if (!isOpen) return;
    const layer: OverlayLayer = {
      id: overlayId,
      containerRef,
      trapFocus,
      onEscape: (...args) => handlers.current.onEscape?.(...args),
      onKeyDown: onKeyDown
        ? (event) => handlers.current.onKeyDown?.(event)
        : undefined,
      onOutsidePointerDown: onOutsidePointerDown
        ? (event) => handlers.current.onOutsidePointerDown?.(event)
        : undefined,
    };
    registerOverlayLayer(layer);
    return () => unregisterOverlayLayer(overlayId);
    // Deliberately not the handlers. They are read above only to decide whether
    // to install a wrapper, their identity lives in the ref, and depending on
    // them would re-register on every render, which moves the layer back to the
    // top of the stack and lets a parent outrank the dialog above it. The deps
    // rule does not inspect this custom hook, so the list is held by hand.
  }, [isOpen, overlayId, containerRef, trapFocus]);
}

/** Back-compat for callers that only need presence in the stack. */
export function useOverlayStackEntry(
  isOpen: boolean,
  overlayId: string,
  containerRef?: RefObject<HTMLElement | null>,
): void {
  const fallbackRef = useRef<HTMLElement | null>(null);
  useOverlayLayer({
    isOpen,
    overlayId,
    containerRef: containerRef ?? fallbackRef,
  });
}
