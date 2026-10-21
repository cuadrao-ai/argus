# Personal hero candidate B

## Problem

The Personal hero needs warmth without weakening signup truth. The left side keeps the current copy and email flow. The right side shows the parent-provided native welcome screen inside an original hand-held phone composition. A square pet peeks from the email field, watches the pointer, and becomes excited while the request is pending. Only a successful `/api/signups` response with `status: "registered"` starts the pet and envelope flight into the phone logo. The existing `SignupState` remains the single owner of idle, pending, success, and error truth. An error keeps the typed email and never starts a flight.

## Usage

The parent imports the real native screen asset and passes it into the Personal hero. Consumer and Business routes do not change.

```tsx
import personalWelcome from "@/public/cuadrao-site/personal-welcome-preview.png";

<PersonalEarlyAccess
  locale={locale}
  welcomeScreen={{ src: personalWelcome, alt: copy.personalWelcomeAlt }}
/>
```

The component continues to submit the same payload and accepts success only at the existing boundary.

```ts
if (isRegisteredSignupResponse(response, result)) {
  flightOrigin.current = measureFlightOrigin();
  setState({ status: "success" });
}
```

The visible success copy renders as soon as `SignupState` becomes `success`. Motion starts afterward and cannot delay or replace the confirmation.

## Shape

```ts
import type { StaticImageData } from "next/image";

type SignupState =
  | { status: "idle" }
  | { status: "submitting" }
  | { status: "success" }
  | { status: "error"; message: string; rejected: boolean };

type WelcomeScreenAsset = Readonly<{
  src: StaticImageData;
  alt: string;
}>;

type PersonalEarlyAccessProps = Readonly<{
  locale: BusinessLocale;
  welcomeScreen: WelcomeScreenAsset;
}>;

type SceneAnchors = Readonly<{
  hero: React.RefObject<HTMLElement | null>;
  emailField: React.RefObject<HTMLDivElement | null>;
  cta: React.RefObject<HTMLButtonElement | null>;
  phoneLogo: React.RefObject<HTMLDivElement | null>;
  pet: React.RefObject<HTMLDivElement | null>;
  petEyes: React.RefObject<HTMLDivElement | null>;
  flightLayer: React.RefObject<HTMLDivElement | null>;
}>;

type FlightOrigin = Readonly<{
  pet: DOMRectReadOnly;
  cta: DOMRectReadOnly;
}>;

function usePersonalHeroMotion(input: Readonly<{
  status: SignupState["status"];
  anchors: SceneAnchors;
  flightOrigin: React.RefObject<FlightOrigin | null>;
}>): void;
```

`WelcomeScreenAsset` makes the parent own the real native screen source. The hero owns only its presentation. This keeps the public interface small and prevents the scene from choosing a substitute screenshot.

The JSX has three layers.

1. `heroCopy` contains the existing copy, email value, errors, privacy text, and immediate success confirmation.
2. `heroScene` contains a decorative SVG or CSS hand, the phone shell, the real welcome image, and a stable `phoneLogo` target. The image keeps useful alt text. The hand, pet, and envelope are `aria-hidden`.
3. `flightLayer` is a non-interactive overlay. It is empty except during a confirmed success flight.

The email control sits in an `emailField` wrapper. The input gets enough right padding for the pet. The square pet peeks over the wrapper's right edge, so it does not cover the email text or change the input hit area. Its two pupils use `transform: translate(...)` and move at most 3 pixels toward the pointer.

`usePersonalHeroMotion` owns temporary browser animation objects, not product state. It holds active `Animation` instances and one `requestAnimationFrame` id in refs. It uses `Element.animate()` for the pending bounce, flight, landing pulse, and eye movement. CSS owns static layout, colors, and the reduced-motion fallback. This is structurally different from a CSS keyframe scene because every moving endpoint comes from measured live anchors.

For pointer tracking, a `pointermove` listener records the latest client coordinates. One animation frame computes the vector from the pet eye center, normalizes it, and clamps each pupil to 3 pixels. Pointer tracking runs only for `pointerType` values with hover support. Touch, keyboard, and devices matching `(hover: none)` keep the pupils centered. The pet remains charming but still.

