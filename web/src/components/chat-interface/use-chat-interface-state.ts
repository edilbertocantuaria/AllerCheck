import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/contexts/auth-context";
import { type ChatHistory } from "@/components/chat-sidebar";
import { type Message } from "@/components/chat-message";
import {
  ApiClientError,
  createConversation,
  deleteConversation,
  getConversationMessages,
  listConversations,
  sendChatRequest
} from "@/lib/chat-api-client";
import { ChatRole, HttpStatus } from "@/lib/enums";
import { type ChatParameters } from "@/lib/chat-types";

export function useChatInterfaceState() {
  const {
    token,
    isLoading: authLoading,
    isAuthenticated,
    logout,
    user
  } = useAuth();

  const [messages, setMessages] = useState<Message[]>([]);
  const [chatMessages, setChatMessages] = useState<Record<string, Message[]>>(
    {}
  );
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingConversations, setIsLoadingConversations] = useState(false);
  const [currentChatId, setCurrentChatId] = useState<string | null>(null);
  const [history, setHistory] = useState<ChatHistory[]>([]);
  const [parameters, setParameters] = useState<ChatParameters>({
    frequency_penalty: 0,
    presence_penalty: 0,
    temperature: 0.7,
    max_tokens: 1024,
    n: 1,
    seed: 0,
    stop: ""
  });

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const currentChatIdRef = useRef<string | null>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    currentChatIdRef.current = currentChatId;
  }, [currentChatId]);

  useEffect(() => {
    if (!isAuthenticated) {
      setIsLoadingConversations(false);
    }
  }, [isAuthenticated]);

  const handleApiError = useCallback(
    (error: unknown, fallbackMessage: string) => {
      if (error instanceof ApiClientError) {
        if (error.status === HttpStatus.UNAUTHORIZED) {
          logout();
        }
        return error.message;
      }

      console.error(fallbackMessage, error);
      return fallbackMessage;
    },
    [logout]
  );

  const loadConversations = useCallback(async () => {
    if (!token) {
      setIsLoadingConversations(false);
      return;
    }

    setIsLoadingConversations(true);

    try {
      const conversations = await listConversations(token);
      setHistory(
        conversations.map((conv) => ({
          id: conv.id,
          title: conv.title || "Conversa sem titulo",
          createdAt: new Date(conv.created_at)
        }))
      );
    } catch (error) {
      handleApiError(error, "Erro ao carregar conversas:");
    } finally {
      setIsLoadingConversations(false);
    }
  }, [token, handleApiError]);

  useEffect(() => {
    if (isAuthenticated && token) {
      loadConversations();
    }
  }, [isAuthenticated, token, loadConversations]);

  const loadMessages = useCallback(
    async (conversationId: string) => {
      if (!token) return;

      try {
        const apiMessages = await getConversationMessages(
          conversationId,
          token
        );
        const formattedMessages: Message[] = apiMessages.map((msg) => ({
          id: msg.id,
          role: msg.role,
          content: msg.content
        }));

        setChatMessages((prev) => ({
          ...prev,
          [conversationId]: formattedMessages
        }));

        if (currentChatIdRef.current === conversationId) {
          setMessages(formattedMessages);
        }
      } catch (error) {
        handleApiError(error, "Erro ao carregar mensagens:");
      }
    },
    [token, handleApiError]
  );

  const syncMessagesForChat = (chatId: string, nextMessages: Message[]) => {
    setChatMessages((prev) => ({
      ...prev,
      [chatId]: nextMessages
    }));

    if (currentChatIdRef.current === chatId) {
      setMessages(nextMessages);
    }
  };

  const syncConversationTitle = useCallback(
    async (conversationId: string) => {
      if (!token) return;

      try {
        const conversations = await listConversations(token);
        const target = conversations.find((conv) => conv.id === conversationId);
        if (!target) return;

        setHistory((prev) =>
          prev.map((chat) =>
            chat.id === conversationId
              ? {
                  ...chat,
                  title: target.title || chat.title
                }
              : chat
          )
        );
      } catch (error) {
        handleApiError(error, "Erro ao sincronizar titulo da conversa:");
      }
    },
    [token, handleApiError]
  );

  const handleNewChat = async () => {
    setCurrentChatId(null);
    currentChatIdRef.current = null;
    setMessages([]);
  };

  const handleSelectChat = async (id: string) => {
    setCurrentChatId(id);
    currentChatIdRef.current = id;

    if (chatMessages[id]) {
      setMessages(chatMessages[id]);
    } else {
      setMessages([]);
      await loadMessages(id);
    }
  };

  const handleDeleteChat = async (id: string) => {
    if (!token) {
      setHistory((prev) => prev.filter((chat) => chat.id !== id));
      setChatMessages((prev) => {
        const nextState = { ...prev };
        delete nextState[id];
        return nextState;
      });

      if (currentChatId === id) {
        setCurrentChatId(null);
        setMessages([]);
      }

      return;
    }

    try {
      await deleteConversation(id, token);
      setHistory((prev) => prev.filter((chat) => chat.id !== id));
      setChatMessages((prev) => {
        const nextState = { ...prev };
        delete nextState[id];
        return nextState;
      });

      if (currentChatId === id) {
        setCurrentChatId(null);
        setMessages([]);
      }
    } catch (error) {
      handleApiError(error, "Erro ao deletar conversa:");
    }
  };

  const handleSendMessage = async (content: string) => {
    let chatId = currentChatId;

    if (!chatId) {
      if (isAuthenticated && token) {
        try {
          const conversation = await createConversation(token);
          chatId = conversation.id;

          const newChat: ChatHistory = {
            id: conversation.id,
            title: "Gerando titulo...",
            createdAt: new Date(conversation.created_at)
          };

          setHistory((prev) => [newChat, ...prev]);
          setCurrentChatId(chatId);
          currentChatIdRef.current = chatId;
        } catch (error) {
          handleApiError(error, "Erro ao criar conversa:");
          return;
        }
      } else {
        chatId = `guest-${Date.now()}`;
        const localTitle =
          content.length > 40 ? `${content.slice(0, 40)}...` : content;
        const newChat: ChatHistory = {
          id: chatId,
          title: localTitle,
          createdAt: new Date()
        };

        setHistory((prev) => [newChat, ...prev]);
        setCurrentChatId(chatId);
        currentChatIdRef.current = chatId;
      }
    }

    const existingMessages = chatMessages[chatId] ?? [];

    const userMessage: Message = {
      id: Date.now().toString(),
      role: ChatRole.USER,
      content
    };

    const assistantMessageId = `${Date.now()}-assistant`;
    const assistantPlaceholder: Message = {
      id: assistantMessageId,
      role: ChatRole.ASSISTANT,
      content: ""
    };

    const nextMessages = [
      ...existingMessages,
      userMessage,
      assistantPlaceholder
    ];

    syncMessagesForChat(chatId, nextMessages);
    setIsLoading(true);

    try {
      const response = await sendChatRequest(content, parameters, {
        token: token || undefined,
        isAuthenticated,
        chatId,
        existingMessages
      });

      if (isAuthenticated && token) {
        await syncConversationTitle(chatId);
      }

      if (!response.body) {
        throw new ApiClientError(
          "A API nao retornou corpo de resposta.",
          HttpStatus.BAD_GATEWAY
        );
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let fullResponse = "";

      while (true) {
        const { done, value } = await reader.read();

        if (done) {
          break;
        }

        fullResponse += decoder.decode(value, { stream: true });

        syncMessagesForChat(
          chatId,
          nextMessages.map((message) =>
            message.id === assistantMessageId
              ? { ...message, content: fullResponse }
              : message
          )
        );
      }
    } catch (error) {
      const errorMessage = handleApiError(
        error,
        "Ocorreu um erro inesperado ao consultar a API."
      );

      syncMessagesForChat(
        chatId,
        nextMessages.map((message) =>
          message.id === assistantMessageId
            ? {
                ...message,
                content: `Erro ao consultar a API: ${errorMessage}`
              }
            : message
        )
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleLogout = () => {
    logout();
    setCurrentChatId(null);
    currentChatIdRef.current = null;
    setMessages([]);
    setChatMessages({});
    setHistory([]);
  };

  return {
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
  };
}
