import type { Metadata, Viewport } from "next"
import { ThemeProvider } from "next-themes"
import { Toaster } from "sonner"
import { Providers } from "@/components/layout/providers"
import "./globals.css"

export const metadata: Metadata = {
  title: {
    template: "%s | Zephyr",
    default: "Zephyr - Clear insights from your data",
  },
  description:
    "Upload a spreadsheet to see clear charts, useful findings, and answers about your data.",
  keywords: [
    "data analysis",
    "AI insights",
    "dashboard generator",
    "business intelligence",
    "CSV analysis",
    "data visualisation",
  ],
  authors: [{ name: "Zephyr" }],
  creator: "Zephyr",
  icons: {
    icon: "/logo/06-favicon-32x32-production.svg",
  },
  metadataBase: new URL(
    process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000"
  ),
  openGraph: {
    type: "website",
    locale: "en_US",
    url: "/",
    title: "Zephyr",
    description: "Clear charts, useful findings, and answers from your spreadsheet",
    siteName: "Zephyr",
  },
  twitter: {
    card: "summary_large_image",
    title: "Zephyr",
    description: "Clear charts, useful findings, and answers from your spreadsheet",
  },
  robots: {
    index: true,
    follow: true,
  },
}

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0f172a" },
  ],
  width: "device-width",
  initialScale: 1,
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className="min-h-screen bg-background font-sans antialiased"
        suppressHydrationWarning
      >
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          <Providers>{children}</Providers>
          <Toaster richColors position="top-right" />
        </ThemeProvider>
      </body>
    </html>
  )
}
