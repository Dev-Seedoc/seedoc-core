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
} from "../endpoints";
import { queryKeys } from "../queryKeys";
import type { AcceptInvitationRequest, MeRead } from "../types";

// No toast: `unauthenticated` is the normal answer when nobody is logged in; the shell redirects to /login.
export function useMe() {
  return useQuery({ queryKey: queryKeys.auth.me(), queryFn: getMe, meta: { errorToast: false } });
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
    // Drop every cached response so the next user never sees the previous user's data.
    onSettled: () => {
      queryClient.clear();
    },
  });
}

export function useReauthenticate() {
  return useMutation({ mutationFn: reauthenticate });
}

export function useRequestPasswordReset() {
  // ForgotPasswordPage shows errors next to the form.
  return useMutation({ mutationFn: requestPasswordReset, meta: { errorToast: false } });
}

export function useConfirmPasswordReset() {
  return useMutation({ mutationFn: confirmPasswordReset });
}

export function useInvitation(token: string) {
  return useQuery({ queryKey: queryKeys.auth.invitation(token), queryFn: () => getInvitation(token) });
}

export function useAcceptInvitation(token: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: AcceptInvitationRequest) => acceptInvitation(token, body),
    onSuccess: (me: MeRead) => {
      queryClient.setQueryData(queryKeys.auth.me(), me);
    },
  });
}
