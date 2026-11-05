# Problem

The Personal hero needs a playful signup celebration while preserving the existing request truth. `SignupState` already owns idle, submitting, success, and error. A successful HTTP response alone is insufficient. Only the existing `response.ok` and `result.status === "registered"` branch can start the flight. The current success branch removes the form, so the CTA position must remain measurable without delaying confirmation.

# Usage (caller's view)

Keep the form and request code in `PersonalEarlyAccess`. A local scene hook receives the existing status and returns anchor refs plus decorative render data.

```tsx
const scene = useSignupScene(state.status);
<section ref={scene.rootRef} className={styles.hero}>
  <div className={styles.capture}>
    <div ref={scene.inputAnchorRef} className={styles.emailShell}>
      <input /* existing input props */ />
      <Pet pose={scene.pose} />
    </div>
    <div ref={scene.ctaAnchorRef} className={styles.ctaSlot}>
      {/* existing form or immediately visible confirmation */}
    </div>
  </div>
  <figure className={styles.preview}>
    <HandPhone screen={welcomeScreen} logoRef={scene.logoAnchorRef} />
  </figure>
  <Celebration flight={scene.flight} onAnimationEnd={scene.finishFlight} />
</section>
```

These components can remain private functions in one scene module. They are not reusable marketing primitives. The input anchor remains present around the success slot, or its final measured point is retained before removal. The CTA anchor is a stable wrapper positioned at the button's old center. Avoid moving that wrapper when confirmation appears. The form can be removed normally once the old center has been stored.

On submission, the pet lifts slightly and smiles. On error, the pet returns to its resting pose and the email remains editable. On confirmed registration, confirmation renders and receives focus immediately while the decorative pet and envelope travel.

# Shape

```ts
type SignupStatus = SignupState["status"];
type Point = Readonly<{ x: number; y: number }>;
type Flight = Readonly<{ from: Point; to: Point; lift: number }> | null;
type PetPose = "rest" | "excited" | "delivered";

type SignupScene = {
  rootRef: RefObject<HTMLElement | null>;
  inputAnchorRef: RefObject<HTMLDivElement | null>;
  ctaAnchorRef: RefObject<HTMLDivElement | null>;
  logoAnchorRef: RefObject<HTMLSpanElement | null>;
  pose: PetPose;
  flight: Flight;
  finishFlight(): void;
};

function useSignupScene(status: SignupStatus): SignupScene;
```

`pose` derives from status and the short cosmetic flight. It is never a second signup state. `Flight` describes geometry, not registration. This is the Model the Domain principle. The small interface hides measurement, pointer throttling, animation cleanup, and motion preferences. Callers retain ownership of semantic content and the true request result. Four DOM anchors are exposed because this scene spans the form and the phone.

Use one hero-relative absolute overlay with `pointer-events: none` and `aria-hidden="true"`. Measure button center and actual logo center through `getBoundingClientRect`, subtract the hero rectangle, and pass coordinates through CSS custom properties. On the pending-to-success transition, use the cached CTA point measured while submitting. Re-measure the target after the success layout commits. This avoids querying a removed button and accommodates the confirmation height changing.

Use nested elements for the flight. The outer wrapper moves linearly from CTA to logo. The inner wrapper runs a vertical hop keyframe with zero displacement at both endpoints. A nested pet/envelope group gives the envelope a slight rotation and delayed follow. End with a small scale bounce at the logo, then remove the overlay through `animationend`. Use one shared duration constant or CSS duration for this animation; do not create a competing timer. The stationary pet is hidden during flight and restored at the logo on completion. It never doubles on screen.

The hand should be an original SVG illustration behind the phone. The welcome screenshot remains an unmodified native asset inside the device. Position a transparent anchor over the real screen logo with percentage coordinates from the supplied image dimensions. Keep the phone upright so target geometry is simple. Do not draw a substitute screen or imply this is a live account.

Eye tracking uses pointermove on the hero for a fine pointer only. Clamp pupil offsets to a few pixels, and write CSS variables on the pet through one requestAnimationFrame. Keep pointer coordinates out of React state. Pointer leave, keyboard focus, coarse pointer, and reduced motion center the pupils. The pet has no tab stop or accessible label.

Mobile retains DOM order of copy, email, and phone. At the current 700px breakpoint, stack them. The overlay still uses hero-local geometry, so the flight moves down to the phone rather than relying on desktop coordinates. If the target is outside the viewport when success occurs, skip travel and show the stationary delivered pose. Never scroll the page for decoration.

A ResizeObserver updates cached anchors while idle/pending. Any resize or scroll during a flight cancels that flight and settles the delivered pose rather than visibly jumping. Disconnect observers, remove listeners, cancel the queued animation frame, and clear the flight on unmount. Honor media-query changes mid-flight. Reduced motion shows success and the delivered pose directly, with no hopping, eye tracking, or bounce.

# Synthesis decision

Candidate A proposes CSS keyframes with measured endpoints. Parent selects the final base. No implementation has been made.

# Tradeoffs accepted

- We accept cancelling the celebration during resize or scroll in exchange for reliable alignment.
- We accept a short linear horizontal path plus a vertical hop in exchange for simple CSS that handles both desktop and mobile.
- We accept one asset-specific percentage logo point in exchange for landing on the actual screenshot logo. Keep this coordinate beside the screenshot metadata so replacement is explicit.
- We accept omitting travel when the phone is offscreen in exchange for immediate, visible confirmation.

# Alternatives considered

A Web Animations API controller could calculate curved keyframes and return only anchor refs. It hides cancellation and timing well but introduces imperative animation instances and sequencing for a small scene. Choose it only if visual review shows the CSS hop cannot achieve the requested movement. CSS is viable because endpoints are measured once and interruption can settle directly.

An SVG scene containing the form, hand, screenshot, and pet would make one coordinate space easy. Its shallow public interface hides too much. It would force the real HTML form into foreignObject or duplicate geometry between HTML and SVG. This complicates responsive layout, accessibility, and input interaction.

# Open questions and risks

Can the sourced native welcome screen provide exact logo bounds and honest localized alt/caption text? Parent owns that asset decision. The present screenshot and payment closeup depict Home and should be replaced for this request.

Can the stable CTA wrapper reserve its original button center without leaving a large blank area after success? Worker should keep the old measured center and allow the success block to size normally if reservation hurts the layout.

# Next implementation step

Implement the Personal-only scene around existing SignupState, then verify pointer, keyboard, error, success, narrow screen, and reduced-motion behavior against the real hero.
