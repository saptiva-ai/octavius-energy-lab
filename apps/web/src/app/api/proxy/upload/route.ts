import { NextRequest, NextResponse } from "next/server";

/**
 * API Route Proxy for File Uploads
 *
 * This proxy forwards file uploads from the browser to the backend,
 * bypassing Cloudflare's challenge system. The browser makes a request
 * to our Next.js server (same-origin), and we forward it server-side
 * to the backend.
 *
 * Flow:
 * Browser → /api/proxy/upload (Next.js) → backend /api/files/upload
 *
 * This works because:
 * 1. Browser → Next.js is same-origin (no CORS, no Cloudflare challenge)
 * 2. Next.js → Backend is server-side (bypasses Cloudflare edge)
 */

const API_BASE_URL =
  process.env.API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://backend:8000"; // Fixed: correct service name from docker-compose.yml

export async function POST(request: NextRequest) {
  try {
    // Extract authorization header
    const authHeader = request.headers.get("authorization");
    if (!authHeader) {
      return NextResponse.json(
        { error: "Authorization header required" },
        { status: 401 },
      );
    }

    // Get the FormData from the incoming request
    const formData = await request.formData();

    // Forward the entire FormData to the backend
    const backendUrl = `${API_BASE_URL}/api/files/upload`;

    // eslint-disable-next-line no-console
    console.log("[Upload Proxy] Forwarding upload to:", backendUrl);
    // eslint-disable-next-line no-console
    console.log(
      "[Upload Proxy] Files in FormData:",
      Array.from(formData.keys()).filter(
        (key) => formData.get(key) instanceof File,
      ),
    );

    const response = await fetch(backendUrl, {
      method: "POST",
      headers: {
        // Forward the authorization header
        Authorization: authHeader,
        // Don't set Content-Type - fetch will set it correctly for FormData
        // including the boundary parameter
      },
      body: formData,
      // Disable caching
      cache: "no-store",
    });

    // Get the response data
    const responseData = await response.json();

    // eslint-disable-next-line no-console
    console.log("[Upload Proxy] Backend response status:", response.status);

    // Return the backend response to the client
    return NextResponse.json(responseData, {
      status: response.status,
      headers: {
        "Cache-Control": "no-store, no-cache, must-revalidate",
        Pragma: "no-cache",
        Expires: "0",
      },
    });
  } catch (error) {
    console.error("[Upload Proxy] Error forwarding upload:", error);

    return NextResponse.json(
      {
        error: "Upload proxy failed",
        details: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 500 },
    );
  }
}
