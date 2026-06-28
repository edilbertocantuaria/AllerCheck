import {
  callUpstream,
  getAuthorizationHeader,
  jsonError,
  parseJsonBody,
  toErrorResponseFromUpstream
} from "@/lib/api-route-utils";
import { CacheMode, HttpMethod, HttpStatus } from "@/lib/enums";

export async function POST(request: Request) {
  const payload = await parseJsonBody<unknown>(request);
  const authHeader = getAuthorizationHeader(request);

  if (!payload) {
    return jsonError(
      "Corpo da requisicao invalido.",
      HttpStatus.BAD_REQUEST,
      "INVALID_REQUEST_BODY"
    );
  }

  const upstreamResponse = await callUpstream({
    path: "/chat",
    method: HttpMethod.POST,
    body: payload,
    authorization: authHeader,
    includeJsonContentType: true
  });

  if (!upstreamResponse) {
    return jsonError(
      "Nao foi possivel conectar a API.",
      HttpStatus.BAD_GATEWAY,
      "UPSTREAM_UNREACHABLE"
    );
  }

  if (!upstreamResponse.ok) {
    return toErrorResponseFromUpstream(
      upstreamResponse,
      "A API retornou um erro ao processar a mensagem.",
      "UPSTREAM_CHAT_ERROR"
    );
  }

  return new Response(upstreamResponse.body, {
    status: upstreamResponse.status,
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": CacheMode.NO_STORE
    }
  });
}
