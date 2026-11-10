"use client";

import * as React from "react";
import Image from "next/image";
import { useTheme } from "next-themes";

import { cn } from "../../lib/utils";
import { ModelSelector, type ChatModel } from "./ModelSelector";
import { featureFlags } from "../../lib/feature-flags";
import { ModeToggle } from "../ui/ModeToggle";
import { HelpOnboardingMenu } from "./HelpOnboardingMenu";

interface ChatShellProps {
  sidebar: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  models: ChatModel[];
  selectedModel?: string;
  onModelChange?: (model: string) => void;
}

export function ChatShell(props: ChatShellProps) {
  const layoutGridEnabled = featureFlags.webSearch;

  if (!layoutGridEnabled) {
    return <LegacyChatShell {...props} />;
  }

  return <GridChatShell {...props} />;
}

function GridChatShell({
  sidebar,
  children,
  footer,
  models,
  selectedModel,
  onModelChange,
}: ChatShellProps) {
  const { resolvedTheme } = useTheme();
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = React.useState(false);
  const [isDesktopSidebarCollapsed, setIsDesktopSidebarCollapsed] =
    React.useState(false);
  const [isDesktop, setIsDesktop] = React.useState(false);

  const sidebarWidth = isDesktopSidebarCollapsed ? 64 : 280;
  const safeLeft = !isDesktop && !isMobileSidebarOpen ? "48px" : "0px";

  // Theme-aware Saptiva logo
  const logoSrc =
    resolvedTheme === "dark"
      ? "/SaptivaAIlogo_blackbg.PNG" // White text logo for dark background
      : "/SaptivaAIlogo_whitebg.PNG"; // Dark text logo for light background

  // Update body data attribute for CSS variable switching
  React.useEffect(() => {
    if (typeof document !== "undefined") {
      document.body.setAttribute(
        "data-sidebar",
        isDesktopSidebarCollapsed ? "collapsed" : "expanded",
      );
    }
  }, [isDesktopSidebarCollapsed]);

  React.useEffect(() => {
    const mediaQuery = window.matchMedia("(min-width: 1024px)");

    const update = () => {
      setIsDesktop(mediaQuery.matches);
      if (mediaQuery.matches) {
        setIsMobileSidebarOpen(false);
      }
    };

    update();

    if (typeof mediaQuery.addEventListener === "function") {
      mediaQuery.addEventListener("change", update);
      return () => mediaQuery.removeEventListener("change", update);
    }

    mediaQuery.addListener(update);
    return () => mediaQuery.removeListener(update);
  }, []);

  const handleCloseSidebar = React.useCallback(() => {
    setIsMobileSidebarOpen(false);
  }, []);

  const handleToggleDesktopSidebar = React.useCallback(() => {
    setIsDesktopSidebarCollapsed((collapsed) => !collapsed);
  }, []);

  const handleRequestSidebar = React.useCallback(() => {
    if (isDesktop) {
      setIsDesktopSidebarCollapsed(false);
      return;
    }
    setIsMobileSidebarOpen(true);
  }, [isDesktop]);

  React.useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "b") {
        event.preventDefault();
        if (isDesktop) {
          handleToggleDesktopSidebar();
        } else {
          setIsMobileSidebarOpen((open) => !open);
        }
      }

      if (event.key === "Escape") {
        setIsMobileSidebarOpen(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleToggleDesktopSidebar, isDesktop]);

  const cloneSidebar = React.useCallback(
    (extraProps: Record<string, unknown>) => {
      if (!React.isValidElement(sidebar)) return sidebar;
      return React.cloneElement(sidebar as React.ReactElement, extraProps);
    },
    [sidebar],
  );

  const desktopSidebar = React.useMemo(
    () =>
      cloneSidebar({
        onCollapse: handleToggleDesktopSidebar,
        isCollapsed: isDesktopSidebarCollapsed,
        variant: "desktop",
        layoutVersion: "grid",
      }),
    [cloneSidebar, handleToggleDesktopSidebar, isDesktopSidebarCollapsed],
  );

  const mobileSidebar = React.useMemo(
    () =>
      cloneSidebar({
        onClose: handleCloseSidebar,
        variant: "mobile",
        layoutVersion: "grid",
      }),
    [cloneSidebar, handleCloseSidebar],
  );

  const containerStyle = React.useMemo<React.CSSProperties>(() => {
    // CSS custom property: cast del literal completo (React.CSSProperties no
    // modela variables CSS), sin `any`.
    const style = { "--safe-left": safeLeft } as React.CSSProperties;

    if (isDesktop) {
      style.display = "grid";
      style.gridTemplateColumns = `${sidebarWidth}px 1fr`;
      style.gridTemplateRows = "56px 1fr";
      style.gridTemplateAreas = '"sidebar header" "sidebar content"';
    } else {
      style.display = "flex";
      style.flexDirection = "column";
    }

    return style;
  }, [isDesktop, sidebarWidth, safeLeft]);

  return (
    <div
      className="relative h-[100dvh] w-full overflow-hidden bg-background text-foreground"
      style={containerStyle}
    >
      {isDesktop ? (
        <>
          <aside
            style={{ gridArea: "sidebar", width: sidebarWidth }}
            className={cn(
              "relative z-[5] flex h-full flex-col overflow-hidden border-r border-border bg-sidebar transition-[width] duration-200",
            )}
          >
            <div className="flex-1 overflow-hidden">{desktopSidebar}</div>
          </aside>

          <header
            style={{
              gridArea: "header",
              paddingLeft: "calc(var(--safe-left, 0px) + 15px)",
            }}
            className="z-30 flex items-center justify-between gap-3 border-b border-border/40 bg-surface/95 px-4 backdrop-blur"
          >
            {featureFlags.modelSelector && selectedModel && onModelChange ? (
              <ModelSelector
                models={models}
                selectedModel={selectedModel}
                onModelChange={onModelChange}
                className="max-w-xs"
              />
            ) : null}
            <div className="flex items-center gap-3">
              <ModeToggle />
              <HelpOnboardingMenu ubicacion="encabezado" />
              <Image
                src={logoSrc}
                alt="Saptiva AI"
                width={120}
                height={32}
                className="h-8 w-auto"
                priority
              />
            </div>
          </header>

          <main
            style={{ gridArea: "content" }}
            className="flex min-h-0 flex-1 flex-col overflow-hidden"
          >
            <div className="flex-1 overflow-hidden">{children}</div>
            {footer ? (
              <div className="shrink-0 border-t border-border/40 bg-surface">
                {footer}
              </div>
            ) : null}
          </main>
        </>
      ) : (
        <LegacyMobileLayout
          mobileSidebar={mobileSidebar}
          isMobileSidebarOpen={isMobileSidebarOpen}
          onRequestSidebar={handleRequestSidebar}
          onCloseSidebar={handleCloseSidebar}
          models={models}
          selectedModel={selectedModel}
          onModelChange={onModelChange}
          footer={footer}
        >
          {children}
        </LegacyMobileLayout>
      )}
    </div>
  );
}

