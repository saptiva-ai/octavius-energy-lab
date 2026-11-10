import { Suspense } from "react";
import { notFound } from "next/navigation";

import { assertProdNoMock } from "../../../lib/runtime";
import { ChatView } from "../_components/ChatView";

interface ChatRouteProps {
  params: Promise<{
    chatId: string;
  }>;
}

assertProdNoMock();

// Validate chatId format (UUID or temporary optimistic ID)
function isValidChatId(chatId: string): boolean {
  if (!chatId || chatId === "new" || chatId.length < 10) return false;
  // P0-UX-HIST-001: Accept temporary IDs during optimistic conversation creation
  // These IDs are created client-side and replaced with real UUIDs after backend responds
  if (chatId.startsWith("temp-")) return true;
  // Standard UUID format check
  const uuidRegex =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  return uuidRegex.test(chatId);
}

export default async function ChatRoute({ params }: ChatRouteProps) {
  const { chatId } = await params;

  // Validate chat ID format
  if (!isValidChatId(chatId)) {
    notFound();
  }

  return (
    <Suspense
      fallback={
        <div className="flex h-screen items-center justify-center">
          <p className="text-saptiva-slate">Cargando conversación...</p>
        </div>
      }
    >
      <ChatView initialChatId={chatId} />
    </Suspense>
  );
}
