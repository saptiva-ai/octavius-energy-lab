/**
 * Loading skeleton for chat route
 *
 * This component is shown by Next.js App Router during:
 * 1. Initial page load
 * 2. Navigation between conversations
 * 3. Optimistic conversation creation (temp-* IDs)
 *
 * P0-UX-HIST-001: Prevents "Conversación no encontrada" flash
 * by providing a stable loading state during route transitions.
 */
export default function Loading() {
  return (
    <div className="flex h-screen items-center justify-center bg-saptiva-dark">
      <div className="flex flex-col items-center gap-4">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-saptiva-blue" />
        <p className="text-saptiva-light/70 text-sm">
          Cargando conversación...
        </p>
      </div>
    </div>
  );
}
