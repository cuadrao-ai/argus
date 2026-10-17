import { readFormsConfig } from "./config";
import type { InquiryDeps } from "./inquiry";
import { WindowLimiter } from "./rate-limit";
import type { SignupDeps } from "./signup";

const TEN_MINUTES = 10 * 60 * 1000;
const HOUR = 60 * 60 * 1000;

// Counters live for the life of the process, so they are built once per module.
const inquiryCounters = {
  perClient: new WindowLimiter(5, TEN_MINUTES),
  perEmail: new WindowLimiter(3, HOUR),
  overall: new WindowLimiter(60, HOUR),
};
const signupCounters = {
  perClient: new WindowLimiter(8, TEN_MINUTES),
  overall: new WindowLimiter(300, HOUR),
};

// Configuration is read per request so a changed environment value is not
// silently ignored by a long-lived module.
export function inquiryDeps(): InquiryDeps {
  return { config: readFormsConfig(process.env), fetch, ...inquiryCounters };
}

export function signupDeps(): SignupDeps {
  return { config: readFormsConfig(process.env), fetch, ...signupCounters };
}
