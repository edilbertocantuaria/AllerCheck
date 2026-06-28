import { RefObject } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ChatMessage, type Message } from "@/components/chat-message";

interface ChatInterfaceContentProps {
  messages: Message[];
  messagesEndRef: RefObject<HTMLDivElement | null>;
}

export function ChatInterfaceContent({
  messages,
  messagesEndRef
}: ChatInterfaceContentProps) {
  return (
    <ScrollArea className="min-w-0 flex-1">
      <div className="mx-auto w-full max-w-3xl min-w-0 px-4 sm:px-6">
        {messages.length === 0 ? (
          <div className="flex h-[60vh] flex-col items-center justify-center gap-4">
            <img src="/logo.png" alt="AllerCheck" className="size-70" />
            <h2 className="text-2xl font-semibold text-foreground text-center text-balance">
              Como posso ajudar você hoje?
            </h2>
            <p className="max-w-md text-center text-muted-foreground text-balance">
              Faça uma pergunta sobre alergia a medicamentos e eu responderei com de acordo com minha base de conhecimento 🩺
            </p>
          </div>
        ) : (
          <div className="min-w-0 divide-y divide-border/50 pb-4">
            {messages.map((message) => (
              <ChatMessage key={message.id} message={message} />
            ))}
            <div ref={messagesEndRef} className="h-3" />
          </div>
        )}
      </div>
    </ScrollArea>
  );
}
