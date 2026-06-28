"use client";

import { Children, isValidElement, type ReactNode, useState } from "react";
import { Bot, Check, Copy, User } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChatRole } from "@/lib/enums";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export interface Message {
  id: string;
  role: ChatRole;
  content: string;
}

interface ChatMessageProps {
  message: Message;
}

function getCodeBlockLanguage(children: ReactNode) {
  const child = Children.toArray(children)[0];

  if (!isValidElement(child)) {
    return "terminal";
  }

  const childProps = child.props as { className?: string };
  const className =
    typeof childProps.className === "string" ? childProps.className : "";
  const match = className.match(/language-([\w-]+)/);

  return match?.[1] ?? "terminal";
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === ChatRole.USER;
  const isStreamingAssistant = !isUser && message.content.trim().length === 0;
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!message.content.trim()) {
      return;
    }

    await navigator.clipboard.writeText(message.content);
    setCopied(true);

    window.setTimeout(() => {
      setCopied(false);
    }, 2000);
  };

  return (
    <div
      className={cn(
        "flex min-w-0 max-w-full gap-4 py-10 px-2.5",
        isUser ? "bg-transparent" : "bg-muted/30"
      )}
    >
      <div
        className={cn(
          "flex size-8 shrink-0 items-center justify-center rounded-full",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-secondary text-secondary-foreground"
        )}
      >
        {isUser ? <User className="size-4" /> : <Bot className="size-4" />}
      </div>
      <div className="min-w-0 flex-1 space-y-2">
        {isUser ? (
          <>
            <p className="text-sm font-medium text-foreground">Você</p>
            <div className="text-sm text-foreground/90 whitespace-pre-wrap break-words [overflow-wrap:anywhere] leading-relaxed">
              {message.content}
            </div>
          </>
        ) : (
          <>
            <div className="flex min-w-0 items-start justify-between gap-3">
              <p className="text-sm font-medium text-foreground">Assistente</p>
              {!isStreamingAssistant && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  className="size-7 rounded-full text-muted-foreground hover:text-foreground"
                  onClick={handleCopy}
                  aria-label={copied ? "Resposta copiada" : "Copiar resposta"}
                >
                  {copied ? (
                    <Check className="size-3.5" />
                  ) : (
                    <Copy className="size-3.5" />
                  )}
                </Button>
              )}
            </div>
            {isStreamingAssistant ? (
              <div className="flex gap-1 pt-1">
                <span className="size-2 rounded-full bg-muted-foreground/50 animate-bounce [animation-delay:0ms]" />
                <span className="size-2 rounded-full bg-muted-foreground/50 animate-bounce [animation-delay:150ms]" />
                <span className="size-2 rounded-full bg-muted-foreground/50 animate-bounce [animation-delay:300ms]" />
              </div>
            ) : (
              <div className="min-w-0 max-w-full text-sm text-foreground/90 leading-relaxed break-words [overflow-wrap:anywhere] [&_a]:break-all [&_a]:text-primary [&_a]:underline [&_code]:rounded [&_code]:bg-background/80 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[0.9em] [&_li]:ml-5 [&_li]:list-disc [&_li]:break-words [&_ol]:ml-5 [&_ol]:list-decimal [&_p]:break-words [&_p:not(:first-child)]:mt-3 [&_pre]:max-w-full [&_pre]:overflow-x-auto [&_pre]:rounded-xl [&_pre]:bg-background/80 [&_pre]:p-4 [&_pre]:text-xs [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_ul]:ml-5 [&_ul]:list-disc [&_ul:not(:first-child)]:mt-3">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    pre({ children }) {
                      const language = getCodeBlockLanguage(children);

                      return (
                        <div className="my-4 w-full max-w-full overflow-hidden rounded-2xl border border-zinc-300 bg-zinc-50 text-zinc-900 shadow-lg dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100">
                          <div className="flex items-center justify-between border-b border-zinc-300 px-4 py-2 dark:border-zinc-800">
                            <div className="flex items-center gap-2">
                              <span className="size-2.5 rounded-full bg-red-400" />
                              <span className="size-2.5 rounded-full bg-amber-400" />
                              <span className="size-2.5 rounded-full bg-emerald-400" />
                            </div>
                            <span className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">
                              {language}
                            </span>
                          </div>
                          <pre className="max-w-full overflow-x-auto bg-transparent p-4 text-xs leading-6 text-zinc-900 dark:text-zinc-100">
                            {children}
                          </pre>
                        </div>
                      );
                    },
                    code({ className, children, ...props }) {
                      const isBlock =
                        typeof className === "string" &&
                        className.includes("language-");

                      if (isBlock) {
                        return (
                          <code
                            className="bg-transparent p-0 font-mono text-xs text-zinc-900 dark:text-zinc-100"
                            {...props}
                          >
                            {children}
                          </code>
                        );
                      }

                      return (
                        <code
                          className="rounded bg-background/80 px-1.5 py-0.5 font-mono text-[0.9em]"
                          {...props}
                        >
                          {children}
                        </code>
                      );
                    }
                  }}
                >
                  {message.content}
                </ReactMarkdown>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
