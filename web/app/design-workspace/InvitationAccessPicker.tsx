"use client";

import { useMemo, useState } from "react";
import AccessRolePicker from "./AccessRolePicker";

/** Connect the shared picker to the invitation form inside its preview frame. */
export default function InvitationAccessPicker({ slot }: { slot: HTMLElement }) {
  const select = slot.parentElement?.querySelector<HTMLSelectElement>("select");
  const options = useMemo(() => Array.from(select?.options ?? []).map(option => ({value:option.value,label:option.textContent ?? "",description:option.dataset.description ?? ""})), [select]);
  const [value, setValue] = useState(select?.value ?? "editor");
  return <AccessRolePicker options={options} value={value} label={slot.dataset.label ?? ""} compact={slot.dataset.compact === "true"} disabled={select?.disabled} ownerDocument={slot.ownerDocument} portalRoot={document.querySelector("[data-invitation-modal]")} onChange={next => {
    setValue(next);
    const nativeSelect = slot.parentElement?.querySelector<HTMLSelectElement>("select");
    if (nativeSelect) {
      nativeSelect.value = next;
      const ChangeEvent = slot.ownerDocument.defaultView?.Event ?? Event;
      nativeSelect.dispatchEvent(new ChangeEvent("change", {bubbles:true}));
    }
  }} />;
}
