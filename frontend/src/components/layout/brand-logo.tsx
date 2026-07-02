"use client"

import { motion } from "framer-motion"
import { cn } from "@/lib/utils"

interface BrandLogoProps {
  showWordmark?: boolean
  className?: string
  wordmarkClassName?: string
}

export function BrandLogo({
  showWordmark = true,
  className,
  wordmarkClassName,
}: BrandLogoProps) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <img
        src="/logo/06-favicon-32x32-production.svg"
        alt=""
        aria-hidden="true"
        className="h-8 w-8 flex-shrink-0 rounded-md"
      />
      {showWordmark && (
        <motion.span
          initial={{ opacity: 0, x: -6 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -6 }}
          transition={{ duration: 0.15 }}
          className={cn(
            "text-[15px] font-semibold tracking-tight text-zinc-900 dark:text-white",
            wordmarkClassName
          )}
        >
          Insight<span className="text-blue-600 dark:text-blue-400">Flow</span>
        </motion.span>
      )}
    </span>
  )
}
