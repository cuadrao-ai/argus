# Personal signup pet design decision

Founder direction, October 9, 2026. Keep copy and email intake left, original hand-held phone right. Use the native welcome screen with the logo and signup button. A square pet follows the cursor, becomes excited on submission, then delivers an envelope to the phone after success.

Grounding: PersonalEarlyAccess owns the email and SignupState union, accepts success only for an OK registered response, focuses confirmation immediately, and preserves the email on errors. The API and storage contract do not change.

The parent read both candidate sketches. A separate cross-judge scored A 23/25 and B 22/25 across success truth, interface size, responsive geometry, accessibility, and visual feasibility. Both preserve the existing signup state. Candidate A is the base because measured endpoints plus CSS animation keep the implementation smaller. Graft B's explicit origin capture immediately before confirmed success and field-to-CTA-to-phone choreography. Keep the public PersonalEarlyAccess(locale) interface unchanged. Asset metadata and the real logo target stay together locally. Reject a new public asset prop, a seven-anchor interface, and separate WAAPI sequences for each movement. No logo redraw or replacement.

Model the Domain keeps registration in the existing SignupState and cosmetic flight geometry in a separate small nullable record. Decorative motion cannot declare success. Confirmation appears immediately and never waits for animation. Fine-pointer eyes move only a few pixels. Offscreen targets receive no long flight. Motion cancels on resize/scroll or reduced-motion changes. Reduced motion shows the same confirmation directly. Keyboard and touch need no cursor interaction.

The asset is an unchanged historical native simulator welcome capture, copied to marketing/public/cuadrao-site/personal-welcome-preview.png. SHA-256 8dc8c6e298742c0bfcec5261a1d4f79d93d4d2733ca46b1a2bc6356b23b22f7c. Provenance is docs/reports/evidence/cuadrao-release-ui/README.md, October 3 design capture. It is not current shipping-app evidence. New hand/pet/envelope graphics are original code-native artwork. No Base assets are extracted.

Implementation and real browser verification remain pending. One worker owns all Marketing writes until handback. The parent owns the preview, tests, final review, commits, and evidence. Comparison 4511 and Consumer/Business code/services remain untouched. No push, publication, real email, hosted writes, or form activation is authorized.
