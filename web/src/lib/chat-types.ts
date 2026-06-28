import { ChatRole } from "@/lib/enums";

export interface APIMessage {
  id: string;
  role: ChatRole;
  content: string;
  created_at: string;
}

export interface APIConversation {
  id: string;
  title: string | null;
  created_at: string;
}

export interface ChatParameters {
  frequency_penalty: number;
  presence_penalty: number;
  temperature: number;
  max_tokens: number;
  n: number;
  seed: number;
  stop: string;
}
