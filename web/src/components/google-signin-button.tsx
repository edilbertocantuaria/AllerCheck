"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Script from "next/script";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/auth-context";

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (params: {
            client_id: string;
            callback: (response: { credential?: string }) => void;
          }) => void;
          renderButton: (
            parent: HTMLElement,
            options: {
              type?: "standard" | "icon";
              theme?: "outline" | "filled_blue" | "filled_black";
              size?: "large" | "medium" | "small";
              shape?: "rectangular" | "pill" | "circle" | "square";
              text?: "signin_with" | "signup_with" | "continue_with" | "signin";
              width?: number;
              logo_alignment?: "left" | "center";
            }
          ) => void;
        };
      };
    };
  }
}

interface GoogleSignInButtonProps {
  text?: "signin_with" | "signup_with" | "continue_with" | "signin";
  onError: (message: string) => void;
}

export function GoogleSignInButton({
  text = "continue_with",
  onError
}: GoogleSignInButtonProps) {
  const router = useRouter();
  const { loginWithGoogle } = useAuth();
  const [scriptReady, setScriptReady] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (window.google?.accounts?.id) {
      setScriptReady(true);
    }
  }, []);

  const renderGoogleButton = useCallback(() => {
    const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;

    if (!scriptReady || !containerRef.current || !window.google?.accounts?.id) {
      return;
    }

    if (!clientId) {
      onError(
        "Google Login não configurado: defina NEXT_PUBLIC_GOOGLE_CLIENT_ID"
      );
      return;
    }

    containerRef.current.innerHTML = "";

    window.google.accounts.id.initialize({
      client_id: clientId,
      callback: async (response) => {
        const credential = response.credential;
        if (!credential) {
          onError("Falha ao obter credencial do Google");
          return;
        }

        try {
          await loginWithGoogle(credential);
          router.push("/");
        } catch (err) {
          onError(
            err instanceof Error ? err.message : "Erro ao autenticar com Google"
          );
        }
      }
    });

    window.google.accounts.id.renderButton(containerRef.current, {
      type: "standard",
      theme: "outline",
      size: "large",
      shape: "rectangular",
      text,
      width: 370,
      logo_alignment: "left"
    });
  }, [loginWithGoogle, onError, router, scriptReady, text]);

  useEffect(() => {
    renderGoogleButton();
  }, [renderGoogleButton]);

  return (
    <>
      <Script
        src="https://accounts.google.com/gsi/client"
        strategy="afterInteractive"
        onLoad={() => setScriptReady(true)}
      />
      <div className="w-full flex justify-center bg-transparent">
        <div ref={containerRef} className="min-h-10 bg-transparent" />
      </div>
    </>
  );
}
