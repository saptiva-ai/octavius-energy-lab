import { NextRequest, NextResponse } from "next/server";

/**
 * Proxy route for downloading audit reports with authentication
 *
 * This route proxies requests to the backend API's audit report download endpoint,
 * forwarding the user's authentication cookie to ensure proper authorization.
 *
 * @param request - The incoming request
 * @param params - Route parameters containing reportId
 * @returns The proxied response with the PDF file
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ reportId: string }> },
) {
  const { reportId } = await params;

  // Get the API base URL
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://api:8001";
  const backendUrl = `${apiBaseUrl}/api/reports/audit/${reportId}/download`;

  try {
    // Forward the authorization cookie/header to the backend
    const authHeader = request.headers.get("authorization");
    const cookie = request.headers.get("cookie");

    const headers: HeadersInit = {
      "Content-Type": "application/json",
    };

    // Add authorization if present (Bearer token or cookie)
    if (authHeader) {
      headers["Authorization"] = authHeader;
    } else if (cookie) {
      headers["Cookie"] = cookie;
    }

    // Fetch from backend with authentication
    const response = await fetch(backendUrl, {
      method: "GET",
      headers,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({
        message: "Error al descargar el reporte",
      }));

      return NextResponse.json(
        {
          error: error.message || "Error al descargar el reporte de auditoría",
        },
        { status: response.status },
      );
    }

    // Get the PDF blob
    const blob = await response.blob();

    // Return the PDF with appropriate headers
    return new NextResponse(blob, {
      headers: {
        "Content-Type": "application/pdf",
        "Content-Disposition": `attachment; filename="reporte-auditoria-${reportId}.pdf"`,
        "Cache-Control": "private, no-cache, no-store, must-revalidate",
      },
    });
  } catch (error) {
    console.error("[Audit Report Download] Error:", error);
    return NextResponse.json(
      { error: "Error al conectar con el servidor de auditoría" },
      { status: 500 },
    );
  }
}
