/**
 * Research State Store
 *
 * Manages deep research tasks:
 * - Active research tasks
 * - Task progress tracking
 * - Current task selection
 */

import { create } from "zustand";
import { devtools } from "zustand/middleware";
import { ResearchTask } from "../types";

interface ResearchState {
  // State
  activeTasks: ResearchTask[];
  currentTaskId: string | null;

  // Actions
  addTask: (task: ResearchTask) => void;
  updateTask: (taskId: string, updates: Partial<ResearchTask>) => void;
  removeTask: (taskId: string) => void;
  setCurrentTaskId: (taskId: string | null) => void;
  clearAllData: () => void;
}

export const useResearchStore = create<ResearchState>()(
  devtools(
    (set) => ({
      // Initial state
      activeTasks: [],
      currentTaskId: null,

      // Actions
      addTask: (task) =>
        set((state) => ({
          activeTasks: [...state.activeTasks, task],
        })),

      updateTask: (taskId, updates) =>
        set((state) => ({
          activeTasks: state.activeTasks.map((task) =>
            task.id === taskId ? { ...task, ...updates } : task,
          ),
        })),

      removeTask: (taskId) =>
        set((state) => ({
          activeTasks: state.activeTasks.filter((task) => task.id !== taskId),
          currentTaskId:
            state.currentTaskId === taskId ? null : state.currentTaskId,
        })),

      setCurrentTaskId: (taskId) => set({ currentTaskId: taskId }),

      clearAllData: () => {
        set({
          activeTasks: [],
          currentTaskId: null,
        });
      },
    }),
    {
      name: "research-store",
    },
  ),
);

// Backward compatibility export
export const useResearch = () => {
  const store = useResearchStore();
  return {
    activeTasks: store.activeTasks,
    currentTaskId: store.currentTaskId,
    addTask: store.addTask,
    updateTask: store.updateTask,
    removeTask: store.removeTask,
    setCurrentTaskId: store.setCurrentTaskId,
  };
};