When status becomes `submitting`, the pet runs a small repeating WAAPI sequence. It rises 3 pixels, squashes slightly, and settles over 460 milliseconds. The button text and `aria-busy` remain the real pending signal. Excitement is decorative.

When the parsed response is exactly `registered`, the submit handler measures the pet and CTA before replacing the form with confirmation. After React commits the success text, a layout effect measures the stable phone logo. The overlay creates visual clones of the pet and a small envelope at the saved origin. WAAPI moves them through measured viewport points.

```text
pet center -> CTA center -> phone logo center
envelope center -> phone logo center
```

The pet uses a short hop into the CTA, then follows a curved offset path toward the logo. The envelope starts at the CTA. Both finish in about 720 milliseconds. The logo then scales to 1.06 and returns with a soft 220 millisecond bounce. The overlay uses `position: fixed`, so form-to-confirmation reflow does not move the captured origin. On completion or cancellation, it removes the clones and clears every `Animation` reference.

The transition is one way. `idle` and `error` never enter the flight branch. An error preserves `email`, restores the calm pet, and keeps focus behavior unchanged. Repeated submissions remain blocked by the existing `pending` ref. The motion hook does not inspect response data and cannot declare success.

At 701 pixels and above, the hero uses two columns. Copy and form sit left. The hand-held phone scene sits right. At 700 pixels and below, it stacks as copy, form, then scene. The phone remains fully visible and the hand can crop decoratively inside its own overflow boundary. Measured anchors make the success path work in either geometry.

The hook installs one `ResizeObserver` on the email wrapper and logo. It refreshes eye centers while idle. A resize during a flight cancels and clears the overlay rather than guessing a new path. `resize`, `scroll`, media-query, pointer, observer, animation, and frame resources are removed in effect cleanup. A route change cannot leave clones behind.

With `prefers-reduced-motion: reduce`, the hook skips all WAAPI motion and pointer following. The success confirmation still appears immediately. The pet and envelope do not fly. The logo does not bounce. This preserves the same truthful state change without motion.

Keyboard use has no motion dependency. Tab order remains email, CTA, privacy links. The pet is decorative and unfocusable. Focus moves to the current success heading exactly as it does now. A user who submits with Enter receives the same success or error result.

The interface hides geometry measurement, animation cancellation, and overlay cleanup from the parent. It exposes only locale and the required native screen asset. That is enough depth for this component and no more.

## Synthesis decision

This candidate proposes the WAAPI measured-anchor architecture for synthesis. It should be compared with the parent's CSS-driven scene on layout stability, cleanup cost, reduced-motion behavior, and whether live anchor measurement earns its extra code. No base candidate is selected in this document.

## Tradeoffs accepted

- We accept a small imperative motion hook in exchange for flights that land on the real CTA and phone logo at desktop and mobile sizes.
- We accept cancelling an in-progress flight on resize in exchange for never showing a visibly wrong destination.
- We accept a temporary fixed overlay in exchange for immediate success rendering without preserving the old form in the accessibility tree.
- We accept centered eyes on touch and keyboard input in exchange for predictable behavior without synthetic pointer assumptions.

## Alternatives considered

- A CSS-only scene with keyframes and percentage endpoints has less JavaScript, but it exposes breakpoint-specific path tuning to the stylesheet. It cannot reliably connect the live field, CTA, and phone logo after reflow. This is the parent's comparison candidate.
- Keeping the form mounted invisibly until the flight ends makes origin geometry easy, but it delays or complicates the success surface and risks hidden interactive content. The measured overlay gives the caller immediate truthful confirmation.
- Canvas or SVG path animation can make a more elaborate curve, but it adds a drawing coordinate system and resize logic to a small interaction. DOM clones and WAAPI hide less and remain easier to inspect.

## Open questions and risks

- Does `personal-welcome-preview.png` contain a Cuadrao logo at a stable location, or should the phone shell provide a separate visible logo target over the image?
- Should the pet use an existing brand illustration asset, or may this component define the square pet with simple DOM shapes?
- Is the hand expected to match an existing Cuadrao illustration style, or is an original flat silhouette acceptable?
- Does the real welcome image already include device chrome? If it does, should the hero omit its own phone shell to avoid a phone inside a phone?

## Next implementation step

Build the static two-column and stacked scene with the parent-provided welcome asset and stable refs, then add the measured motion hook without changing signup submission behavior.
