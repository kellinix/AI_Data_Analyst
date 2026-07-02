"use client"

import dynamic from "next/dynamic"
import { useEffect, useRef, useState } from "react"
import { motion } from "framer-motion"
import { X, Send, Loader2, Bot } from "lucide-react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { chatApi } from "@/lib/api/chat"
import { ScrollArea } from "@/components/ui/scroll-area"
import { ChatMessage } from "@/components/chat/chat-message"
import type { ChartConfig } from "@/types"

const EChartsReact = dynamic(() => import("echarts-for-react"), { ssr: false })

interface ChatPanelProps {
  analysisId: string
  onClose: () => void
}

const SUGGESTIONS = [
  "Summarise the key findings",
  "What are the top performing categories?",
  "Show me any unusual patterns",
  "What should we focus on next?",
]

export function ChatPanel({ analysisId, onClose }: ChatPanelProps) {
  const queryClient = useQueryClient()
  const [input, setInput] = useState("")
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [activeChart, setActiveChart] = useState<ChartConfig | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Load sessions
  const { data: sessions } = useQuery({
    queryKey: ["chat-sessions", analysisId],
    queryFn: () => chatApi.getSessions(analysisId),
  })

  // Create session if none
  const createSession = useMutation({
    mutationFn: () => chatApi.createSession(analysisId),
    onSuccess: (session) => {
      setActiveSessionId(session.id)
      queryClient.invalidateQueries({ queryKey: ["chat-sessions", analysisId] })
    },
  })

  // Load messages for active session
  const { data: messages, isLoading: loadingMessages } = useQuery({
    queryKey: ["chat-messages", activeSessionId],
    queryFn: () => chatApi.getMessages(activeSessionId!),
    enabled: !!activeSessionId,
  })

  // Send message
  const sendMessage = useMutation({
    mutationFn: (content: string) =>
      chatApi.sendMessage(activeSessionId!, content),
    onMutate: async (content) => {
      // Optimistic update
      const userMessage = {
        id: `temp-${Date.now()}`,
        session_id: activeSessionId!,
        role: "user" as const,
        content,
        chart_config: null,
        created_at: new Date().toISOString(),
      }
      queryClient.setQueryData(
        ["chat-messages", activeSessionId],
        (old: typeof messages) => [...(old ?? []), userMessage]
      )
      setInput("")
    },
    onSuccess: (reply) => {
      queryClient.setQueryData(
        ["chat-messages", activeSessionId],
        (old: typeof messages) => {
          const filtered = (old ?? []).filter((m) => !m.id.startsWith("temp-"))
          return [...filtered, reply]
        }
      )
      if (reply.chart_config) {
        setActiveChart(reply.chart_config)
      }
    },
    onError: () => {
      toast.error("Failed to send message")
    },
  })

  // Init: use first session or create one
  useEffect(() => {
    if (sessions !== undefined) {
      if (sessions.length > 0) {
        setActiveSessionId(sessions[0].id)
      } else {
        createSession.mutate()
      }
    }
  }, [sessions]) // eslint-disable-line react-hooks/exhaustive-deps

  // Scroll to bottom on new message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  const handleSend = () => {
    const trimmed = input.trim()
    if (!trimmed || sendMessage.isPending || !activeSessionId) return
    sendMessage.mutate(trimmed)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <>
      <motion.aside
        initial={{ x: "100%", opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        exit={{ x: "100%", opacity: 0 }}
        transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
        className="flex w-[380px] flex-shrink-0 flex-col border-l border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900"
      >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-600">
            <Bot className="h-4 w-4 text-white" />
          </div>
          <div>
            <p className="text-sm font-semibold text-zinc-900 dark:text-white">
              Data Assistant
            </p>
            <p className="text-[11px] text-zinc-400">Ask anything about your data</p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="rounded-lg p-1.5 text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-600 dark:hover:bg-zinc-800"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Messages */}
      <ScrollArea className="flex-1 px-4 py-4">
        {loadingMessages ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-5 w-5 animate-spin text-zinc-400" />
          </div>
        ) : messages && messages.length > 0 ? (
          <div className="space-y-4">
            {messages.map((msg) => (
              <ChatMessage
                key={msg.id}
                message={msg}
                onOpenChart={setActiveChart}
              />
            ))}
            {sendMessage.isPending && (
              <div className="flex items-center gap-2 text-zinc-400">
                <Bot className="h-4 w-4" />
                <div className="flex gap-1">
                  {[0, 1, 2].map((i) => (
                    <motion.span
                      key={i}
                      animate={{ opacity: [0.3, 1, 0.3] }}
                      transition={{ repeat: Infinity, duration: 1.2, delay: i * 0.2 }}
                      className="h-1.5 w-1.5 rounded-full bg-zinc-400"
                    />
                  ))}
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        ) : (
          <div className="space-y-4">
            <div className="rounded-xl bg-zinc-50 p-4 dark:bg-zinc-800/50">
              <p className="text-sm text-zinc-600 dark:text-zinc-300">
                👋 I&apos;ve analysed your data. Ask me anything — I can explain trends,
                find patterns, run calculations, and suggest actions.
              </p>
            </div>
            <div className="space-y-2">
              <p className="text-xs font-medium text-zinc-400">Try asking:</p>
              {SUGGESTIONS.map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => setInput(suggestion)}
                  className="block w-full rounded-lg border border-zinc-200 px-3 py-2 text-left text-xs text-zinc-600 transition-colors hover:border-blue-300 hover:bg-blue-50 hover:text-blue-600 dark:border-zinc-700 dark:text-zinc-400 dark:hover:border-blue-700 dark:hover:bg-blue-950/30 dark:hover:text-blue-400"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}
      </ScrollArea>

      {/* Input */}
      <div className="border-t border-zinc-200 p-4 dark:border-zinc-800">
        <div className="flex items-end gap-2 rounded-xl border border-zinc-200 bg-white p-2.5 focus-within:border-blue-400 focus-within:ring-2 focus-within:ring-blue-400/20 dark:border-zinc-700 dark:bg-zinc-800 dark:focus-within:border-blue-500">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your data..."
            rows={1}
            className="flex-1 resize-none bg-transparent text-sm text-zinc-900 placeholder-zinc-400 outline-none dark:text-white"
            style={{ maxHeight: 120 }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || sendMessage.isPending || !activeSessionId}
            className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-blue-600 text-white transition-colors hover:bg-blue-500 disabled:opacity-40"
          >
            {sendMessage.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Send className="h-3.5 w-3.5" />
            )}
          </button>
        </div>
        <p className="mt-1.5 text-center text-[10px] text-zinc-400">
          Powered by GPT-4o · Results may contain errors
        </p>
      </div>
      </motion.aside>
      {activeChart && (
        <ChatChartModal
          chart={activeChart}
          onClose={() => setActiveChart(null)}
        />
      )}
    </>
  )
}

function ChatChartModal({
  chart,
  onClose,
}: {
  chart: ChartConfig
  onClose: () => void
}) {
  const option = withFullDataLabels(chart)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.97, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.18 }}
        className="flex h-[min(620px,86vh)] w-[min(900px,92vw)] flex-col rounded-lg bg-white shadow-2xl dark:bg-zinc-900"
      >
        <div className="flex items-start justify-between border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
          <div>
            <h2 className="text-base font-semibold text-zinc-950 dark:text-white">
              {chart.title}
            </h2>
            {chart.description && (
              <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                {chart.description}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close chart"
            className="flex h-8 w-8 items-center justify-center rounded-md text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-900 dark:hover:bg-zinc-800 dark:hover:text-white"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1 p-4">
          <EChartsReact
            option={option}
            style={{ height: "100%", width: "100%" }}
            notMerge
          />
        </div>
      </motion.div>
    </div>
  )
}

function formatFullNumber(value: unknown): string {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return String(value ?? "")
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: Number.isInteger(numeric) ? 0 : 2,
  }).format(numeric)
}

function withFullDataLabels(chart: ChartConfig): Record<string, unknown> {
  const option: Record<string, unknown> = {
    color: chart.color_scheme,
    backgroundColor: "transparent",
    textStyle: { fontFamily: "Inter, system-ui, sans-serif" },
    ...chart.echarts_option,
  }

  const series = Array.isArray(option.series) ? option.series : []
  return {
    ...option,
    series: series.map((item) => {
      if (!item || typeof item !== "object" || Array.isArray(item)) return item
      const seriesItem = item as Record<string, unknown>
      if (seriesItem.type !== "bar") return seriesItem
      const label =
        seriesItem.label && typeof seriesItem.label === "object" && !Array.isArray(seriesItem.label)
          ? (seriesItem.label as Record<string, unknown>)
          : {}
      return {
        ...seriesItem,
        label: {
          ...label,
          formatter: (params: { value: unknown }) => formatFullNumber(params.value),
        },
      }
    }),
  }
}
