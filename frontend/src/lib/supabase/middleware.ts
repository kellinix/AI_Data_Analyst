import { createServerClient } from "@supabase/ssr"
import { type NextRequest, NextResponse } from "next/server"

type CookieToSet = {
  name: string
  value: string
  options?: Parameters<ReturnType<typeof NextResponse.next>["cookies"]["set"]>[2]
}

export async function updateSession(request: NextRequest) {
  const host = request.headers.get("host") ?? ""
  if (host.startsWith("0.0.0.0")) {
    const url = request.nextUrl.clone()
    url.hostname = "localhost"
    return NextResponse.redirect(url)
  }

  let supabaseResponse = NextResponse.next({ request })

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll()
        },
        setAll(cookiesToSet: CookieToSet[]) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value)
          )
          supabaseResponse = NextResponse.next({ request })
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          )
        },
      },
    }
  )

  // Refresh session — do not remove
  const {
    data: { user },
  } = await supabase.auth.getUser()

  const { pathname } = request.nextUrl

  // Protected routes
  const protectedPaths = ["/dashboard", "/analysis", "/settings", "/upload"]
  const isProtected = protectedPaths.some((p) => pathname.startsWith(p))

  // Auth routes (redirect away if already logged in)
  const authPaths = ["/login", "/register"]
  const isAuthPage = authPaths.some((p) => pathname.startsWith(p))

  if (isProtected && !user) {
    const loginUrl = request.nextUrl.clone()
    loginUrl.pathname = "/login"
    loginUrl.searchParams.set("redirectTo", pathname)
    return NextResponse.redirect(loginUrl)
  }

  if (isAuthPage && user) {
    const dashboardUrl = request.nextUrl.clone()
    dashboardUrl.pathname = "/dashboard"
    return NextResponse.redirect(dashboardUrl)
  }

  return supabaseResponse
}
