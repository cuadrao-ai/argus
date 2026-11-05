let recoveryEmail = "";

export function rememberRecoveryEmail(email: string) { recoveryEmail = email; }
export function takeRecoveryEmail() {
  const email = recoveryEmail;
  recoveryEmail = "";
  return email;
}
