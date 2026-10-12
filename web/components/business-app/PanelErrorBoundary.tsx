"use client";

import { Component, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { cardClass, secondaryButtonClass } from "./business-ui";

type State = { failed: boolean; attempt: number };

/** A render error in one panel shows a message with a retry inside the workspace; the rest of the page stays. */
export default class PanelErrorBoundary extends Component<{ children: ReactNode; label?: string }, State> {
  state: State = { failed: false, attempt: 0 };

  static getDerivedStateFromError(): Partial<State> {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    if (process.env.NODE_ENV !== "production") console.error("business panel crashed", error);
  }

  render() {
    if (this.state.failed) return <PanelCrashed onRetry={() => this.setState((s) => ({ failed: false, attempt: s.attempt + 1 }))} />;
    return <div key={this.state.attempt}>{this.props.children}</div>;
  }
}

export function PanelCrashed({ onRetry }: { onRetry: () => void }) {
  const { t } = useTranslation();
  return (
    <div role="alert" data-testid="business-panel-crashed" className={`${cardClass} text-[14px] text-black/75 dark:text-white/75`}>
      <p>{t("business.panel.crashed", "This part couldn't be shown. Your receipts are saved.")}</p>
      <button type="button" className={`${secondaryButtonClass} mt-3`} onClick={onRetry}>{t("business.panel.retry", "Try again")}</button>
    </div>
  );
}
