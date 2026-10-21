"use client";

import { useEffect, useState } from "react";

/**
 * What this browser can actually do for receipt intake, detected from the
 * platform APIs themselves. Screen width, pointer type and the user agent decide
 * nothing here. Camera access is never requested: device kinds are listed
 * without labels until a permission exists.
 */
export type InputCapabilities = Readonly<{
  /** A camera exists and file inputs support `capture`. */
  cameraCapture: boolean;
  /** Files can be dropped onto the page. */
  dragAndDrop: boolean;
  /** The async clipboard can read an image on request. */
  clipboardRead: boolean;
}>;

const UNKNOWN: InputCapabilities = {
  cameraCapture: false,
  dragAndDrop: false,
  clipboardRead: false,
};

export function useInputCapabilities(): InputCapabilities {
  const [capabilities, setCapabilities] = useState<InputCapabilities>(UNKNOWN);

  useEffect(() => {
    let cancelled = false;
    const probe = document.createElement("div");
    const dragAndDrop = "ondrop" in probe && "ondragover" in probe && typeof DataTransfer !== "undefined";
    const clipboardRead =
      typeof navigator.clipboard?.read === "function" && typeof ClipboardItem !== "undefined";
    const supportsCaptureAttribute = "capture" in document.createElement("input");
    const settle = (hasCamera: boolean) => {
      if (cancelled) return;
      setCapabilities({
        cameraCapture: hasCamera && supportsCaptureAttribute,
        dragAndDrop,
        clipboardRead,
      });
    };
    const devices = navigator.mediaDevices?.enumerateDevices?.();
    if (!devices) {
      settle(false);
    } else {
      devices
        .then((list) => settle(list.some((device) => device.kind === "videoinput")))
        .catch(() => settle(false));
    }
    return () => {
      cancelled = true;
    };
  }, []);

  return capabilities;
}

/** Reads the first receipt-shaped file from the clipboard, if one is there. */
export async function readClipboardFile(acceptedTypes: readonly string[]): Promise<File | null> {
  const items = await navigator.clipboard.read();
  for (const item of items) {
    const type = item.types.find((candidate) => acceptedTypes.includes(candidate));
    if (type) {
      const blob = await item.getType(type);
      const extension = type.split("/")[1] ?? "bin";
      return new File([blob], `pasted-receipt.${extension}`, { type });
    }
  }
  return null;
}
