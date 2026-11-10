import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { ChartData, CanvasChartSync } from "@/lib/types";
import { apiClient } from "@/lib/api-client";
import { logWarn } from "@/lib/logger";

const DEFAULT_CANVAS_WIDTH = 40;

const getChartVisualizationSignature = (
  chart: ChartData | null | undefined,
): string | null => {
  if (!chart) return null;

  try {
    return JSON.stringify({
      title: chart.title,
      data_as_of: chart.data_as_of,
      source: chart.source,
      time_range: chart.time_range,
      plotly_data: chart.plotly_config?.data ?? [],
      plotly_layout: chart.plotly_config?.layout ?? {},
      plotly_config: chart.plotly_config?.config ?? {},
    });
  } catch {
    return null;
  }
};

export const clampCanvasWidthPercent = (width?: number | null): number => {
  const numericWidth =
    typeof width === "number" ? width : Number(width ?? DEFAULT_CANVAS_WIDTH);

  if (!Number.isFinite(numericWidth)) {
    return DEFAULT_CANVAS_WIDTH;
  }

  return Math.min(Math.max(numericWidth, 30), 70);
};

interface CanvasState {
  isSidebarOpen: boolean;
  activeArtifactId: string | null;
  activeArtifactData: any | null;

  // Chart artifact state (generic)
  activeChart: ChartData | null;
  activeMessageId: string | null;
  chartHistory: CanvasChartSync[];

  // BA-004: UX feedback for chart opening
  chartHighlighted: boolean;

  // Current session ID for persistence
  currentSessionId: string | null;

  // Canvas width as percentage of viewport (30-70%, default 40%)
  canvasWidthPercent: number;

  // Existing methods
  setArtifact: (id: string | null) => void;
  openArtifact: (type: string, data: any) => void;
  toggleSidebar: () => void;
  reset: () => void;
  setCanvasWidth: (widthPercent: number) => void;

  // Chart methods (generic)
  openChart: (
    chartData: ChartData,
    artifactId: string,
    messageId: string,
    autoOpen?: boolean,
  ) => void;
  setActiveMessage: (messageId: string | null) => void;
  addToChartHistory: (sync: CanvasChartSync) => void;
  clearChartHistory: () => void;

  // MongoDB persistence
  setCurrentSessionId: (sessionId: string | null) => void;
  syncToMongoDB: () => Promise<void>;
  loadFromMongoDB: (sessionId: string) => Promise<void>;
}

