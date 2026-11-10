/**
 * Forgot Password Proxy Route
 *
 * Proxy endpoint for password reset requests that forwards to the backend.
 *
 * Why needed:
 * - Frontend needs to call backend forgot-password endpoint
 * - This proxy handles CORS and forwarding
 *
 * Backend endpoint: POST /api/auth/forgot-password
 */

import { NextRequest, NextResponse } from "next/server";

// Use backend service name for Docker inter-container communication
// In Docker: http://backend:8000
// For local development outside Docker: http://localhost:8000
const BACKEND_URL = process.env.BACKEND_API_URL || "http://backend:8000";

export async function POST(request: NextRequest) {
  try {
    // Parse request body
    const body = await request.json();

    // Forward request to backend
    const backendUrl = `${BACKEND_URL}/api/auth/forgot-password`;
    const response = await fetch(backendUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    // Avoid JSON parse failures when upstream returns HTML/error pages
    const contentType = response.headers.get("content-type") || "";
    const data = contentType.includes("application/json")
      ? await response.json()
      : {
          detail:
            (await response.text()) || "Error en el servicio de recuperación",
        };

    // Return response with same status code
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error("Forgot password proxy error:", error);
    return NextResponse.json(
      {
        detail: "Error al procesar la solicitud de recuperación de contraseña",
      },
      { status: 500 },
    );
  }
}
