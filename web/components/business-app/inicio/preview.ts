/** The Inicio redesign shows in the local preview only, until Lucas approves it for every build. One owner for that gate. */
export const INICIO_REDESIGN_PREVIEW = process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_MOCK_AUTH === "true";

/**
 * Every Business screen's content and its bar share one box (Inicio's first): fluid up to 80rem, centered beyond it. Two list columns stay
 * scannable at this width (title to action under ~700px); wider, rows stretch without showing more.
 */
export const HOME_CANVAS_MAX = "80rem";
