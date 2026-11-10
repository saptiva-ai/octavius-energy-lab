/**
 * Thumbnail Proxy Route
 *
 * Proxy endpoint for document thumbnails that adds authentication.
 *
 * Why needed:
 * - <img> tags don't send auth headers automatically
 * - Backend requires authentication for thumbnails
 * - This proxy reads token from Authorization header and forwards it
 *
 * Usage:
 * Use ThumbnailImage component which sends Authorization header
 */

import { NextRequest, NextResponse } from "next/server";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8001";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ fileId: string }> },
) {
  try {
    const params = await context.params;
    const { fileId } = params;

    // Get auth token from Authorization header
    const authHeader = request.headers.get("authorization");

    if (!authHeader) {
      return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
    }

    // Extract token
    const accessToken = authHeader.replace("Bearer ", "");

    if (!accessToken) {
      return NextResponse.json(
        { error: "No access token found" },
        { status: 401 },
      );
    }

    // Fetch thumbnail from backend with auth token
    const backendUrl = `${API_BASE_URL}/api/documents/${fileId}/thumbnail`;
    const response = await fetch(backendUrl, {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
      // Don't cache on server side - let browser handle cache via headers
      cache: "no-store",
    });

    if (!response.ok) {
      console.error(
        `Thumbnail fetch failed: ${response.status} ${response.statusText}`,
      );
      return NextResponse.json(
        { error: "Failed to fetch thumbnail" },
        { status: response.status },
      );
    }

    // Get image data
    const imageBuffer = await response.arrayBuffer();
    const contentType = response.headers.get("content-type") || "image/jpeg";
    const cacheControl =
      response.headers.get("cache-control") || "public, max-age=3600";

    // Return image with cache headers
    return new NextResponse(imageBuffer, {
      status: 200,
      headers: {
        "Content-Type": contentType,
        "Cache-Control": cacheControl,
      },
    });
  } catch (error) {
    console.error("Thumbnail proxy error:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}
