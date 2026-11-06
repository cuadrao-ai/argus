export const EMAIL_OTP_LENGTH = 8;
export const EMAIL_OTP_PATTERN = new RegExp(`^[0-9]{${EMAIL_OTP_LENGTH}}$`);

export function isEmailOtp(value: string): boolean {
  return value.length === EMAIL_OTP_LENGTH && EMAIL_OTP_PATTERN.test(value);
}
