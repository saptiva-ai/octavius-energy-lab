export const getEffectiveCanvasChatId = (
  routeChatId: string | null,
  storeChatId: string | null,
): string | null => routeChatId ?? storeChatId ?? null;

export const isTempToRealChatReconciliation = (
  previousChatId: string | null,
  nextChatId: string | null,
): boolean =>
  Boolean(
    previousChatId &&
    previousChatId.startsWith("temp-") &&
    nextChatId &&
    !nextChatId.startsWith("temp-"),
  );

export const shouldResetCanvasForChatTransition = (
  previousChatId: string | null,
  nextChatId: string | null,
): boolean => {
  const hasChanged = previousChatId !== nextChatId;
  if (!hasChanged || previousChatId === null) {
    return false;
  }

  return !isTempToRealChatReconciliation(previousChatId, nextChatId);
};

export const shouldResetCanvasForNoActiveChat = (
  previousChatId: string | null,
  nextChatId: string | null,
): boolean => previousChatId !== null && nextChatId === null;

/** Restaurar el canvas persistido al ENTRAR a una conversación real: primera
 * carga o cambio de conversación. Ni en ids temporales (aún no hay nada
 * guardado) ni en la reconciliación temp→real (el canvas vivo del turno en
 * curso ganaría contra un GET stale del backend). */
export const shouldRestoreCanvasForChat = (
  previousChatId: string | null,
  nextChatId: string | null,
): boolean =>
  Boolean(
    nextChatId &&
    !nextChatId.startsWith("temp-") &&
    previousChatId !== nextChatId &&
    !isTempToRealChatReconciliation(previousChatId, nextChatId),
  );
