/**
 * The one hard password rule is the auth server's: `minimum_password_length` in
 * supabase/config.toml, with `password_requirements` empty. No composition rule
 * is added here. Everything else is coaching: a local entropy estimate where
 * length counts most and common words, sequences and repeats count little.
 */
export const PASSWORD_MIN_LENGTH = 8;

/** What password managers read to generate one that the server accepts. */
export const PASSWORD_RULES = `minlength: ${PASSWORD_MIN_LENGTH};`;

export type PasswordStrength = "empty" | "weak" | "almost" | "strong";

export type PasswordReading = {
  strength: PasswordStrength;
  bits: number;
  longEnough: boolean;
  /** A common word, a run like abc or 123, or one character repeated. */
  predictable: boolean;
};

const ALMOST_BITS = 40;
const STRONG_BITS = 60;
/** What a guesser pays for a word from a short list of favourites. */
const COMMON_WORD_BITS = 10;

const COMMON_WORDS = [
  "password", "contrasena", "clave", "secreto", "qwerty", "asdf", "zxcv", "admin", "welcome", "bienvenido",
  "iloveyou", "teamo", "letmein", "monkey", "dragon", "football", "baseball", "beisbol", "pelota", "cuadrao",
  "dominicana", "santodomingo", "santiago", "quisqueya", "republica", "aguila", "licey", "escogido", "dios",
  "amor", "mama", "papa", "familia", "hola", "princesa", "superman", "batman", "pokemon", "abc",
] as const;

const LEET: Record<string, string> = { "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i" };

function poolSize(password: string): number {
  let pool = 0;
  if (/[a-z]/.test(password)) pool += 26;
  if (/[A-Z]/.test(password)) pool += 26;
  if (/\d/.test(password)) pool += 10;
  if (/[^\p{L}\d]/u.test(password)) pool += 33;
  if (/[^\x00-\x7F]/.test(password) && /\p{L}/u.test(password)) pool += 20;
  return Math.max(pool, 1);
}

/** Each character counts once, except the ones a guesser gets for free. */
function freeCharacters(password: string): { free: number; words: number; predictable: boolean } {
  const bare = password.normalize("NFD").replace(/\p{M}/gu, "");
  const plain = [...bare.toLowerCase()].map((char) => LEET[char] ?? char).join("");
  const taken = new Array<boolean>(plain.length).fill(false);
  let words = 0;
  for (const word of COMMON_WORDS) {
    for (let at = plain.indexOf(word); at !== -1; at = plain.indexOf(word, at + word.length)) {
      if (taken.slice(at, at + word.length).some(Boolean)) continue;
      taken.fill(true, at, at + word.length);
      words += 1;
    }
  }
  let free = taken.filter(Boolean).length;
  let patterned = false;
  for (let index = 2; index < plain.length; index += 1) {
    if (taken[index]) continue;
    const step = bare.charCodeAt(index) - bare.charCodeAt(index - 1);
    const before = bare.charCodeAt(index - 1) - bare.charCodeAt(index - 2);
    // The third character of "aaa", "abc" or "321" is free, and so is every one after it.
    if (step === before && Math.abs(step) <= 1) {
      free += 1;
      patterned = true;
    }
  }
  const predictable = words > 0 || patterned;
  return { free, words, predictable };
}

export function readPassword(password: string): PasswordReading {
  if (!password) return { strength: "empty", bits: 0, longEnough: false, predictable: false };
  const { free, words, predictable } = freeCharacters(password);
  const counted = Math.max(password.length - free, 0);
  const bits = Math.round(counted * Math.log2(poolSize(password)) + words * COMMON_WORD_BITS + free);
  const longEnough = password.length >= PASSWORD_MIN_LENGTH;
  const strength = !longEnough || bits < ALMOST_BITS ? "weak" : bits < STRONG_BITS ? "almost" : "strong";
  return { strength, bits, longEnough, predictable };
}
