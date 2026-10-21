# Original Cuadrao website reference

The original Marketing layout is preserved for inspiration. This archive is historical design material, not a release candidate.

- [Download the complete Marketing source](cuadrao-original-171779c97.tar.gz).
- Source commit: `171779c97c0b895ab437debe7750c30db04b8ecc`.
- Marketing tree: `8edd34949e03fd70a1acdf703c14cb7e9febb94b`.
- All 109 tracked Marketing files in the preserved comparison directory match that commit byte-for-byte. The archive is generated with `git archive`, so it excludes credentials, dependencies and build caches.
- Original comparison files remain at `/Users/garces/.codex/visualizations/2026/09/26/01a0de75-29ee-71f0-8f58-0d2bb3934a33/cuadrao-marketing-touchup/canonical/marketing`.
- Port4511 was no longer listening on this pass. It was restored from a separate extraction at `/private/tmp/cuadrao-layout-reference-20261009/cuadrao-original/marketing`, with its own dependencies and a fresh build. Real provider credentials remain unset. The old source directory is unchanged.

## Visual references

These existing screenshots record the original layout's earlier verified source `eb7c6f59b`; they are historical captures, not new exact-head evidence for the archive commit. [Original evidence and provenance](../../cuadrao-marketing-launch/README.md).

| Page | Desktop | Mobile |
| --- | --- | --- |
| Business ES | [View](../../cuadrao-marketing-launch/screens/es-home-1440.jpg) | [View](../../cuadrao-marketing-launch/screens/es-home-390.jpg) |
| Personal ES | [View](../../cuadrao-marketing-launch/screens/es-personal-1440.jpg) | [View](../../cuadrao-marketing-launch/screens/es-personal-390.jpg) |
| Business EN | [View](../../cuadrao-marketing-launch/screens/en-home-1440.jpg) | [View](../../cuadrao-marketing-launch/screens/en-home-390.jpg) |
| Personal EN | [View](../../cuadrao-marketing-launch/screens/en-personal-1440.jpg) | [View](../../cuadrao-marketing-launch/screens/en-personal-390.jpg) |

## Replay later

Extract the archive into a new directory. From its `cuadrao-original/marketing` directory, run `bun install --frozen-lockfile` and `NEXT_TELEMETRY_DISABLED=1 bun run build`. Start it on a free loopback port with provider values unset:

```sh
env -u RESEND_API_KEY -u SUPABASE_SERVICE_ROLE_KEY -u SUPABASE_URL -u RESEND_API_URL -u CUADRAO_INQUIRY_FROM -u CUADRAO_INQUIRY_TO CUADRAO_SITE_INDEXING=private NEXT_TELEMETRY_DISABLED=1 bun run start --hostname 127.0.0.1 -p 4511
```

Do not connect historical forms to real providers. Dependencies and local build output are deliberately excluded from the archive.

Archive SHA-256: `6aa3b6d38c9774ac39ac36c3cb0ee5046266f13b9c53475e3e511090197f48aa`.