interface LegacyMobileLayoutProps {
  children: React.ReactNode;
  mobileSidebar: React.ReactNode;
  isMobileSidebarOpen: boolean;
  onRequestSidebar: () => void;
  onCloseSidebar: () => void;
  models: ChatModel[];
  selectedModel?: string;
  onModelChange?: (model: string) => void;
  footer?: React.ReactNode;
}

function LegacyMobileLayout({
  children,
  mobileSidebar,
  isMobileSidebarOpen,
  onRequestSidebar,
  onCloseSidebar,
  models,
  selectedModel,
  onModelChange,
  footer,
}: LegacyMobileLayoutProps) {
  const { resolvedTheme } = useTheme();

  // Theme-aware Saptiva logo
  const logoSrc =
    resolvedTheme === "dark"
      ? "/SaptivaAIlogo_blackbg.PNG" // White text logo for dark background
      : "/SaptivaAIlogo_whitebg.PNG"; // Dark text logo for light background

  return (
    <div className="relative flex h-[100dvh] w-full flex-col overflow-hidden bg-background text-foreground">
      <div className="absolute left-3 top-2.5 z-30 block">
        <button
          type="button"
          onClick={onRequestSidebar}
          className="flex h-9 w-9 items-center justify-center rounded-full border border-border bg-surface text-foreground shadow-card transition hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
          aria-label="Abrir historial"
        >
          <svg
            className="h-4 w-4"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
          >
            <path d="M4 6h16" strokeWidth="1.8" strokeLinecap="round" />
            <path d="M4 12h12" strokeWidth="1.8" strokeLinecap="round" />
            <path d="M4 18h8" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
        </button>
      </div>

      <div
        className={cn(
          "fixed inset-0 z-40 bg-black/50 transition-opacity duration-200",
          isMobileSidebarOpen
            ? "pointer-events-auto opacity-100"
            : "pointer-events-none opacity-0",
        )}
        onClick={onCloseSidebar}
      />

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 w-[85vw] max-w-[22rem] overflow-hidden rounded-r-xl bg-sidebar shadow-card transition-transform duration-300",
          isMobileSidebarOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="h-full" onClick={(event) => event.stopPropagation()}>
          {mobileSidebar}
        </div>
      </aside>

      <header className="sticky top-0 z-20 flex shrink-0 items-center justify-between gap-3 border-b border-border/40 bg-surface/95 pl-[52px] pr-3 py-2.5 backdrop-blur transition-all duration-200">
        {featureFlags.modelSelector && selectedModel && onModelChange ? (
          <ModelSelector
            models={models}
            selectedModel={selectedModel}
            onModelChange={onModelChange}
            className="max-w-[40%] min-w-0"
          />
        ) : null}
        <div className="flex items-center gap-3 shrink-0">
          <ModeToggle />
          <HelpOnboardingMenu ubicacion="encabezado-compacto" />
          <Image
            src={logoSrc}
            alt="Saptiva AI"
            width={100}
            height={28}
            className="h-7 w-auto"
            priority
          />
        </div>
      </header>

      <main className="flex-1 min-h-0 overflow-hidden">{children}</main>

      {footer ? (
        <div className="shrink-0 border-t border-border/40 bg-surface">
          {footer}
        </div>
      ) : null}
    </div>
  );
}

