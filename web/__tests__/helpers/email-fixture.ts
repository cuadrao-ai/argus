import { afterEach, beforeEach } from "bun:test";

export const postalAddress = "Cuadrao LLC, 1209 Mountain Road Pl NE Ste N, Albuquerque NM 87110, EE. UU.";

export function installEmailFixture() {
  let previousAddress: string | undefined;
  beforeEach(() => {
    previousAddress = process.env.MARKETING_POSTAL_ADDRESS;
    process.env.MARKETING_POSTAL_ADDRESS = postalAddress;
  });
  afterEach(() => {
    if (previousAddress === undefined) delete process.env.MARKETING_POSTAL_ADDRESS;
    else process.env.MARKETING_POSTAL_ADDRESS = previousAddress;
  });
}
