// TanStack Query hooks for /auth. Names from the "Frontend fn / hook" column of docs/API.md §2.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  acceptInvitation,
  confirmPasswordReset,
  getInvitation,
  getMe,
  login,
  logout,
  reauthenticate,
  requestPasswordReset,
  setupTotp,
  verifyTotp,
} from "../endpoints";
import { queryKeys } from "../queryKeys";
import type { AcceptInvitationRequest, MeRead } from "../types";

// No toast: `unauthenticated` is the normal answer when nobody is logged in; the shell redirects to /login.
// No retryOnMount: a component mounting later must not re-ask (and briefly reset to "pending") after a definite
// "not logged in" — login, logout and accept_invitation update this cache directly.
export function useMe() {
  return useQuery({
    queryKey: queryKeys.auth.me(),
    queryFn: getMe,
    retryOnMount: false,
    meta: { errorToast: false },
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: login,
    // LoginPage shows wrong-password and rate-limit errors next to the form.
    meta: { errorToast: false },
    onSuccess: (me: MeRead) => {
      queryClient.setQueryData(queryKeys.auth.me(), me);
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: logout,
    onSettled: () => {
      // Drop every tenant's data so the next user never sees the previous user's data.
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== queryKeys.auth.all()[0] });
      // Reset (not remove) auth queries: screens still showing them ask again and learn "not logged in".
      void queryClient.resetQueries({ queryKey: queryKeys.auth.all() });
    },
  });
}

export function useReauthenticate() {
  // ReauthDialog shows a wrong password inside the dialog.
  return useMutation({ mutationFn: reauthenticate, meta: { errorToast: false } });
}

export function useRequestPasswordReset() {
  // ForgotPasswordPage shows errors next to the form.
  return useMutation({ mutationFn: requestPasswordReset, meta: { errorToast: false } });
}

export function useConfirmPasswordReset() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: confirmPasswordReset,
    meta: { errorToast: false },
    // The API ends every session of the user, so whatever this browser cached as "logged in" is stale.
    onSuccess: () => {
      queryClient.clear();
    },
  });
}

export function useInvitation(token: string) {
  return useQuery({
    queryKey: queryKeys.auth.invitation(token),
    queryFn: () => getInvitation(token),
    // AcceptInvitationPage explains an invalid link itself.
    meta: { errorToast: false },
  });
}

export function useAcceptInvitation(token: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: AcceptInvitationRequest) => acceptInvitation(token, body),
    meta: { errorToast: false },
    onSuccess: (me: MeRead) => {
      queryClient.setQueryData(queryKeys.auth.me(), me);
    },
  });
}

export function useSetupTotp() {
  // TotpScreen shows errors next to the form.
  return useMutation({ mutationFn: setupTotp, meta: { errorToast: false } });
}

export function useVerifyTotp() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: verifyTotp,
    meta: { errorToast: false },
    // The session is now MFA-verified: reload `get_me` so `mfa_verified` becomes true.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.auth.me() }),
  });
}
