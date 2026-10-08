import { describe, expect, it } from "vitest";

import { ApiError } from "./errors";
import { createQueryClient } from "./queryClient";
import { queryKeys } from "./queryKeys";

describe("createQueryClient", () => {
  it("reloads get_me instead of showing an error when the staff session needs TOTP again", async () => {
    const queryClient = createQueryClient();
    queryClient.setQueryData(queryKeys.auth.me(), { mfa_verified: true });

    await queryClient
      .query({
        queryKey: ["staff", "tenants"],
        queryFn: () => Promise.reject(new ApiError(401, "mfa_required")),
      })
      .catch(() => undefined);

    expect(queryClient.getQueryState(queryKeys.auth.me())?.isInvalidated).toBe(true);
  });
});
