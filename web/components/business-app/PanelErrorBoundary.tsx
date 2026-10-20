"use client";

import { Component, type ReactNode } from "react";

import { ServerErrorScreen } from "@/components/status/ServerErrorScreen";
import { referenceCode } from "@/lib/failure-screen";

type State = { failed: boolean; attempt: number; reference: string };

export default class PanelErrorBoundary extends Component<{ children: ReactNode; label?: string }, State> {
  state: State = { failed: false, attempt: 0, reference: "" };

  static getDerivedStateFromError(error: unknown): Partial<State> {
    return { failed: true, reference: referenceCode(error) };
  }

  render() {
    if (this.state.failed) {
      return (
        <PanelCrashed
          reference={this.state.reference}
          onRetry={() => this.setState((current) => ({ failed: false, attempt: current.attempt + 1, reference: "" }))}
        />
      );
    }
    return <div key={this.state.attempt}>{this.props.children}</div>;
  }
}

export function PanelCrashed({ onRetry, reference }: { onRetry: () => void; reference: string }) {
  return <ServerErrorScreen onRetry={onRetry} reference={reference} />;
}
