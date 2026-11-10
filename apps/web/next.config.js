const path = require('path');

/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ['@copilotos/shared'],
  output: 'standalone',
  // Next.js 15: outputFileTracingRoot moved to root level
  outputFileTracingRoot: path.join(__dirname, '../../'),
  experimental: {
    // El proxy de rewrites (/api/* → backend) corta el socket a los 30 s por
    // default y el navegador ve ECONNRESET aunque el backend termine bien
    // (visto en vivo: consulta retail de 45 s completada y guardada, pero el
    // usuario vio "no pude conectar" — card proxy-timeout-chat-largo).
    // Alineado con el presupuesto real del cliente: 120 s chat sin archivos,
    // 180 s análisis de archivos (api-client.ts) + margen.
    proxyTimeout: 200_000,
    // Next.js 15: serverActions config moved to experimental.serverActions
    serverActions: {
      allowedOrigins: [
        'localhost:3000',
        '127.0.0.1:3000',
        '*.localhost:3000',
        '*.saptiva.com',
        ...(process.env.ALLOWED_ORIGINS || '').split(',').filter(Boolean),
      ],
    },
    // Optimize barrel imports for faster builds and smaller bundles
    // See: https://vercel.com/blog/how-we-optimized-package-imports-in-next-js
    optimizePackageImports: [
      '@heroicons/react',
      'lucide-react',
      '@radix-ui/react-icons',
    ],
  },
  async headers() {
    return [
      {
        // Apply anti-cache headers to all API routes and auth pages
        source: '/(api|auth|login|register)/:path*',
        headers: [
          {
            key: 'Cache-Control',
            value: 'no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0',
          },
          {
            key: 'Pragma',
            value: 'no-cache',
          },
          {
            key: 'Expires',
            value: '0',
          },
          {
            key: 'Surrogate-Control',
            value: 'no-store',
          },
        ],
      },
      {
        // CRITICAL: Prevent Cloudflare from caching JavaScript bundles
        // This ensures users always get the latest code with bug fixes
        source: '/_next/static/:path*',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=0, must-revalidate',
          },
          {
            key: 'CDN-Cache-Control',
            value: 'no-store',
          },
          {
            key: 'Cloudflare-CDN-Cache-Control',
            value: 'no-store',
          },
        ],
      },
      {
        // Also prevent HTML page caching
        source: '/:path*',
        headers: [
          {
            key: 'Cache-Control',
            value: 'no-store, no-cache, must-revalidate, max-age=0',
          },
        ],
      },
    ]
  },
  async rewrites() {
    // Enable API proxy when API_BASE_URL is set (Docker) or in development mode
    const apiUrl = process.env.API_BASE_URL || process.env.NEXT_DEV_API_PROXY

    if (apiUrl) {
      // Use API_BASE_URL (internal Docker network) for server-side proxy
      // This avoids CORS issues by proxying through Next.js
      console.log('[Next.js Rewrites] Proxying /api/* to:', apiUrl)
      return [
        {
          // Proxy API calls to backend
          source: '/api/:path*',
          destination: `${apiUrl}/api/:path*`,
        },
        {
          // Proxy Tidewave MCP calls to backend
          source: '/tidewave/:path*',
          destination: `${apiUrl}/tidewave/:path*`,
        }
      ];
    }

    return [];
  },
}

module.exports = nextConfig
