import { getMailpitUrl } from "./env.ts";

// Reads mails the local API sent to Mailpit (`make up`): GET /api/v1/messages (newest first) → GET /api/v1/message/{ID}.
// The API sends after its transaction commits, in the background, so the mail can arrive a moment after the click.

interface MailpitAddress {
  Address: string;
}

interface MailpitSummary {
  ID: string;
  To: MailpitAddress[] | null;
}

interface MailpitMessage {
  Text: string;
}

const POLL_INTERVAL_MS = 500;
const DEFAULT_TIMEOUT_MS = 15_000;
// The path of `invitation_url` in the invitation_tenant_member mail. Only the path is used, so the test opens it on
// E2E_BASE_URL whatever APP_URL the API has.
const INVITATION_PATH = /\/invite\/[A-Za-z0-9_-]+/;

async function getJson<T>(path: string): Promise<T> {
  const url = `${getMailpitUrl()}${path}`;
  let response: Response;
  try {
    response = await fetch(url);
  } catch (error) {
    throw new Error(`Mailpit is not reachable at ${getMailpitUrl()} (is \`make up\` running?)`, { cause: error });
  }
  if (!response.ok) {
    throw new Error(`Mailpit answered ${String(response.status)} for ${path}`);
  }
  return (await response.json()) as T;
}

async function findNewestMessageId(email: string): Promise<string | undefined> {
  const { messages } = await getJson<{ messages: MailpitSummary[] }>("/api/v1/messages?limit=50");
  const address = email.toLowerCase();
  return messages.find((message) => message.To?.some((to) => to.Address.toLowerCase() === address))?.ID;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// `/invite/<token>` from the newest mail to `email`; waits until it arrives. Each run invites a new address, so an
// older mail can never be picked up by mistake.
export async function findInvitationPath(email: string, timeoutMs: number = DEFAULT_TIMEOUT_MS): Promise<string> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const id = await findNewestMessageId(email);
    if (id) {
      const { Text } = await getJson<MailpitMessage>(`/api/v1/message/${encodeURIComponent(id)}`);
      const path = INVITATION_PATH.exec(Text)?.[0];
      if (!path) {
        throw new Error(`the newest mail to ${email} contains no /invite/ link`);
      }
      return path;
    }
    if (Date.now() > deadline) {
      throw new Error(`no mail to ${email} in Mailpit after ${String(timeoutMs / 1000)} s (did the API send it?)`);
    }
    await sleep(POLL_INTERVAL_MS);
  }
}
