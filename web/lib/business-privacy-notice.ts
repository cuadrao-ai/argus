import enCatalog from "@/public/locales/en/common.json";
import esCatalog from "@/public/locales/es-419/common.json";

export const MOCK_AUTH_CONSENT_USER_ID = "mock-auth-user";

/**
 * The words that say what a person accepts, in screen order. The one-time
 * line, the privacy link and the failure line explain the screen; they are not
 * what is accepted, so editing them asks no one again.
 */
export const BUSINESS_CONSENT_WORDING_KEYS = [
  "business.consent.title",
  "business.consent.body",
  "business.consent.opt_in",
  "business.consent.continue",
] as const;

type Catalog = Record<string, unknown>;

const CATALOGS: readonly Catalog[] = [esCatalog, enCatalog];

function lookup(catalog: Catalog, key: string): unknown {
  return key.split(".").reduce<unknown>(
    (value, part) => (value && typeof value === "object" ? (value as Catalog)[part] : undefined),
    catalog,
  );
}

const ROUND = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

const rotr = (value: number, bits: number) => (value >>> bits) | (value << (32 - bits));

/**
 * SHA-256 (FIPS 180-4) of the UTF-8 text, as hex. Synchronous on purpose:
 * `crypto.subtle` exists only in secure contexts, and the LAN dev link is not one.
 */
export function sha256Hex(text: string): string {
  const bytes = new TextEncoder().encode(text);
  const padded = new Uint8Array(Math.ceil((bytes.length + 9) / 64) * 64);
  padded.set(bytes);
  padded[bytes.length] = 0x80;
  const view = new DataView(padded.buffer);
  view.setUint32(padded.length - 8, Math.floor(bytes.length / 0x20000000));
  view.setUint32(padded.length - 4, (bytes.length * 8) >>> 0);

  const hash = new Uint32Array([0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]);
  const words = new Uint32Array(64);
  for (let block = 0; block < padded.length; block += 64) {
    for (let i = 0; i < 16; i += 1) words[i] = view.getUint32(block + i * 4);
    for (let i = 16; i < 64; i += 1) {
      const early = words[i - 15];
      const late = words[i - 2];
      words[i] = words[i - 16] + (rotr(early, 7) ^ rotr(early, 18) ^ (early >>> 3)) + words[i - 7] + (rotr(late, 17) ^ rotr(late, 19) ^ (late >>> 10));
    }
    let [a, b, c, d, e, f, g, h] = hash;
    for (let i = 0; i < 64; i += 1) {
      const first = (h + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + ROUND[i] + words[i]) | 0;
      const second = ((rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) | 0;
      h = g;
      g = f;
      f = e;
      e = (d + first) | 0;
      d = c;
      c = b;
      b = a;
      a = (first + second) | 0;
    }
    [a, b, c, d, e, f, g, h].forEach((value, i) => { hash[i] += value; });
  }
  return [...hash].map((value) => value.toString(16).padStart(8, "0")).join("");
}

/**
 * The wording a person accepts, Spanish then English: changing any of it in
 * either language is a new wording, and everyone is asked again.
 */
export function consentCopyVersion(): string {
  const words = CATALOGS.map((catalog) => BUSINESS_CONSENT_WORDING_KEYS.map((key) => lookup(catalog, key)));
  return sha256Hex(JSON.stringify(words)).slice(0, 16);
}

export function canEnterBusiness(accepted: boolean, grantId: string | null): boolean {
  return accepted || grantId === null;
}
