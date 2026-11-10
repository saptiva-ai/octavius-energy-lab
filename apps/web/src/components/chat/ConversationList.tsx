"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import toast from "react-hot-toast";
import { Menu, Transition } from "@headlessui/react";

import type { ChatSession, ChatSessionOptimistic } from "../../lib/types";
import { cn, formatRelativeTime, debounce } from "../../lib/utils";
import { useAuthStore } from "../../lib/auth-store";
import { useKeyboardNavigation } from "../../hooks/useKeyboardNavigation";
import { ModeToggle } from "../ui/ModeToggle";
import { PRODUCT_NAME } from "@/lib/brand";
// import { VirtualizedConversationList } from './VirtualizedConversationList'

// Threshold for enabling virtualization (performance optimization)
// Temporarily disabled due to react-window build issues in production
const VIRTUALIZATION_THRESHOLD = 999999;

interface ConversationListProps {
  sessions: ChatSession[];
  onNewChat: () => Promise<string | null>;
  onSelectChat: (chatId: string) => void;
  activeChatId?: string | null;
  isLoading?: boolean;
  onClose?: () => void;
  onCollapse?: () => void;
  isCollapsed?: boolean;
  className?: string;
  // New actions for UX-002
  onRenameChat?: (chatId: string, newTitle: string) => void;
  onPinChat?: (chatId: string) => void;
  onDeleteChat?: (chatId: string) => void;
  layoutVersion?: "legacy" | "grid";
  variant?: "desktop" | "mobile";
  // P0-UX-HIST-001: Optimistic UI
  isCreatingConversation?: boolean;
  // Anti-spam: Can create new chat
  canCreateNew?: boolean;
}

