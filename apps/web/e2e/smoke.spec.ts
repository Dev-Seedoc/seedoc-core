import { randomBytes } from "node:crypto";

import { expect, test } from "@playwright/test";

import { getStaffLogin } from "./support/env.ts";
import { findInvitationPath } from "./support/mailpit.ts";
import { getTotpCode } from "./support/totp.ts";

// M0-B7 smoke test against the local stack: staff creates a tenant → owner accepts the invitation → owner logs in.
// Every run uses a new tenant and owner address, so runs never depend on each other or on older data.

test("staff creates a tenant, the owner accepts the invitation and logs in", async ({ page }) => {
  const runId = Date.now().toString(36);
  const tenant = { name: `E2E Maschinenbau ${runId}`, slug: `e2e-${runId}` };
  const ownerEmail = `owner-${runId}@e2e.example.com`;
  // New for every run and never printed; 24 characters, above the 12-character minimum.
  const ownerPassword = randomBytes(18).toString("base64url");
  const staff = getStaffLogin();

  await test.step("staff logs in with password and TOTP code", async () => {
    await page.goto("/staff");
    await expect(page).toHaveURL(/\/login$/);
    await page.getByLabel("E-Mail-Adresse", { exact: true }).fill(staff.email);
    await page.getByLabel("Passwort", { exact: true }).fill(staff.password);
    await page.getByRole("button", { name: "Anmelden" }).click();

    await expect(page.getByRole("heading", { name: "Bestätigungscode eingeben" })).toBeVisible();
    await page.getByLabel("Bestätigungscode").fill(getTotpCode(staff.totpSecret));
    await page.getByRole("button", { name: "Bestätigen" }).click();
    await expect(page.getByRole("navigation", { name: "Navigation SeeDoc-Team" })).toBeVisible();
  });

  await test.step("staff creates the tenant with its owner", async () => {
    // The header button; an empty list shows a second one in its empty state.
    await page.getByRole("button", { name: "Hersteller anlegen" }).first().click();
    const dialog = page.getByRole("dialog", { name: "Hersteller anlegen" });
    await dialog.getByLabel("Name", { exact: true }).fill(tenant.name);
    await dialog.getByLabel("Kurzname (Slug)").fill(tenant.slug);
    await dialog.getByLabel("E-Mail-Adresse des Inhabers").fill(ownerEmail);
    await dialog.getByRole("button", { name: "Anlegen" }).click();

    await expect(page).toHaveURL(/\/staff\/tenants\/[0-9a-f-]{36}$/);
    await expect(page.getByRole("heading", { name: tenant.name })).toBeVisible();
    const invitation = page.getByRole("row").filter({ hasText: ownerEmail });
    await expect(invitation).toContainText("Inhaber");
  });

  await test.step("owner accepts the invitation from the mail", async () => {
    const invitationPath = await findInvitationPath(ownerEmail);
    // Without the staff session, as if the owner opened the mail on their own computer.
    await page.context().clearCookies();
    await page.goto(invitationPath);

    await expect(page.getByRole("heading", { name: `Einladung zu ${tenant.name}` })).toBeVisible();
    await expect(page.getByText(`Die Einladung gilt für ${ownerEmail}.`)).toBeVisible();
    await page.getByLabel("Name (optional)").fill("E2E Inhaber");
    await page.getByLabel("Neues Passwort").fill(ownerPassword);
    await page.getByLabel("Passwort wiederholen").fill(ownerPassword);
    await page.getByRole("button", { name: "Konto erstellen und beitreten" }).click();

    await expectOwnerApp();
  });

  await test.step("owner logs out and logs in with the new password", async () => {
    await page.getByRole("button", { name: "Benutzermenü" }).click();
    await page.getByRole("menuitem", { name: "Abmelden" }).click();
    await expect(page).toHaveURL(/\/login$/);

    await page.getByLabel("E-Mail-Adresse", { exact: true }).fill(ownerEmail);
    await page.getByLabel("Passwort", { exact: true }).fill(ownerPassword);
    await page.getByRole("button", { name: "Anmelden" }).click();

    await expectOwnerApp();
  });

  // The manufacturer app with the new tenant as its only one (TenantSwitcher shows the name).
  async function expectOwnerApp() {
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("navigation", { name: "Hauptnavigation" })).toBeVisible();
    await expect(page.getByText(tenant.name, { exact: true })).toBeVisible();
  }
});
