"use client"

import { motion } from "framer-motion"
import { BarChart3, Bot, User } from "lucide-react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { cn } from "@/lib/utils"
import type { ChartConfig, ChatMessage as ChatMessageType } from "@/types"

interface ChatMessageProps {
  message: ChatMessageType
  onOpenChart?: (chart: ChartConfig) => void
}

export function ChatMessage({ message, onOpenChart }: ChatMessageProps) {
  const isUser = message.role === "user"

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className={cn("flex gap-2.5", isUser && "flex-row-reverse")}
    >
      {/* Avatar */}
      <div
        className={cn(
          "flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full",
          isUser
            ? "bg-blue-600"
            : "bg-zinc-100 dark:bg-zinc-800"
        )}
      >
        {isUser ? (
          <User className="h-3.5 w-3.5 text-white" />
        ) : (
          <Bot className="h-3.5 w-3.5 text-zinc-500 dark:text-zinc-400" />
        )}
      </div>

      {/* Bubble */}
      <div
        className={cn(
          "max-w-[82%] rounded-2xl px-3.5 py-2.5",
          isUser
            ? "rounded-tr-sm bg-blue-600 text-white"
            : "rounded-tl-sm bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-white"
        )}
      >
        {isUser ? (
          <p className="text-sm">{message.content}</p>
        ) : (
          <div className="prose prose-sm dark:prose-invert max-w-none [&_p]:my-1 [&_ul]:my-1 [&_li]:my-0.5 [&_table]:text-xs [&_code]:rounded [&_code]:bg-zinc-200 [&_code]:px-1 [&_code]:dark:bg-zinc-700">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {message.content}
            </ReactMarkdown>
          </div>
        )}
        {!isUser && message.chart_config && onOpenChart && (
          <button
            type="button"
            onClick={() => onOpenChart(message.chart_config!)}
            className="mt-3 inline-flex h-8 items-center gap-2 rounded-md border border-blue-200 bg-white px-2.5 text-xs font-medium text-blue-700 transition-colors hover:bg-blue-50 dark:border-blue-800 dark:bg-zinc-900 dark:text-blue-300 dark:hover:bg-blue-950/40"
          >
            <BarChart3 className="h-3.5 w-3.5" />
            View chart
          </button>
        )}
      </div>
    </motion.div>
  )
}
