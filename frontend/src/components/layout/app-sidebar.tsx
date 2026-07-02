"use client"

import { useState } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { motion, AnimatePresence } from "framer-motion"
import {
  LayoutDashboard,
  BarChart3,
  Settings,
  Upload,
  ChevronLeft,
  ChevronRight,
  LogOut,
  Moon,
  Sun,
} from "lucide-react"
import { useTheme } from "next-themes"
import { cn } from "@/lib/utils"
import { useAuth } from "@/hooks/use-auth"
import { BrandLogo } from "@/components/layout/brand-logo"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { getInitials } from "@/lib/utils"

const NAV_ITEMS = [
  {
    href: "/dashboard",
    label: "Dashboard",
    icon: LayoutDashboard,
    exact: true,
  },
  { href: "/analyses", label: "Analyses", icon: BarChart3 },
  { href: "/settings", label: "Settings", icon: Settings },
]

export function AppSidebar() {
  const [collapsed, setCollapsed] = useState(false)
  const pathname = usePathname()
  const { user, signOut } = useAuth()
  const { theme, setTheme } = useTheme()

  return (
    <motion.aside
      animate={{ width: collapsed ? 64 : 220 }}
      transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
      className="relative flex flex-shrink-0 flex-col border-r border-zinc-200/80 bg-white dark:border-zinc-800/80 dark:bg-zinc-900"
    >
      {/* Logo */}
      <div className="flex h-14 items-center border-b border-zinc-200/80 px-4 dark:border-zinc-800/80">
        <Link href="/dashboard" className="flex items-center gap-2.5 overflow-hidden">
          <AnimatePresence initial={false}>
            <BrandLogo showWordmark={!collapsed} />
          </AnimatePresence>
        </Link>
      </div>

      {/* New analysis button */}
      <div className="p-3">
        <Link
          href="/upload"
          className={cn(
            "flex items-center gap-2.5 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500",
            collapsed && "justify-center px-0"
          )}
        >
          <Upload className="h-4 w-4 flex-shrink-0" />
          <AnimatePresence>
            {!collapsed && (
              <motion.span
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="whitespace-nowrap"
              >
                New analysis
              </motion.span>
            )}
          </AnimatePresence>
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-0.5 px-2 py-2">
        {NAV_ITEMS.map(({ href, label, icon: Icon, exact }) => {
          const isActive = exact ? pathname === href : pathname.startsWith(href)
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "group flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-all",
                isActive
                  ? "bg-zinc-100 font-medium text-zinc-900 dark:bg-zinc-800 dark:text-white"
                  : "text-zinc-500 hover:bg-zinc-50 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800/50 dark:hover:text-white",
                collapsed && "justify-center px-2"
              )}
            >
              <Icon
                className={cn(
                  "h-[18px] w-[18px] flex-shrink-0 transition-colors",
                  isActive
                    ? "text-zinc-900 dark:text-white"
                    : "text-zinc-400 group-hover:text-zinc-900 dark:group-hover:text-white"
                )}
              />
              <AnimatePresence>
                {!collapsed && (
                  <motion.span
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="whitespace-nowrap"
                  >
                    {label}
                  </motion.span>
                )}
              </AnimatePresence>
            </Link>
          )
        })}
      </nav>

      {/* User menu */}
      <div className="border-t border-zinc-200/80 p-3 dark:border-zinc-800/80">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              className={cn(
                "flex w-full items-center gap-2.5 rounded-lg p-2 text-left transition-colors hover:bg-zinc-50 dark:hover:bg-zinc-800/50",
                collapsed && "justify-center"
              )}
            >
              <Avatar className="h-7 w-7 flex-shrink-0">
                <AvatarImage src={user?.avatar_url ?? ""} />
                <AvatarFallback className="bg-blue-100 text-xs text-blue-700 dark:bg-blue-900 dark:text-blue-300">
                  {getInitials(user?.full_name ?? user?.email ?? "U")}
                </AvatarFallback>
              </Avatar>
              <AnimatePresence>
                {!collapsed && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="min-w-0 flex-1"
                  >
                    <p className="truncate text-xs font-medium text-zinc-900 dark:text-white">
                      {user?.full_name ?? user?.email}
                    </p>
                    {user?.full_name && (
                      <p className="truncate text-[11px] text-zinc-400">
                        {user.email}
                      </p>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" side="right" className="w-48">
            <DropdownMenuItem
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            >
              {theme === "dark" ? (
                <Sun className="mr-2 h-4 w-4" />
              ) : (
                <Moon className="mr-2 h-4 w-4" />
              )}
              {theme === "dark" ? "Light mode" : "Dark mode"}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={signOut} className="text-red-500 focus:text-red-500">
              <LogOut className="mr-2 h-4 w-4" />
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Collapse toggle */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="absolute -right-3 top-14 flex h-6 w-6 items-center justify-center rounded-full border border-zinc-200 bg-white shadow-sm transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
      >
        {collapsed ? (
          <ChevronRight className="h-3 w-3 text-zinc-500" />
        ) : (
          <ChevronLeft className="h-3 w-3 text-zinc-500" />
        )}
      </button>
    </motion.aside>
  )
}
