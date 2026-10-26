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
      animate={{ width: collapsed ? 72 : 244 }}
      transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
      className="relative flex flex-shrink-0 flex-col border-r border-violet-950/30 bg-[#211b3a] text-white dark:border-zinc-800/80 dark:bg-[#171329]"
    >
      {/* Logo */}
      <div className="flex h-20 items-center border-b border-white/10 px-5">
        <Link href="/dashboard" className="flex items-center gap-2.5 overflow-hidden">
          <AnimatePresence initial={false}>
            <BrandLogo showWordmark={!collapsed} wordmarkClassName="!text-white [&_span]:!text-[#a8f0dc]" />
          </AnimatePresence>
        </Link>
      </div>

      {/* New analysis button */}
      <div className="p-3 pt-6">
        <Link
          href="/upload"
          className={cn(
            "flex items-center gap-2.5 rounded-xl bg-gradient-to-r from-violet-500 to-fuchsia-500 px-3 py-3 text-sm font-semibold text-white shadow-lg shadow-violet-950/30 transition-transform hover:-translate-y-0.5",
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
      <nav className="flex-1 space-y-1 px-3 py-5">
        {NAV_ITEMS.map(({ href, label, icon: Icon, exact }) => {
          const isActive = exact ? pathname === href : pathname.startsWith(href)
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "group flex items-center gap-3 rounded-xl px-3 py-3 text-sm transition-all",
                isActive
                  ? "bg-white/15 font-semibold text-white shadow-inner shadow-white/5"
                  : "text-violet-100/65 hover:bg-white/10 hover:text-white",
                collapsed && "justify-center px-2"
              )}
            >
              <Icon
                className={cn(
                  "h-[18px] w-[18px] flex-shrink-0 transition-colors",
                  isActive
                    ? "text-[#b6ffde]"
                    : "text-violet-200/60 group-hover:text-white"
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
      <div className="border-t border-white/10 p-3">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              className={cn(
                "flex w-full items-center gap-2.5 rounded-xl p-2 text-left transition-colors hover:bg-white/10",
                collapsed && "justify-center"
              )}
            >
              <Avatar className="h-7 w-7 flex-shrink-0">
                <AvatarImage src={user?.avatar_url ?? ""} />
                <AvatarFallback className="bg-violet-300 text-xs text-violet-950">
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
                    <p className="truncate text-xs font-medium text-white">
                      {user?.full_name ?? user?.email}
                    </p>
                    {user?.full_name && (
                      <p className="truncate text-[11px] text-violet-200/60">
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
        className="absolute -right-3 top-16 flex h-6 w-6 items-center justify-center rounded-full border border-violet-200 bg-white shadow-sm transition-colors hover:bg-violet-50"
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
