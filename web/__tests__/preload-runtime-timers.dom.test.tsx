import { clearTimeout, setTimeout } from "node:timers";
import { expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act, useEffect } from "react";
import { createRoot } from "react-dom/client";

test("the preload lets a render outside act reach its effect", async () => {
  const actEnvironment = Object.getOwnPropertyDescriptor(globalThis, "IS_REACT_ACT_ENVIRONMENT");
  GlobalRegistrator.register({ url: "http://localhost" });
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", {
    configurable: true, writable: true, value: false,
  });
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  let timeout: ReturnType<typeof setTimeout> | undefined;

  try {
    await new Promise<void>((resolve, reject) => {
      timeout = setTimeout(() => reject(new Error("Timed out waiting for an outside-act render's effect")), 1_000);
      function Harness() {
        useEffect(() => { resolve(); }, []);
        return <span>ready</span>;
      }
      root.render(<Harness />);
    });
    expect(container.textContent).toBe("ready");
  } finally {
    clearTimeout(timeout);
    Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", {
      configurable: true, writable: true, value: true,
    });
    await act(async () => root.unmount());
    container.remove();
    await GlobalRegistrator.unregister();
    if (actEnvironment) {
      Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", actEnvironment);
    } else {
      Reflect.deleteProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT");
    }
  }
});
