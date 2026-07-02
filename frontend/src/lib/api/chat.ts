import { get, post, del } from "@/lib/api/client"
import type { ChatMessage, ChatSession } from "@/types"

export const chatApi = {
  getSessions(analysisId: string): Promise<ChatSession[]> {
    return get(`/chat/sessions`, { params: { analysis_id: analysisId } })
  },

  getSession(sessionId: string): Promise<ChatSession> {
    return get(`/chat/sessions/${sessionId}`)
  },

  getMessages(sessionId: string): Promise<ChatMessage[]> {
    return get(`/chat/sessions/${sessionId}/messages`)
  },

  sendMessage(
    sessionId: string,
    content: string
  ): Promise<ChatMessage> {
    return post(`/chat/sessions/${sessionId}/messages`, { content })
  },

  createSession(analysisId: string, title?: string): Promise<ChatSession> {
    return post("/chat/sessions", { analysis_id: analysisId, title })
  },

  deleteSession(sessionId: string): Promise<void> {
    return del(`/chat/sessions/${sessionId}`)
  },
}
