import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

// Public routes that don't require authentication
const PUBLIC_ROUTES = ['/login', '/register', '/healthz'];

// Routes that should redirect to /chat if already authenticated
const AUTH_ROUTES = ['/login', '/register'];

export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  // CRITICAL: Never intercept Next.js internal routes or API routes
  if (
    pathname.startsWith('/_next') ||
    pathname.startsWith('/api') ||
    pathname === '/favicon.ico' ||
    pathname === '/robots.txt' ||
    pathname === '/sitemap.xml' ||
    pathname.startsWith('/healthz')
  ) {
    return NextResponse.next();
  }

  // Get auth token from cookie (if stored in cookie) or check localStorage flag
  // Note: We can't access localStorage in middleware, so we use a simple heuristic
  // The actual auth check happens client-side in useRequireAuth hook

  // For now, we'll just handle basic redirects
  const isPublicRoute = PUBLIC_ROUTES.some(route => pathname.startsWith(route));

  // Redirect root to chat
  if (pathname === '/') {
    return NextResponse.redirect(new URL('/chat', request.url));
  }

  // If accessing protected route without session, let client-side handle it
  // (useRequireAuth will redirect to login if needed)

  // Add pathname header for debugging
  const response = NextResponse.next();
  response.headers.set('x-pathname', pathname);

  return response;
}

// DEFENSIVE MATCHER: Exclude Next.js internals and API routes
export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico, robots.txt, sitemap.xml (static files)
     * - api, healthz routes (API/health routes)
     */
    '/((?!_next/static|_next/image|favicon.ico|robots.txt|sitemap.xml|api|healthz).*)',
  ],
};