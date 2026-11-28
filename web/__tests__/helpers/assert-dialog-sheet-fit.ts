import assert from "node:assert/strict";
import { SHEET_SNAP_SHARE } from "@/components/ui/BottomSheet";

export function assertDialogSheetFit() {
  const sheet = document.querySelector<HTMLElement>('[role="dialog"]');
  assert.ok(sheet);
  assert.equal(sheet.dataset.snap, "fit");
  assert.equal(sheet.style.height, "");
  assert.equal(sheet.style.maxHeight, `${Math.round(window.innerHeight * SHEET_SNAP_SHARE.full)}px`);
}
