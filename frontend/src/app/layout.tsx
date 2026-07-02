import type { Metadata, Viewport } from "next"
import { ThemeProvider } from "next-themes"
import { Toaster } from "sonner"
import { Providers } from "@/components/layout/providers"
import "./globals.css"

export const metadata: Metadata = {
  title: {
    template: "%s | InsightFlow",
    default: "InsightFlow - Instant Data Insights",
  },
  description:
    "Upload any dataset and get instant AI-powered charts, insights, and forecasts in seconds. No SQL. No coding.",
  keywords: [
    "data analysis",
    "AI insights",
    "dashboard generator",
    "business intelligence",
    "CSV analysis",
    "data visualisation",
  ],
  authors: [{ name: "InsightFlow" }],
  creator: "InsightFlow",
  icons: {
    icon: "/logo/06-favicon-32x32-production.svg",
  },
  metadataBase: new URL(
    process.env.NEXT_PUBLIC_APP_URL ?? "https://aidashboard.app"
  ),
  openGraph: {
    type: "website",
    locale: "en_US",
    url: "/",
    title: "InsightFlow",
    description: "Instant AI-powered data insights from any spreadsheet",
    siteName: "InsightFlow",
  },
  twitter: {
    card: "summary_large_image",
    title: "InsightFlow",
    description: "Instant AI-powered data insights from any spreadsheet",
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
