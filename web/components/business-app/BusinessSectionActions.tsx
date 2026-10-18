"use client";
import { useBusiness } from "./BusinessWorkspace";
import { secondaryButtonClass } from "./business-ui";

export default function BusinessSectionActions() {
  const { panel, actions } = useBusiness();
  const visible = panel.kind === "inbox" ? actions.create.filter((action) => action.id === "capture_note") : [];
  if (!visible.length) return null;
  return <div className="mb-3 flex flex-wrap justify-end gap-2">{visible.map((action) => <button key={action.id} type="button" className={secondaryButtonClass} onClick={action.run}><action.icon className="h-4 w-4" aria-hidden="true" />{action.label}</button>)}</div>;
}
