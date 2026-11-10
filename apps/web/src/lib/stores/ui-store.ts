/**
 * UI State Store
 *
 * Manages application UI state:
 * - Sidebar visibility
 * - Theme (light/dark)
 * - Connection status
 */

import { create } from "zustand";
import { devtools, persist } from "zustand/middleware";
import { apiClient } from "../api-client";
import { logWarn } from "../logger";

export type ConnectionStatus = "connected" | "disconnected" | "connecting";
export type Theme = "light" | "dark";

interface UIState {
  // State
  sidebarOpen: boolean;
  theme: Theme;
  connectionStatus: ConnectionStatus;

  // Actions
  setSidebarOpen: (open: boolean) => void;
  setTheme: (theme: Theme) => void;
  setConnectionStatus: (status: ConnectionStatus) => void;
  checkConnection: () => Promise<void>;
  clearAllData: () => void;
}

export const useUIStore = create<UIState>()(
  devtools(
    persist(
      (set) => ({
        // Initial state
        sidebarOpen: false,
        theme: "light",
        connectionStatus: "disconnected",

        // Actions
        setSidebarOpen: (open) => set({ sidebarOpen: open }),
        setTheme: (theme) => set({ theme }),
        setConnectionStatus: (status) => set({ connectionStatus: status }),

        checkConnection: async () => {
          try {
            set({ connectionStatus: "connecting" });
            const isConnected = await apiClient.checkConnection();
            set({
              connectionStatus: isConnected ? "connected" : "disconnected",
            });
          } catch (error) {
            set({ connectionStatus: "disconnected" });
          }
        },

        clearAllData: () => {
          set({
            sidebarOpen: false,
            connectionStatus: "disconnected",
          });

          // Clear localStorage
          try {
            localStorage.removeItem("ui-store");
            const cacheKeys = [
              "chat-cache",
              "research-cache",
              "session-cache",
              "msw",
              "mock-api",
              "dev-mode",
            ];
            cacheKeys.forEach((key) => {
              localStorage.removeItem(key);
            });
          } catch (error) {
            logWarn("Failed to clear localStorage:", error);
          }
        },
      }),
      {
        name: "ui-store",
        partialize: (state) => ({
          theme: state.theme,
        }),
      },
    ),
    {
      name: "ui-store",
    },
  ),
);

// Backward compatibility export
export const useUI = () => {
  const store = useUIStore();
  return {
    sidebarOpen: store.sidebarOpen,
    theme: store.theme,
    connectionStatus: store.connectionStatus,
    setSidebarOpen: store.setSidebarOpen,
    setTheme: store.setTheme,
    checkConnection: store.checkConnection,
    clearAllData: store.clearAllData,
  };
};
