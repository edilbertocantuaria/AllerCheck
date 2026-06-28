"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ChatSidebar } from "./chat-sidebar";
import { ChatInput } from "./chat-input";
import { ChatInterfaceHeader } from "./chat-interface/chat-interface-header";
import { ChatInterfaceContent } from "./chat-interface/chat-interface-content";
import { useChatInterfaceState } from "./chat-interface/use-chat-interface-state";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

export function ChatInterface() {
  const router = useRouter();
  const {
    authLoading,
    isAuthenticated,
    user,
    messages,
    history,
    currentChatId,
    isLoading,
    isLoadingConversations,
    parameters,
    setParameters,
    messagesEndRef,
    handleNewChat,
    handleSelectChat,
    handleDeleteChat,
    handleSendMessage,
    handleLogout
  } = useChatInterfaceState();

  const [sidebarOpen, setSidebarOpen] = useState(true);

  if (authLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <Spinner className="size-8" />
      </div>
    );
  }

  return (
    <div className="flex h-screen min-w-0 bg-background">
      <ChatSidebar
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen(!sidebarOpen)}
        history={history}
        currentChatId={currentChatId}
        onSelectChat={handleSelectChat}
        onNewChat={handleNewChat}
        onDeleteChat={handleDeleteChat}
        isLoading={isLoadingConversations}
      />

      <main
        className={cn(
          "flex min-w-0 flex-1 flex-col transition-all duration-300 ease-in-out",
          sidebarOpen ? "ml-64" : "ml-0"
        )}
      >
        <ChatInterfaceHeader
          sidebarOpen={sidebarOpen}
          isAuthenticated={isAuthenticated}
          userEmail={user?.email}
          parameters={parameters}
          onParametersChange={setParameters}
          onLogout={handleLogout}
          onGoLogin={() => router.push("/login")}
          onGoRegister={() => router.push("/register")}
        />

        <ChatInterfaceContent
          messages={messages}
          messagesEndRef={messagesEndRef}
        />

        <div className="border-t border-border bg-background/80 backdrop-blur-sm px-4 py-3">
          <div className="mx-auto w-full max-w-3xl min-w-0">
            <ChatInput
              onSend={handleSendMessage}
              isLoading={isLoading}
              disabled={false}
            />
          </div>
        </div>
      </main>
    </div>
  );
}
