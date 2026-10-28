/**
 * One fluid canvas for every workspace screen. The parent keeps 1rem phone
 * gutters and 2rem tablet gutters; each screen owns its narrower reading or
 * form column inside this canvas. The top bar uses the same tablet gutter. A screen may bound both on one
 * centered box (body[data-workspace-bounded], globals.css); the canvas and bar carry the data hooks for it.
 */
export const WORKSPACE_CANVAS_CLASS = "w-full";
export const WORKSPACE_BAR_PADDING_CLASS = "tablet:px-8";