// SINGLETON REAL por runtime del navegador (fix del fixme chart-caching,
// 2026-07-21): en dev, la compilación bajo demanda de Next puede incluir este
// módulo en el chunk de más de una ruta; la navegación SPA /chat →
// /chat/[chatId] lo RE-EVALÚA y crea una SEGUNDA instancia de zustand — el
// chart vivía en la instancia vieja y el panel de la ruta nueva se suscribía
// a la nueva (vacía): el "canvas se vació solo" del e2e (comprobado con
// trace: 4 instancias armadas en un run, 0 transiciones de cierre). Anclar
// la instancia en globalThis garantiza UNA sola, sin efecto en prod.
const _crearCanvasStore = () =>
  create<CanvasState>()(
    persist(
      (set, get) => ({
        isSidebarOpen: false,
        activeArtifactId: null,
        activeArtifactData: null,
        activeChart: null,
        activeMessageId: null,
        chartHistory: [],
        chartHighlighted: false, // BA-004: UX feedback state
        currentSessionId: null,
        canvasWidthPercent: DEFAULT_CANVAS_WIDTH, // Default to 40% of viewport width

        setArtifact: (id) =>
          set((state) => ({
            activeArtifactId: id,
            activeArtifactData: null,
            activeChart: null, // Clear chart when setting artifact
            isSidebarOpen: id ? true : state.isSidebarOpen,
          })),

        openArtifact: (_type, data) =>
          set(() => ({
            activeArtifactId: null,
            activeArtifactData: data,
            activeChart: null, // Clear chart when opening artifact
            isSidebarOpen: true,
          })),

        toggleSidebar: () => {
          set((state) => {
            const newOpenState = !state.isSidebarOpen;

            // If closing, clear active message and deactivate all charts
            if (!newOpenState) {
              return {
                isSidebarOpen: false,
                activeMessageId: null,
                chartHistory: state.chartHistory.map((c) => ({
                  ...c,
                  isActive: false,
                })),
              };
            }

            return { isSidebarOpen: true };
          });

          // Sync to MongoDB after state change
          get().syncToMongoDB();
        },

        reset: () =>
          set(() => ({
            isSidebarOpen: false,
            activeArtifactId: null,
            activeArtifactData: null,
            activeChart: null,
            activeMessageId: null,
            chartHistory: [],
          })),

        // Set canvas width (percentage of viewport, constrained to 30-70%)
        setCanvasWidth: (widthPercent) =>
          set(() => ({
            canvasWidthPercent: clampCanvasWidthPercent(widthPercent),
          })),

        // Open a chart artifact in the canvas (main method)
        openChart: (chartData, artifactId, messageId, autoOpen = false) => {
          const {
            chartHistory,
            addToChartHistory,
            activeChart,
            activeArtifactId,
          } = get();

          // BA-004: If the exact same visualization is already open, only trigger highlight.
          // BUG-2026-02-04: Compare full visualization signature to avoid stale charts
          // when only layout/context changes between consecutive queries.
          const activeChartSignature =
            getChartVisualizationSignature(activeChart);
          const incomingChartSignature =
            getChartVisualizationSignature(chartData);

          const isSameChart =
            activeArtifactId === artifactId &&
            !!activeChartSignature &&
            activeChartSignature === incomingChartSignature;

          if (isSameChart && get().isSidebarOpen) {
            set({ chartHighlighted: true });
            setTimeout(() => set({ chartHighlighted: false }), 600);
            return;
          }

          set({
            activeChart: chartData,
            // Don't set activeArtifactId for temp artifacts or when we have chartData
            // This prevents canvas-panel from trying to fetch the artifact
            activeArtifactId: artifactId !== "temp" ? artifactId : null,
            activeMessageId: messageId,
            isSidebarOpen: true,
            activeArtifactData: null, // Clear audit data if present
            chartHighlighted: true, // BA-004: Brief highlight on open
          });

          // BA-004: Clear highlight after animation
          setTimeout(() => set({ chartHighlighted: false }), 600);

          // Add to history if not already present
          if (!chartHistory.find((c) => c.artifactId === artifactId)) {
            addToChartHistory({
              artifactId,
              messageId,
              isActive: true,
            });
          } else {
            // Update existing entry to mark as active
            set((state) => ({
              chartHistory: state.chartHistory.map((c) =>
                c.artifactId === artifactId
                  ? { ...c, isActive: true }
                  : { ...c, isActive: false },
              ),
            }));
          }

          if (process.env.NODE_ENV === "development") {
            logWarn("[Canvas] Opened chart:", {
              artifactId,
              messageId,
              title: chartData.title,
              autoOpen,
            });
          }

          // Sync to MongoDB after opening chart
          get().syncToMongoDB();
        },

        // 🆕 Set active message (for highlight synchronization)
        setActiveMessage: (messageId) =>
          set((state) => ({
            activeMessageId: messageId,
            chartHistory: state.chartHistory.map((c) => ({
              ...c,
              isActive: c.messageId === messageId,
            })),
          })),

        // 🆕 Add chart to history (with max limit of 20 charts)
        addToChartHistory: (sync) =>
          set((state) => {
            const MAX_CHART_HISTORY = 20;
            const updatedHistory = [
              ...state.chartHistory.map((c) => ({ ...c, isActive: false })),
              sync,
            ];

            // Keep only the last 20 charts
            const limitedHistory =
              updatedHistory.length > MAX_CHART_HISTORY
                ? updatedHistory.slice(-MAX_CHART_HISTORY)
                : updatedHistory;

            return { chartHistory: limitedHistory };
          }),

        // 🆕 Clear chart history (on session change)
        clearChartHistory: () =>
          set(() => ({
            chartHistory: [],
            activeChart: null,
            activeMessageId: null,
          })),

        // Set current session ID for persistence
        setCurrentSessionId: (sessionId) =>
          set({ currentSessionId: sessionId }),

        // Sync canvas state to MongoDB
        syncToMongoDB: async () => {
          const state = get();
          const {
            currentSessionId,
            isSidebarOpen,
            activeArtifactId,
            activeMessageId,
            activeChart,
          } = state;

          if (!currentSessionId) {
            // No session ID set, skip sync
            return;
          }

          try {
            await apiClient.saveCanvasState(currentSessionId, {
              is_sidebar_open: isSidebarOpen,
              active_artifact_id: activeArtifactId,
              active_message_id: activeMessageId,
              active_chart: activeChart,
            });
          } catch (_error) {
            // Silently fail - sync will retry on next change
          }
        },

        // Load canvas state from MongoDB
        loadFromMongoDB: async (sessionId) => {
          try {
            const canvasState = await apiClient.getCanvasState(sessionId);

            // Canvas VIVO gana: si el turno en curso ya abrió un chart o un
            // artefacto (la URL transiciona a la conversación a mitad del
            // stream), el estado remoto puede venir stale/vacío y cerraría lo
            // que el usuario está viendo. Solo aplica en entrada fría.
            const { activeChart, activeArtifactId } = get();
            if (activeChart || activeArtifactId) {
              set({ currentSessionId: sessionId });
              return;
            }

            if (canvasState) {
              set({
                isSidebarOpen: canvasState.is_sidebar_open || false,
                activeArtifactId: canvasState.active_artifact_id || null,
                activeMessageId: canvasState.active_message_id || null,
                activeChart: canvasState.active_chart || null,
                currentSessionId: sessionId,
              });
            } else {
              // No saved state, just set the session ID
              set({ currentSessionId: sessionId });
            }
          } catch (_error) {
            // Set session ID anyway so we can save later
            set({ currentSessionId: sessionId });
          }
        },
      }),
      {
        name: "canvas-store",
        version: 2, // Bump to v2 to force full localStorage reset
        // Only persist width preference - Canvas state should reset per conversation
        partialize: (state) => ({
          canvasWidthPercent: state.canvasWidthPercent,
          // DO NOT persist isSidebarOpen - causes Canvas to stay open between conversations
        }),
      },
    ),
  );

const _globalConStore = globalThis as typeof globalThis & {
  __canvasStore?: ReturnType<typeof _crearCanvasStore>;
};
export const useCanvasStore = (_globalConStore.__canvasStore ??=
  _crearCanvasStore());