function LegacyChatShell({
  sidebar,
  children,
  footer,
  models,
  selectedModel,
  onModelChange,
}: ChatShellProps) {
  const { resolvedTheme } = useTheme();
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = React.useState(false);
  const [isDesktopSidebarCollapsed, setIsDesktopSidebarCollapsed] =
    React.useState(false);

  // Theme-aware Saptiva logo
  const logoSrc =
    resolvedTheme === "dark"
      ? "/SaptivaAIlogo_blackbg.PNG" // White text logo for dark background
      : "/SaptivaAIlogo_whitebg.PNG"; // Dark text logo for light background

  const handleCloseSidebar = React.useCallback(() => {
    setIsMobileSidebarOpen(false);
  }, []);

  const handleToggleDesktopSidebar = React.useCallback(() => {
    setIsDesktopSidebarCollapsed((collapsed) => !collapsed);
  }, []);

  const handleRequestSidebar = React.useCallback(() => {
    if (
      typeof window !== "undefined" &&
      window.matchMedia("(min-width: 1024px)").matches
    ) {
      setIsDesktopSidebarCollapsed(false);
    } else {
      setIsMobileSidebarOpen(true);
    }
  }, []);

  React.useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsMobileSidebarOpen(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const desktopSidebar = React.useMemo(() => {
    if (!React.isValidElement(sidebar)) return sidebar;

    // React 19: cloneElement requires explicit typing for additional props
    return React.cloneElement(
      sidebar as React.ReactElement<Record<string, unknown>>,
      {
        onCollapse: handleToggleDesktopSidebar,
        isCollapsed: isDesktopSidebarCollapsed,
        layoutVersion: "legacy",
      },
    );
  }, [sidebar, handleToggleDesktopSidebar, isDesktopSidebarCollapsed]);

  const mobileSidebar = React.useMemo(() => {
    if (!React.isValidElement(sidebar)) return sidebar;

    // React 19: cloneElement requires explicit typing for additional props
    return React.cloneElement(
      sidebar as React.ReactElement<Record<string, unknown>>,
      {
        onClose: handleCloseSidebar,
        layoutVersion: "legacy",
      },
    );
  }, [sidebar, handleCloseSidebar]);

  return (
    <div className="safe-area-top relative flex h-[100dvh] w-full overflow-hidden bg-background text-foreground">
      {/* Desktop sidebar - with persistent rail */}
      <aside
        className={cn(
          "hidden h-full shrink-0 overflow-hidden transition-[width] duration-200 ease-in-out lg:flex bg-sidebar",
          isDesktopSidebarCollapsed
            ? "lg:w-16"
            : "lg:w-[288px] border-r border-border",
        )}
      >
        <div className="relative h-full w-full">{desktopSidebar}</div>
      </aside>

      {/* Mobile sidebar */}
      <div
        className={cn(
          "fixed inset-0 z-40 bg-black/50 transition-opacity duration-200 lg:hidden",
          isMobileSidebarOpen
            ? "pointer-events-auto opacity-100"
            : "pointer-events-none opacity-0",
        )}
        onClick={handleCloseSidebar}
      />
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 w-[85vw] max-w-[22rem] overflow-hidden rounded-r-xl bg-sidebar shadow-card transition-transform duration-300 lg:hidden",
          isMobileSidebarOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="h-full" onClick={(event) => event.stopPropagation()}>
          {mobileSidebar}
        </div>
      </aside>

      {/* Chat area - Following saptiva-chat-fixes-v3.yaml structure */}
      <main className="flex-1 min-w-0 flex flex-col">
        {/* Header con selector de modelo - UX-001 */}
        <header className="sticky top-0 z-20 shrink-0 border-b border-border/30 bg-surface/95 backdrop-blur px-4 py-3 transition-all duration-200">
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleRequestSidebar}
                className="m-0 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full border border-border bg-surface text-text shadow-card transition hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 lg:hidden"
                aria-label="Mostrar conversaciones"
              >
                <svg
                  className="h-[18px] w-[18px]"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                >
                  <path d="M4 6h16" strokeWidth="1.8" strokeLinecap="round" />
                  <path d="M4 12h12" strokeWidth="1.8" strokeLinecap="round" />
                  <path d="M4 18h8" strokeWidth="1.8" strokeLinecap="round" />
                </svg>
              </button>

              {/* Model Selector - header-left según UX-001 */}
              {featureFlags.modelSelector && selectedModel && onModelChange && (
                <ModelSelector
                  models={models}
                  selectedModel={selectedModel}
                  onModelChange={onModelChange}
                  className="max-w-full whitespace-nowrap"
                />
              )}
            </div>
            <div className="ml-auto flex items-center gap-2">
              <ModeToggle />
              <HelpOnboardingMenu ubicacion="movil" />
              <Image
                src={logoSrc}
                alt="Saptiva AI"
                width={120}
                height={32}
                className="h-8 w-auto"
                priority
              />
            </div>
          </div>
        </header>

        {/* Message area - scroll manejado por ChatInterface CHT-05 */}
        <section className="flex-1 min-h-0 px-2 py-4">{children}</section>

        {/* Input area as footer - conditionally render */}
        {footer && (
          <footer className="shrink-0 border-t border-border">{footer}</footer>
        )}
      </main>
    </div>
  );
}
