// Test-only settings (NAMING §10), loaded from apps/web/e2e/.env by playwright.config.ts. Errors name the variable,
// never its value.

const SETUP_HINT = "fill apps/web/e2e/.env (template: e2e/.env.example), then run `make seed ARGS=--e2e-staff` once";

export interface StaffLogin {
  email: string;
  password: string;
  totpSecret: string;
}

function readRequired(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`${name} is empty: ${SETUP_HINT}`);
  }
  return value;
}

// The staff user that `make seed ARGS=--e2e-staff` created from the same three values.
export function getStaffLogin(): StaffLogin {
  return {
    email: readRequired("E2E_STAFF_EMAIL"),
    password: readRequired("E2E_STAFF_PASSWORD"),
    totpSecret: readRequired("E2E_STAFF_TOTP_SECRET"),
  };
}

export function getMailpitUrl(): string {
  return (process.env.E2E_MAILPIT_URL?.trim() || "http://localhost:8025").replace(/\/+$/, "");
}
