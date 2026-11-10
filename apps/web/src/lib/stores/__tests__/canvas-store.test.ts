/**
 * Tests de canvas-store: persistencia entre navegaciones (loadFromMongoDB).
 *
 * Regresión 2026-07-21 (e2e chart-caching): el estado se guardaba con
 * syncToMongoDB pero nunca se restauraba; y al restaurar, un GET stale no
 * debe pisar el canvas VIVO del turno en curso.
 */
import { act } from "@testing-library/react";
import { useCanvasStore } from "../canvas-store";
import { apiClient } from "../../api-client";
import type { ChartData } from "@/lib/types";

jest.mock("../../api-client", () => ({
  apiClient: {
    getCanvasState: jest.fn(),
    saveCanvasState: jest.fn(),
  },
}));

jest.mock("../../logger", () => ({
  logWarn: jest.fn(),
  logDebug: jest.fn(),
  logError: jest.fn(),
}));

const mockedGet = apiClient.getCanvasState as jest.Mock;

const chartFixture: ChartData = {
  type: "chart",
  title: "venta_hora",
  chart_status: "success",
  response_text: "narración",
  plotly_config: { data: [], layout: {}, config: {} },
} as unknown as ChartData;

function resetStore() {
  act(() => {
    useCanvasStore.setState({
      isSidebarOpen: false,
      activeArtifactId: null,
      activeMessageId: null,
      activeChart: null,
      currentSessionId: null,
    });
  });
}

describe("canvas-store loadFromMongoDB", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    resetStore();
  });

  it("restaura el estado persistido en entrada fría (canvas vacío)", async () => {
    mockedGet.mockResolvedValue({
      is_sidebar_open: true,
      active_artifact_id: "msg-1",
      active_message_id: "msg-1",
      active_chart: chartFixture,
    });

    await act(() => useCanvasStore.getState().loadFromMongoDB("conv-1"));

    const state = useCanvasStore.getState();
    expect(state.isSidebarOpen).toBe(true);
    expect(state.activeChart).toEqual(chartFixture);
    expect(state.currentSessionId).toBe("conv-1");
  });

  it("NO pisa un canvas vivo con estado remoto stale", async () => {
    act(() => {
      useCanvasStore.setState({
        isSidebarOpen: true,
        activeChart: chartFixture,
        activeMessageId: "msg-live",
      });
    });
    // El backend aún no tiene el PATCH del turno en curso: estado vacío.
    mockedGet.mockResolvedValue({
      is_sidebar_open: false,
      active_artifact_id: null,
      active_message_id: null,
      active_chart: null,
    });

    await act(() => useCanvasStore.getState().loadFromMongoDB("conv-1"));

    const state = useCanvasStore.getState();
    expect(state.activeChart).toEqual(chartFixture); // sigue vivo
    expect(state.isSidebarOpen).toBe(true);
    expect(state.currentSessionId).toBe("conv-1"); // pero sí fija la sesión
  });

  it("fija la sesión aunque el GET falle", async () => {
    mockedGet.mockRejectedValue(new Error("network"));

    await act(() => useCanvasStore.getState().loadFromMongoDB("conv-2"));

    expect(useCanvasStore.getState().currentSessionId).toBe("conv-2");
  });
});
