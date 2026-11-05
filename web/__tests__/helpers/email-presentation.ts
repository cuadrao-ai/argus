import { Window } from "happy-dom";

const luminance = (rgb: number[]) => rgb.map(value => value / 255).map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4)
  .reduce((sum, value, index) => sum + value * [.2126, .7152, .0722][index], 0);
const rgb = (value: string) => {
  if (/^#[0-9a-f]{6}$/i.test(value)) return value.slice(1).match(/../g)!.map(channel => parseInt(channel, 16));
  const channels = value.match(/[\d.]+/g)?.map(Number);
  if (!channels || channels.length < 3 || channels[3] === 0) return null;
  return channels.slice(0, 3);
};

export function assertEmailPresentation(html: string, text: string) {
  if (/argus|get-argus|[\w.-]*staging[\w.-]*\.(?:com|ai|test)|onrender\.com/i.test(`${html}\n${text}`)) throw new Error("Legacy branding or staging domain in rendered email");
  for (const mode of ["light", "dark"]) {
    const window = new Window();
    window.document.write(html);
    if (mode === "dark") window.document.documentElement.setAttribute("data-ogsc", "");
    let checked = 0;
    for (const element of window.document.body.querySelectorAll("*")) {
      if (![...element.childNodes].some(node => node.nodeType === 3 && node.textContent?.trim())) continue;
      const style = window.getComputedStyle(element);
      let background: number[] | null = null;
      let foreground = rgb(style.color);
      let hidden = false;
      for (let parent: typeof element | null = element; parent; parent = parent.parentElement) {
        const parentStyle = window.getComputedStyle(parent);
        if (parentStyle.display === "none" || parentStyle.visibility === "hidden" || parentStyle.opacity === "0") hidden = true;
        background ??= rgb(parentStyle.backgroundColor);
        foreground ??= rgb(parentStyle.color);
      }
      if (hidden) continue;
      if (!foreground || !background) throw new Error(`${mode}: missing computed color for ${element.tagName}`);
      const values = [luminance(foreground), luminance(background)].sort((a,b) => b-a);
      const ratio = (values[0] + .05) / (values[1] + .05);
      if (ratio < 4.5) throw new Error(`${mode}: ${element.tagName}.${element.className} contrast ${ratio.toFixed(2)} < 4.5`);
      checked++;
    }
    if (checked === 0) throw new Error(`${mode}: no visible email text checked`);
    void window.happyDOM.abort();
  }
}
