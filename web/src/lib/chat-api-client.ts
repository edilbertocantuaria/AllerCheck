import { CacheMode, HttpMethod, HttpStatus } from "@/lib/enums";
import {
  type APIConversation,
  type APIMessage,
  type ChatParameters
} from "@/lib/chat-types";
import { type Message } from "@/components/chat-message";

interface ApiClientErrorPayload {
  detail?: string;
  error?: string;
}

export class ApiClientError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function buildAuthHeaders(token?: string) {
  const headers: HeadersInit = { "Content-Type": "application/json" };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  return headers;
}

async function readErrorMessage(response: Response, fallbackMessage: string) {
  try {
    const payload = (await response.json()) as ApiClientErrorPayload;
    if (payload.error) return payload.error;
    if (payload.detail) return payload.detail;
  } catch {
    const text = await response.text();
    if (text) return text;
  }

  return fallbackMessage;
}

async function requestJson<T>(
  path: string,
  method: HttpMethod,
  token?: string,
  body?: unknown
): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: buildAuthHeaders(token),
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: CacheMode.NO_STORE
  });

  if (!response.ok) {
    const message = await readErrorMessage(response, "Falha na requisicao.");
    throw new ApiClientError(message, response.status);
  }

  return (await response.json()) as T;
}

export async function listConversations(token: string) {
  return requestJson<APIConversation[]>(
    "/api/conversations",
    HttpMethod.GET,
    token
  );
}

export async function getConversationMessages(
  conversationId: string,
  token: string
) {
  return requestJson<APIMessage[]>(
    `/api/conversations/${conversationId}`,
    HttpMethod.GET,
    token
  );
}

export async function createConversation(
  token: string,
  title: string | null = null
) {
  return requestJson<APIConversation>(
    "/api/conversations",
    HttpMethod.POST,
    token,
    { title }
  );
}

export async function deleteConversation(
  conversationId: string,
  token: string
) {
  const response = await fetch(`/api/conversations/${conversationId}`, {
    method: HttpMethod.DELETE,
    headers: { Authorization: `Bearer ${token}` },
    cache: CacheMode.NO_STORE
  });

  if (response.status === HttpStatus.NO_CONTENT) {
    return;
  }

  if (!response.ok) {
    const message = await readErrorMessage(
      response,
      "Falha ao deletar conversa."
    );
    throw new ApiClientError(message, response.status);
  }
}

interface SendChatAuthenticatedPayload extends ChatParameters {
  conversation_id: string;
  question: string;
}

interface SendChatGuestPayload extends ChatParameters {
  question: string;
  history: Array<{ role: Message["role"]; content: string }>;
}

export async function sendChatRequest(
  content: string,
  parameters: ChatParameters,
  options: {
    token?: string;
    isAuthenticated: boolean;
    chatId: string;
    existingMessages: Message[];
  }
) {
  const body: SendChatAuthenticatedPayload | SendChatGuestPayload =
    options.isAuthenticated && options.token
      ? {
          conversation_id: options.chatId,
          question: content,
          ...parameters
        }
      : {
          question: content,
          history: options.existingMessages.map((message) => ({
            role: message.role,
            content: message.content
          })),
          ...parameters
        };

  const response = await fetch("/api/chat", {
    method: HttpMethod.POST,
    headers: buildAuthHeaders(options.token),
    body: JSON.stringify(body)
  });

  if (!response.ok) {
    const message = await readErrorMessage(
      response,
      "Nao foi possivel obter resposta da API."
    );
    throw new ApiClientError(message, response.status);
  }

  if (!response.body) {
    throw new ApiClientError(
      "A API nao retornou corpo de resposta.",
      HttpStatus.BAD_GATEWAY
    );
  }

  return response;
}
