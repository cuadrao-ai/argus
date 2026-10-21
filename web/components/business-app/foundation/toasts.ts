"use client";

import { useSyncExternalStore } from "react";

/**
 * Toasts only confirm (Lucas, October 21, 2026). A problem that spans the app
 * docks in ConnectionBanner; a failed piece of work says so inline where the
 * work is, with Reintentar. The type has no error or warning kind, so a
 * caller that wants one does not compile.
 */
export type ToastKind = "info" | "success";
export type ToastAction = { label: string; run: () => void };
export type ToastInput = { kind: ToastKind; text: string; action?: ToastAction };
export type Toast = ToastInput & { id: number };

/** How long each kind stays. */
export const TOAST_MS: Record<ToastKind, number> = { info: 4000, success: 4000 };
/** A toast with an action (Deshacer) stays long enough to reach it. */
export const ACTION_TOAST_MS = 8000;

export function toastDuration(toast: ToastInput): number {
  return toast.action ? ACTION_TOAST_MS : TOAST_MS[toast.kind];
}

/**
 * One presenter shows one toast at a time. The newest replaces the one on
 * screen, Deshacer included, so an old undo never lands after newer work.
 */
let toasts: readonly Toast[] = [];
let nextId = 0;
const listeners = new Set<() => void>();

function publish(next: readonly Toast[]) {
  toasts = next;
  listeners.forEach((listener) => listener());
}

export function showToast(input: ToastInput): number {
  nextId += 1;
  publish([{ ...input, id: nextId }]);
  return nextId;
}

export function dismissToast(id: number) {
  if (toasts.some((toast) => toast.id === id)) publish(toasts.filter((toast) => toast.id !== id));
}

/** For tests and for leaving a Business: nothing from before stays on screen. */
export function clearToasts() {
  if (toasts.length) publish([]);
}

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};
const snapshot = () => toasts;

export function useToasts(): readonly Toast[] {
  return useSyncExternalStore(subscribe, snapshot, snapshot);
}

/**
 * The CSS `linear()` curve of a damped spring released from rest, and how long
 * it takes to settle within 0.1%. Stiffness 180 and damping 20 (mass 1) is the
 * toast stack's spring: a small overshoot, then rest.
 */
export function springEasing(stiffness = 180, damping = 20, mass = 1, samples = 48): { easing: string; durationMs: number } {
  const omega = Math.sqrt(stiffness / mass);
  const zeta = damping / (2 * Math.sqrt(stiffness * mass));
  const decay = zeta * omega;
  const settle = Math.log(1000) / decay;
  const at = (time: number) => {
    if (zeta >= 1) return 1 - Math.exp(-omega * time) * (1 + omega * time);
    const damped = omega * Math.sqrt(1 - zeta * zeta);
    return 1 - Math.exp(-decay * time) * (Math.cos(damped * time) + (decay / damped) * Math.sin(damped * time));
  };
  const points = Array.from({ length: samples + 1 }, (_, index) => at((settle * index) / samples).toFixed(4));
  points[points.length - 1] = "1";
  return { easing: `linear(${points.join(", ")})`, durationMs: Math.round(settle * 1000) };
}
