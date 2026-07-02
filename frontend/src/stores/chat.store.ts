import { create } from "zustand"
import type { ChatMessage, ChatSession } from "@/types"

interface ChatState {
  sessions: ChatSession[]
  activeSessionId: string | null
  messages: Record<string, ChatMessage[]>
  isStreaming: boolean
  streamingContent: string
  setSessions: (sessions: ChatSession[]) => void
  setActiveSession: (sessionId: string | null) => void
  addMessage: (sessionId: string, message: ChatMessage) => void
  setMessages: (sessionId: string, messages: ChatMessage[]) => void
  appendStreamingToken: (token: string) => void
  setStreaming: (streaming: boolean) => void
  commitStreamingMessage: (sessionId: string, message: ChatMessage) => void
}

export const useChatStore = create<ChatState>((set) => ({
  sessions: [],
  activeSessionId: null,
  messages: {},
  isStreaming: false,
  streamingContent: "",
  setSessions: (sessions) => set({ sessions }),
  setActiveSession: (sessionId) => set({ activeSessionId: sessionId }),
  addMessage: (sessionId, message) =>
    set((state) => ({
      messages: {
        ...state.messages,
        [sessionId]: [...(state.messages[sessionId] ?? []), message],
      },
    })),
  setMessages: (sessionId, messages) =>
    set((state) => ({
      messages: { ...state.messages, [sessionId]: messages },
    })),
  appendStreamingToken: (token) =>
    set((state) => ({ streamingContent: state.streamingContent + token })),
  setStreaming: (isStreaming) =>
    set({ isStreaming, streamingContent: isStreaming ? "" : "" }),
  commitStreamingMessage: (sessionId, message) =>
    set((state) => ({
      isStreaming: false,
      streamingContent: "",
      messages: {
        ...state.messages,
        [sessionId]: [...(state.messages[sessionId] ?? []), message],
      },
    })),
}))