export function ConversationList({
  sessions,
  onNewChat,
  onSelectChat,
  activeChatId,
  isLoading = false,
  onClose,
  onCollapse,
  isCollapsed,
  className,
  onRenameChat,
  onPinChat,
  onDeleteChat,
  layoutVersion = "legacy",
  variant = "desktop",
  isCreatingConversation = false,
  canCreateNew = true,
}: ConversationListProps) {
  const router = useRouter();
  const [hoveredChatId, setHoveredChatId] = React.useState<string | null>(null);
  const [renamingChatId, setRenamingChatId] = React.useState<string | null>(
    null,
  );
  const [renameValue, setRenameValue] = React.useState("");
  const { user, logout } = useAuthStore();
  const renameInputRef = React.useRef<HTMLInputElement>(null);
  const isGridLayout = layoutVersion === "grid";
  const isDesktopVariant = variant === "desktop";
  const showList = !(isGridLayout && isDesktopVariant && isCollapsed);

  // Sort sessions first for keyboard navigation
  // P0-UX-HIST-001: Merge optimistic conversations with real sessions
  // Progressive Commitment: Filter empty conversations
  const sortedSessions = React.useMemo(() => {
    const seen = new Set<string>();
    const deduped = sessions.filter((session) => {
      if (seen.has(session.id)) {
        return false;
      }
      seen.add(session.id);
      return true;
    });

    const getSortTimestamp = (session: ChatSession | ChatSessionOptimistic) => {
      const fallback = session.created_at;
      const timestamp =
        session.last_message_at || session.first_message_at || fallback;
      return new Date(timestamp || fallback).getTime();
    };

    const pendingSessions = deduped
      .filter((session) => {
        const optimistic = session as ChatSessionOptimistic;
        return optimistic.pending || optimistic.state === "creating";
      })
      .sort((a, b) => getSortTimestamp(b) - getSortTimestamp(a));

    const pendingIds = new Set(pendingSessions.map((session) => session.id));

    const pinned = deduped
      .filter((session) => session.pinned && !pendingIds.has(session.id))
      .sort((a, b) => getSortTimestamp(b) - getSortTimestamp(a));

    const unpinned = deduped
      .filter((session) => !session.pinned && !pendingIds.has(session.id))
      .sort((a, b) => getSortTimestamp(b) - getSortTimestamp(a));

    return [...pendingSessions, ...pinned, ...unpinned];
  }, [sessions]);

  // Keyboard navigation hook
  const keyboardNav = useKeyboardNavigation({
    items: sortedSessions,
    onSelect: (session) => handleSelect(session),
    activeItemId: activeChatId,
    getItemId: (session) => session.id,
    isEnabled: !renamingChatId, // Disable when renaming
    onEscape: () => {
      if (renamingChatId) {
        setRenamingChatId(null);
        setRenameValue("");
      }
    },
  });

  // Keyboard shortcut for collapse - UX-002
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Cmd/Ctrl+B toggles sidebar collapse
      if ((e.metaKey || e.ctrlKey) && e.key === "b" && onCollapse) {
        e.preventDefault();
        onCollapse();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onCollapse]);

  // Auto-focus rename input
  React.useEffect(() => {
    if (renamingChatId && renameInputRef.current) {
      renameInputRef.current.focus();
      renameInputRef.current.select();
    }
  }, [renamingChatId]);

  const handleLogout = async () => {
    await logout();
  };

  const handleSelect = (session: ChatSession | ChatSessionOptimistic) => {
    // REMOVED: No bloquear navegación por estado lifecycle
    // La UI central decide qué mostrar basado en state + messages.length
    // El usuario SIEMPRE puede hacer switch entre conversaciones

    onSelectChat(session.id);
    router.push(`/chat/${session.id}`);
    onClose?.();
  };

  // P0-FE-BLOCK-BUTTON: Check if there's an existing empty draft or creating conversation
  const existingEmptyDraft = React.useMemo(() => {
    return sortedSessions.find(
      (s) =>
        (s.state === "draft" || s.state === "creating") &&
        s.message_count === 0,
    );
  }, [sortedSessions]);

  const handleCreate = React.useCallback(async () => {
    // PR4: Prevent double-click with isCreatingConversation state
    if (isCreatingConversation) {
      return;
    }

    // P0-FE-BLOCK-BUTTON: If there's an empty draft, do SILENT no-op
    // No toast, no spinner - just quietly focus the existing draft
    if (existingEmptyDraft) {
      // Silently redirect to the empty draft
      onSelectChat(existingEmptyDraft.id);
      router.push(`/chat/${existingEmptyDraft.id}`);
      onClose?.();
      return;
    }

    // Note: Removed "canCreateNew" check and toast - anti-spam logic now relies
    // on existingEmptyDraft detection above (silent redirect instead of blocking)

    try {
      const optimisticId = await onNewChat();

      if (optimisticId) {
        router.push(`/chat/${optimisticId}`);
      }

      onClose?.();
    } catch (error) {
      toast.error("No se pudo crear la conversación.");
    }
  }, [
    isCreatingConversation,
    existingEmptyDraft,
    onSelectChat,
    router,
    onClose,
    onNewChat,
  ]);

  // Hover actions handlers - UX-002
  const handleStartRename = (chatId: string, currentTitle: string) => {
    setRenamingChatId(chatId);
    setRenameValue(currentTitle || "Conversación sin título");
    setHoveredChatId(null);
  };

  // Debounced rename handler - waits 500ms after user stops typing
  const debouncedRename = React.useMemo(
    () =>
      debounce((chatId: string, newTitle: string) => {
        if (onRenameChat && newTitle.trim()) {
          onRenameChat(chatId, newTitle.trim());
        }
      }, 500),
    [onRenameChat],
  );

  const handleFinishRename = () => {
    if (renamingChatId && renameValue.trim() && onRenameChat) {
      onRenameChat(renamingChatId, renameValue.trim());
    }
    setRenamingChatId(null);
    setRenameValue("");
  };

  const handleCancelRename = () => {
    setRenamingChatId(null);
    setRenameValue("");
  };

  const handleRenameKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleFinishRename();
    } else if (e.key === "Escape") {
      e.preventDefault();
      handleCancelRename();
    }
  };

  const handlePin = (chatId: string) => {
    if (onPinChat) {
      onPinChat(chatId);
    }
    setHoveredChatId(null);
  };

  const handleDelete = (chatId: string) => {
    if (onDeleteChat) {
      onDeleteChat(chatId);
    }
    setHoveredChatId(null);
  };

  // sortedSessions is now defined at the top for keyboard navigation

  // Use virtualization for large lists (>50 items) for performance
  const shouldVirtualize = sortedSessions.length > VIRTUALIZATION_THRESHOLD;

  const listContent = isLoading ? (
    <div className="flex h-full items-center justify-center text-sm text-muted">
      Cargando conversaciones...
    </div>
  ) : sessions.length === 0 ? (
    // Empty state - no card, just subtle text
    <div className="flex h-full items-center justify-center px-6 text-center">
      <p className="text-sm text-muted/70">No hay conversaciones aún</p>
    </div>
  ) : false ? null : (
    // Virtualization temporarily disabled - always use regular list
    // TODO: Fix react-window build issues and re-enable virtualization
    // Regular list for smaller collections (<= 50 items)
    <ul
      className="space-y-1"
      ref={keyboardNav.listRef as React.RefObject<HTMLUListElement>}
      role={keyboardNav.listProps.role}
      aria-activedescendant={keyboardNav.listProps["aria-activedescendant"]}
      tabIndex={keyboardNav.listProps.tabIndex}
    >
      {sortedSessions.map((session, index) => {
        const isActive = activeChatId === session.id;
        const isHovered = hoveredChatId === session.id;
        const isRenaming = renamingChatId === session.id;
        const isPinned = session.pinned;
        const isFocused = keyboardNav.isFocused(session);
        // P0-UX-HIST-001: Check if this is an optimistic or new session
        const sessionOpt = session as ChatSessionOptimistic;
        const isOptimistic = sessionOpt.isOptimistic === true;
        const isNew = sessionOpt.isNew === true;

        return (
          <li key={session.id} {...keyboardNav.getItemProps(session, index)}>
            <div
              className={cn(
                "group relative flex w-full flex-col rounded-lg transition-all duration-150",
                // Saptiva Design: Active state with primary accent
                isActive
                  ? "border-l-4 border-primary bg-surface shadow-sm pl-3 pr-3 py-3"
                  : "border-l-4 border-transparent bg-transparent pl-3 pr-3 py-3",
                !isActive && "hover:bg-surface/50",
                isFocused &&
                  !isActive &&
                  "ring-1 ring-primary/40 bg-surface/50",
                // P0-UX-HIST-001: Highlight new sessions with animation
                isNew && "animate-highlight-fade",
              )}
              onMouseEnter={() => setHoveredChatId(session.id)}
              onMouseLeave={() => setHoveredChatId(null)}
            >
              {/* Main content area - clickable to select */}
              <button
                type="button"
                onClick={() => !isRenaming && handleSelect(session)}
                className={cn(
                  "flex w-full flex-col text-left transition-opacity",
                  sessionOpt.state === "creating" && "opacity-75",
                )}
                disabled={isRenaming}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    {/* Pin indicator - Classic office pushpin */}
                    {isPinned && (
                      <svg
                        className={cn(
                          "h-3 w-3 flex-shrink-0",
                          isActive ? "text-primary" : "text-primary/70",
                        )}
                        fill="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path d="M16,12V4H17V2H7V4H8V12L6,14V16H11.2V22H12.8V16H18V14L16,12Z" />
                      </svg>
                    )}

                    {isRenaming ? (
                      <input
                        ref={renameInputRef}
                        type="text"
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                        onKeyDown={handleRenameKeyDown}
                        onBlur={handleFinishRename}
                        className="bg-surface-2 text-sm font-semibold text-foreground rounded px-2 py-1 border border-border focus:border-primary focus:outline-none min-w-0 flex-1"
                        onClick={(e) => e.stopPropagation()}
                      />
                    ) : (
                      <>
                        <span
                          className={cn(
                            "text-sm truncate",
                            isActive
                              ? "font-medium text-foreground"
                              : "font-normal text-muted hover:text-foreground",
                          )}
                        >
                          {session.title || "Conversación sin título"}
                        </span>
                      </>
                    )}
                  </div>

                  {!isRenaming && (
                    <div className="flex items-center gap-1.5 flex-shrink-0 opacity-70">
                      {/* Removed NEW badge and timestamp for minimal design */}
                    </div>
                  )}
                </div>

                {/* Removed preview text for minimal design */}
              </button>

              {/* Hover actions - UX-002 */}
              {isHovered && !isRenaming && (
                <div className="absolute right-2 top-3 flex items-center gap-1 bg-surface/90 backdrop-blur-sm rounded-lg border border-border p-1">
                  {/* Rename button */}
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleStartRename(session.id, session.title || "");
                    }}
                    className="h-7 w-7 flex items-center justify-center rounded text-text-muted hover:text-text hover:bg-surface-2 transition-colors"
                    title="Renombrar"
                  >
                    <svg
                      className="h-3.5 w-3.5"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                      />
                    </svg>
                  </button>

                  {/* Pin button - Classic office pushpin */}
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handlePin(session.id);
                    }}
                    className={cn(
                      "h-7 w-7 flex items-center justify-center rounded transition-colors",
                      isPinned
                        ? "text-primary hover:text-primary/80 hover:bg-surface-2"
                        : "text-muted hover:text-foreground hover:bg-surface-2",
                    )}
                    title={isPinned ? "Desfijar" : "Fijar"}
                  >
                    <svg
                      className="h-3.5 w-3.5"
                      fill="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path d="M16,12V4H17V2H7V4H8V12L6,14V16H11.2V22H12.8V16H18V14L16,12Z" />
                    </svg>
                  </button>

                  {/* Delete button */}
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(session.id);
                    }}
                    className="h-7 w-7 flex items-center justify-center rounded text-text-muted hover:text-danger hover:bg-danger/10 transition-colors"
                    title="Eliminar"
                  >
                    <svg
                      className="h-3.5 w-3.5"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                      />
                    </svg>
                  </button>
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
  if (!isGridLayout) {
    return (
      <div className={cn("flex h-full w-full flex-col bg-surface", className)}>
        <div className="flex items-center justify-between gap-2 px-3 py-3">
          {/* Layout: [<] [Historial OctaviOS] [+] */}

          {/* Botón colapsar - siempre visible en desktop */}
          {onCollapse && (
            <button
              type="button"
              onClick={onCollapse}
              className="hidden h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-muted transition hover:bg-surface hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 lg:flex"
              aria-label={
                isCollapsed ? "Expandir historial" : "Colapsar historial"
              }
            >
              {isCollapsed ? (
                <svg
                  className="h-4 w-4"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                >
                  <path
                    d="M10 6 16 12 10 18"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              ) : (
                <svg
                  className="h-4 w-4"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                >
                  <path
                    d="M14 6 8 12 14 18"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              )}
            </button>
          )}

          {/* Texto central - solo cuando expandido */}
          {!isCollapsed && (
            <div className="flex-1 min-w-0 text-center">
              <p className="text-xs uppercase tracking-[0.2em] text-text-muted">
                Historial
              </p>
              <h2 className="text-lg font-semibold text-foreground">
                {PRODUCT_NAME}
              </h2>
            </div>
          )}

          {/* Botones derecha - solo cuando expandido */}
          {!isCollapsed && (
            <div className="flex shrink-0 items-center gap-2">
              {/* Botón cerrar - solo mobile */}
              {onClose && (
                <button
                  type="button"
                  onClick={onClose}
                  className="flex h-8 w-8 items-center justify-center rounded-lg bg-surface-2 text-muted transition hover:bg-surface hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 lg:hidden"
                  aria-label="Cerrar historial"
                >
                  <svg
                    className="h-4 w-4"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                  >
                    <path
                      d="m16 8-8 8"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                    />
                    <path
                      d="m8 8 8 8"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                    />
                  </svg>
                </button>
              )}

              {/* Botón crear conversación */}
              <button
                type="button"
                onClick={handleCreate}
                disabled={isCreatingConversation || !canCreateNew}
                aria-disabled={isCreatingConversation || !canCreateNew}
                className={cn(
                  "flex h-8 w-8 items-center justify-center rounded-lg transition",
                  isCreatingConversation || !canCreateNew
                    ? "bg-surface-2/60 text-muted cursor-not-allowed"
                    : existingEmptyDraft
                      ? "bg-primary/10 text-primary hover:bg-primary/20"
                      : "bg-surface-2 text-foreground hover:bg-surface",
                )}
                aria-label={
                  isCreatingConversation
                    ? "Creando conversación..."
                    : existingEmptyDraft
                      ? "Ir a conversación vacía existente"
                      : "Nueva conversación"
                }
                title={
                  existingEmptyDraft
                    ? "Ya tienes una conversación vacía"
                    : "Nueva conversación"
                }
              >
                {existingEmptyDraft ? (
                  <svg
                    className="h-4 w-4"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                  >
                    <path
                      d="M15 18l-6-6 6-6"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                ) : (
                  <svg
                    className="h-4 w-4"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                  >
                    <path
                      d="M12 5v14"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                    />
                    <path
                      d="M5 12h14"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                    />
                  </svg>
                )}
              </button>
            </div>
          )}
        </div>

        {!isCollapsed ? (
          <div className="flex-1 overflow-y-auto px-3 pb-6">{listContent}</div>
        ) : (
          /* Rail persistente cuando está colapsado - Legacy Layout */
          <div className="flex flex-1 flex-col items-start justify-between py-4 px-3">
            <span className="sr-only">Historial colapsado</span>

            {/* Botón crear conversación (abajo) - mismo tamaño que header */}
            <button
              type="button"
              onClick={handleCreate}
              disabled={isCreatingConversation || !canCreateNew}
              className={cn(
                "group flex h-8 w-8 items-center justify-center rounded-lg transition focus-visible:outline-none focus-visible:ring-2 relative",
                isCreatingConversation || !canCreateNew
                  ? "bg-surface-2/60 text-text/60 cursor-not-allowed"
                  : existingEmptyDraft
                    ? "bg-primary/10 text-primary hover:bg-primary/20 focus-visible:ring-primary"
                    : "bg-surface-2 text-text hover:bg-surface focus-visible:ring-primary",
              )}
              aria-label={
                isCreatingConversation
                  ? "Creando conversación..."
                  : existingEmptyDraft
                    ? "Ir a conversación vacía existente"
                    : "Nueva conversación"
              }
              title={
                isCreatingConversation
                  ? "Creando conversación..."
                  : existingEmptyDraft
                    ? "Ya tienes una conversación vacía"
                    : "Nueva conversación"
              }
            >
              {existingEmptyDraft ? (
                <svg
                  className="h-4 w-4"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                >
                  <path
                    d="M15 18l-6-6 6-6"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              ) : (
                <svg
                  className="h-4 w-4"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                >
                  <path d="M12 5v14" strokeWidth="1.8" strokeLinecap="round" />
                  <path d="M5 12h14" strokeWidth="1.8" strokeLinecap="round" />
                </svg>
              )}
            </button>
          </div>
        )}

        {/* Account bar fixed at bottom - ACC-01 */}
        {user && !isCollapsed && (
          <div className="border-t border-border p-4">
            <Menu as="div" className="relative">
              {({ open }) => (
                <>
                  <Menu.Button className="flex w-full items-center gap-3 rounded-xl bg-surface-2 p-3 transition-colors hover:bg-surface-2/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60">
                    {/* Avatar con iniciales */}
                    <div className="h-8 w-8 rounded-full bg-primary/20 flex items-center justify-center">
                      <span className="text-sm font-bold text-primary">
                        {user.username?.[0]?.toUpperCase() ||
                          user.email?.[0]?.toUpperCase() ||
                          "U"}
                      </span>
                    </div>

                    {/* User info */}
                    <div className="flex-1 min-w-0 text-left">
                      <p className="text-sm font-bold text-text truncate">
                        {user.username}
                      </p>
                      <p className="text-xs text-text-muted truncate">
                        {user.email}
                      </p>
                    </div>

                    {/* Menu arrow */}
                    <svg
                      className={cn(
                        "h-4 w-4 text-text-muted transition-transform",
                        open && "rotate-180",
                      )}
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="1.8"
                        d="M19 9l-7 7-7-7"
                      />
                    </svg>
                  </Menu.Button>

                  <Transition
                    as={React.Fragment}
                    enter="transition ease-out duration-150"
                    enterFrom="transform opacity-0 scale-95"
                    enterTo="transform opacity-100 scale-100"
                    leave="transition ease-in duration-100"
                    leaveFrom="transform opacity-100 scale-100"
                    leaveTo="transform opacity-0 scale-95"
                  >
                    <Menu.Items className="absolute bottom-full left-0 right-0 mb-2 rounded-xl border border-border bg-surface shadow-card overflow-hidden origin-bottom focus:outline-none">
                      <Menu.Item>
                        {({ active }) => (
                          <button
                            type="button"
                            onClick={handleLogout}
                            className={cn(
                              "w-full px-3 py-2 text-left text-sm transition-colors",
                              active
                                ? "bg-danger/10 text-danger"
                                : "text-danger",
                            )}
                          >
                            Cerrar sesión
                          </button>
                        )}
                      </Menu.Item>
                      {/* Placeholder for future Settings option */}
                      {/* <Menu.Item>
                      {({ active }) => (
                        <button
                          type="button"
                          onClick={() => {}}
                          className={cn(
                            'w-full px-3 py-2 text-left text-sm transition-colors',
                            active ? 'bg-surface-2 text-text' : 'text-text-muted'
                          )}
                        >
                          Configuración
                        </button>
                      )}
                    </Menu.Item> */}
                    </Menu.Items>
                  </Transition>
                </>
              )}
            </Menu>
          </div>
        )}
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex h-full flex-col bg-surface text-foreground",
        className,
      )}
    >
      <div
        className={cn(
          "sticky top-0 z-20 flex items-center gap-2 border-b border-border/60 bg-surface/95 backdrop-blur",
          isDesktopVariant ? "h-14 px-2" : "px-4 py-4",
        )}
      >
        {isDesktopVariant ? (
          <>
            {/* Layout Grid: [<] [Historial OctaviOS] [+] */}

            {/* Botón colapsar - siempre visible */}
            {onCollapse && (
              <button
                type="button"
                onClick={onCollapse}
                className="relative z-20 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-text transition hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                aria-label={
                  isCollapsed ? "Expandir historial" : "Colapsar historial"
                }
              >
                {isCollapsed ? (
                  <svg
                    className="h-4 w-4"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                  >
                    <path
                      d="M10 6 16 12 10 18"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                ) : (
                  <svg
                    className="h-4 w-4"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                  >
                    <path
                      d="M14 6 8 12 14 18"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                )}
              </button>
            )}

            {/* Texto central - solo cuando expandido */}
            {!isCollapsed && (
              <div className="flex-1 min-w-0 text-center">
                <p className="text-[11px] uppercase tracking-[0.2em] text-text-muted">
                  Historial
                </p>
                <h2 className="text-sm font-semibold text-foreground">
                  {PRODUCT_NAME}
                </h2>
              </div>
            )}

            {/* Botón crear - solo cuando expandido */}
            {!isCollapsed && (
              <button
                type="button"
                onClick={handleCreate}
                disabled={isCreatingConversation || !canCreateNew}
                className={cn(
                  "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition focus-visible:outline-none focus-visible:ring-2",
                  isCreatingConversation || !canCreateNew
                    ? "bg-surface-2/60 text-text/60 cursor-not-allowed"
                    : existingEmptyDraft
                      ? "bg-primary/10 text-primary hover:bg-primary/20 focus-visible:ring-primary"
                      : "bg-surface-2 text-text hover:bg-surface focus-visible:ring-primary",
                )}
                aria-label={
                  isCreatingConversation
                    ? "Creando conversación..."
                    : existingEmptyDraft
                      ? "Ir a conversación vacía existente"
                      : "Nueva conversación"
                }
                title={
                  isCreatingConversation
                    ? "Creando conversación..."
                    : existingEmptyDraft
                      ? "Ya tienes una conversación vacía"
                      : "Nueva conversación"
                }
              >
                {existingEmptyDraft ? (
                  <svg
                    className="h-4 w-4"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                  >
                    <path
                      d="M15 18l-6-6 6-6"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                ) : (
                  <svg
                    className="h-4 w-4"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                  >
                    <path
                      d="M12 5v14"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                    />
                    <path
                      d="M5 12h14"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                    />
                  </svg>
                )}
              </button>
            )}
          </>
        ) : (
          <div className="flex w-full items-center justify-between gap-2">
            <div className="min-w-0">
              <p className="text-xs uppercase tracking-[0.2em] text-text-muted">
                Historial
              </p>
              <h2 className="text-lg font-semibold text-foreground">
                {PRODUCT_NAME}
              </h2>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {onClose && (
                <button
                  type="button"
                  onClick={onClose}
                  className="flex h-10 w-10 items-center justify-center rounded-full bg-surface-2 text-muted transition hover:bg-surface hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
                  aria-label="Cerrar historial"
                >
                  <svg
                    className="h-5 w-5"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                  >
                    <path
                      d="m16 8-8 8"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                    />
                    <path
                      d="m8 8 8 8"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                    />
                  </svg>
                </button>
              )}

              <button
                type="button"
                onClick={handleCreate}
                disabled={isCreatingConversation || !canCreateNew}
                className={cn(
                  "flex h-10 w-10 items-center justify-center rounded-full transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
                  isCreatingConversation || !canCreateNew
                    ? "bg-primary/10 text-primary/60 cursor-not-allowed"
                    : "bg-primary/20 text-primary hover:scale-[1.02] hover:bg-primary/30",
                )}
                aria-label={
                  isCreatingConversation
                    ? "Creando conversación..."
                    : "Nueva conversación"
                }
                title={undefined}
              >
                <svg
                  className="h-5 w-5"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                >
                  <path d="M12 5v14" strokeWidth="1.8" strokeLinecap="round" />
                  <path d="M5 12h14" strokeWidth="1.8" strokeLinecap="round" />
                </svg>
              </button>
            </div>
          </div>
        )}
      </div>

      {showList ? (
        <div className="flex-1 overflow-y-auto px-3 pb-6">{listContent}</div>
      ) : (
        /* Rail persistente cuando está colapsado - Grid Layout */
        <div className="flex flex-1 flex-col items-start justify-between py-4 px-2">
          <span className="sr-only">Historial colapsado</span>

          {/* Botón crear conversación (abajo) - mismo tamaño que header */}
          <button
            type="button"
            onClick={handleCreate}
            disabled={isCreatingConversation || !canCreateNew}
            className={cn(
              "group flex h-8 w-8 items-center justify-center rounded-lg transition focus-visible:outline-none focus-visible:ring-2 relative",
              isCreatingConversation || !canCreateNew
                ? "bg-surface-2/60 text-text/60 cursor-not-allowed"
                : existingEmptyDraft
                  ? "bg-primary/10 text-primary hover:bg-primary/20 focus-visible:ring-primary"
                  : "bg-surface-2 text-text hover:bg-surface focus-visible:ring-primary",
            )}
            aria-label={
              isCreatingConversation
                ? "Creando conversación..."
                : existingEmptyDraft
                  ? "Ir a conversación vacía existente"
                  : "Nueva conversación"
            }
            title={
              isCreatingConversation
                ? "Creando conversación..."
                : existingEmptyDraft
                  ? "Ya tienes una conversación vacía"
                  : "Nueva conversación"
            }
          >
            {existingEmptyDraft ? (
              <svg
                className="h-4 w-4"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
              >
                <path
                  d="M15 18l-6-6 6-6"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            ) : (
              <svg
                className="h-4 w-4"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
              >
                <path d="M12 5v14" strokeWidth="1.8" strokeLinecap="round" />
                <path d="M5 12h14" strokeWidth="1.8" strokeLinecap="round" />
              </svg>
            )}
          </button>
        </div>
      )}

      {user && showList && (
        <div className="border-t border-border p-4">
          <Menu as="div" className="relative">
            {({ open }) => (
              <>
                <Menu.Button className="flex w-full items-center gap-3 rounded-xl bg-surface-2 p-3 transition-colors hover:bg-surface-2/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60">
                  {/* Avatar */}
                  <div className="h-8 w-8 rounded-full bg-primary/20 flex items-center justify-center">
                    <span className="text-sm font-bold text-primary">
                      {user.username?.[0]?.toUpperCase() ||
                        user.email?.[0]?.toUpperCase() ||
                        "U"}
                    </span>
                  </div>

                  {/* User info */}
                  <div className="flex-1 min-w-0 text-left">
                    <p className="text-sm font-bold text-text truncate">
                      {user.username}
                    </p>
                    <p className="text-xs text-text-muted truncate">
                      {user.email}
                    </p>
                  </div>

                  {/* Menu arrow */}
                  <svg
                    className={cn(
                      "h-4 w-4 text-text-muted transition-transform",
                      open && "rotate-180",
                    )}
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="1.8"
                      d="M19 9l-7 7-7-7"
                    />
                  </svg>
                </Menu.Button>

                <Transition
                  as={React.Fragment}
                  enter="transition ease-out duration-150"
                  enterFrom="transform opacity-0 scale-95"
                  enterTo="transform opacity-100 scale-100"
                  leave="transition ease-in duration-100"
                  leaveFrom="transform opacity-100 scale-100"
                  leaveTo="transform opacity-0 scale-95"
                >
                  <Menu.Items className="absolute bottom-full left-0 right-0 mb-2 rounded-xl border border-border bg-surface shadow-card overflow-hidden origin-bottom focus:outline-none">
                    <Menu.Item>
                      {({ active }) => (
                        <button
                          type="button"
                          onClick={handleLogout}
                          className={cn(
                            "w-full px-3 py-2 text-left text-sm transition-colors",
                            active ? "bg-danger/10 text-danger" : "text-danger",
                          )}
                        >
                          Cerrar sesión
                        </button>
                      )}
                    </Menu.Item>
                    {/* Placeholder for future Settings option */}
                    {/* <Menu.Item>
                      {({ active }) => (
                        <button
                          type="button"
                          onClick={() => {}}
                          className={cn(
                            'w-full px-3 py-2 text-left text-sm transition-colors',
                            active ? 'bg-surface-2 text-text' : 'text-text-muted'
                          )}
                        >
                          Configuración
                        </button>
                      )}
                    </Menu.Item> */}
                  </Menu.Items>
                </Transition>
              </>
            )}
          </Menu>
        </div>
      )}
    </div>
  );
}
