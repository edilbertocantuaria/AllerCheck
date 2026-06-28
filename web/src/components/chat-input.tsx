"use client";

import { useState, useRef, useEffect } from "react";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";

interface ChatInputProps {
  onSend: (message: string) => void;
  isLoading?: boolean;
  disabled?: boolean;
}

export function ChatInput({ onSend, isLoading, disabled }: ChatInputProps) {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim() && !isLoading && !disabled) {
      onSend(input.trim());
      setInput("");
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  }, [input]);

  return (
    <form onSubmit={handleSubmit} className="relative">
      <div className="relative flex items-center gap-2 rounded-2xl border border-border bg-muted/50 p-4 shadow-lg">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Digite sua mensagem..."
          disabled={isLoading || disabled}
          rows={1}
          className="flex-1 resize-none overflow-y-auto bg-transparent text-sm leading-6 text-foreground placeholder:text-muted-foreground focus:outline-none disabled:opacity-50 max-h-[240px] py-2 [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden"
        />
        <Button
          type="submit"
          size="icon"
          disabled={!input.trim() || isLoading || disabled}
          className="shrink-0 size-9 self-center rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {isLoading ? (
            <Spinner className="size-3.5" />
          ) : (
            <Send className="size-3.5" />
          )}
          <span className="sr-only">Enviar mensagem</span>
        </Button>
      </div>
      <p className="text-xs text-muted-foreground text-center mt-2">
        Pressione Enter para enviar, Shift + Enter para nova linha
      </p>
    </form>
  );
}
