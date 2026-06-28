import {
  callUpstream,
  jsonDetailError,
  parseJsonBody,
  toErrorResponseFromUpstream,
  toJsonResponse
} from "@/lib/api-route-utils";
import { HttpMethod, HttpStatus } from "@/lib/enums";

interface GoogleAuthPayload {
  id_token: string;
}

export async function POST(request: Request) {
  const payload = await parseJsonBody<GoogleAuthPayload>(request);

  if (!payload) {
    return jsonDetailError(
      "Corpo da requisição inválido.",
      HttpStatus.BAD_REQUEST,
      "INVALID_REQUEST_BODY"
    );
  }

  const upstreamResponse = await callUpstream({
    path: "/auth/google",
    method: HttpMethod.POST,
    body: payload,
    includeJsonContentType: true
  });

  if (!upstreamResponse) {
    return jsonDetailError(
      "Não foi possível conectar à API.",
      HttpStatus.BAD_GATEWAY,
      "UPSTREAM_UNREACHABLE"
    );
  }

  if (!upstreamResponse.ok) {
    return toErrorResponseFromUpstream(
      upstreamResponse,
      "Falha na autenticação Google.",
      "UPSTREAM_AUTH_ERROR"
    );
  }

  return toJsonResponse(upstreamResponse);
}
