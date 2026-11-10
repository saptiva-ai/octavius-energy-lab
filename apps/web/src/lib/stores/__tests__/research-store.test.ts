/**
 * Tests for Research Store
 *
 * Tests research task management and state tracking
 */

import { renderHook, act } from "@testing-library/react";
import { useResearchStore, useResearch } from "../research-store";
import { ResearchTask } from "../../types";

describe("useResearchStore", () => {
  beforeEach(() => {
    // Reset store state before each test
    const { result } = renderHook(() => useResearchStore());
    act(() => {
      result.current.clearAllData();
    });
  });

  describe("initial state", () => {
    it("should initialize with empty tasks", () => {
      const { result } = renderHook(() => useResearchStore());

      expect(result.current.activeTasks).toEqual([]);
      expect(result.current.currentTaskId).toBeNull();
    });
  });

  describe("addTask", () => {
    it("should add a task to active tasks", () => {
      const { result } = renderHook(() => useResearchStore());

      const task: ResearchTask = {
        id: "task-1",
        query: "Test query",
        status: "pending",
        progress: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      act(() => {
        result.current.addTask(task);
      });

      expect(result.current.activeTasks).toHaveLength(1);
      expect(result.current.activeTasks[0]).toEqual(task);
    });

    it("should add multiple tasks", () => {
      const { result } = renderHook(() => useResearchStore());

      const task1: ResearchTask = {
        id: "task-1",
        query: "Query 1",
        status: "pending",
        progress: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      const task2: ResearchTask = {
        id: "task-2",
        query: "Query 2",
        status: "pending",
        progress: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      act(() => {
        result.current.addTask(task1);
        result.current.addTask(task2);
      });

      expect(result.current.activeTasks).toHaveLength(2);
      expect(result.current.activeTasks[0].id).toBe("task-1");
      expect(result.current.activeTasks[1].id).toBe("task-2");
    });

    it("should preserve existing tasks when adding new one", () => {
      const { result } = renderHook(() => useResearchStore());

      const task1: ResearchTask = {
        id: "task-1",
        query: "Query 1",
        status: "pending",
        progress: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      const task2: ResearchTask = {
        id: "task-2",
        query: "Query 2",
        status: "running",
        progress: 50,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      act(() => {
        result.current.addTask(task1);
      });

      act(() => {
        result.current.addTask(task2);
      });

      expect(result.current.activeTasks).toHaveLength(2);
      expect(result.current.activeTasks[0]).toEqual(task1);
    });
  });

  describe("updateTask", () => {
    it("should update task status", () => {
      const { result } = renderHook(() => useResearchStore());

      const task: ResearchTask = {
        id: "task-1",
        query: "Test query",
        status: "pending",
        progress: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      act(() => {
        result.current.addTask(task);
      });

      act(() => {
        result.current.updateTask("task-1", { status: "running" });
      });

      expect(result.current.activeTasks[0].status).toBe("running");
    });

    it("should update task progress", () => {
      const { result } = renderHook(() => useResearchStore());

      const task: ResearchTask = {
        id: "task-1",
        query: "Test query",
        status: "running",
        progress: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      act(() => {
        result.current.addTask(task);
      });

      act(() => {
        result.current.updateTask("task-1", { progress: 50 });
      });

      expect(result.current.activeTasks[0].progress).toBe(50);
    });

    it("should update multiple fields", () => {
      const { result } = renderHook(() => useResearchStore());

      const task: ResearchTask = {
        id: "task-1",
        query: "Test query",
        status: "pending",
        progress: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      act(() => {
        result.current.addTask(task);
      });

      act(() => {
        result.current.updateTask("task-1", {
          status: "completed",
          progress: 100,
        });
      });

      expect(result.current.activeTasks[0].status).toBe("completed");
      expect(result.current.activeTasks[0].progress).toBe(100);
    });

    it("should only update the specified task", () => {
      const { result } = renderHook(() => useResearchStore());

      const task1: ResearchTask = {
        id: "task-1",
        query: "Query 1",
        status: "pending",
        progress: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      const task2: ResearchTask = {
        id: "task-2",
        query: "Query 2",
        status: "pending",
        progress: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      act(() => {
        result.current.addTask(task1);
        result.current.addTask(task2);
      });

      act(() => {
        result.current.updateTask("task-1", { status: "running" });
      });

      expect(result.current.activeTasks[0].status).toBe("running");
      expect(result.current.activeTasks[1].status).toBe("pending");
    });

    it("should not modify tasks if task id not found", () => {
      const { result } = renderHook(() => useResearchStore());

      const task: ResearchTask = {
        id: "task-1",
        query: "Test query",
        status: "pending",
        progress: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      act(() => {
        result.current.addTask(task);
      });

      act(() => {
        result.current.updateTask("non-existent-task", { status: "running" });
      });

      expect(result.current.activeTasks[0].status).toBe("pending");
    });
  });

  describe("removeTask", () => {
    it("should remove a task", () => {
      const { result } = renderHook(() => useResearchStore());

      const task: ResearchTask = {
        id: "task-1",
        query: "Test query",
        status: "pending",
        progress: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      act(() => {
        result.current.addTask(task);
      });

      expect(result.current.activeTasks).toHaveLength(1);

      act(() => {
        result.current.removeTask("task-1");
      });

      expect(result.current.activeTasks).toHaveLength(0);
    });

    it("should remove only the specified task", () => {
      const { result } = renderHook(() => useResearchStore());

      const task1: ResearchTask = {
        id: "task-1",
        query: "Query 1",
        status: "pending",
        progress: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      const task2: ResearchTask = {
        id: "task-2",
        query: "Query 2",
        status: "pending",
        progress: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      act(() => {
        result.current.addTask(task1);
        result.current.addTask(task2);
      });

      act(() => {
        result.current.removeTask("task-1");
      });

      expect(result.current.activeTasks).toHaveLength(1);
      expect(result.current.activeTasks[0].id).toBe("task-2");
    });

    it("should clear currentTaskId if removing current task", () => {
      const { result } = renderHook(() => useResearchStore());

      const task: ResearchTask = {
        id: "task-1",
        query: "Test query",
        status: "pending",
        progress: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      act(() => {
        result.current.addTask(task);
        result.current.setCurrentTaskId("task-1");
      });

      expect(result.current.currentTaskId).toBe("task-1");

      act(() => {
        result.current.removeTask("task-1");
      });

      expect(result.current.currentTaskId).toBeNull();
    });

    it("should not modify state if task id not found", () => {
      const { result } = renderHook(() => useResearchStore());

      const task: ResearchTask = {
        id: "task-1",
        query: "Test query",
        status: "pending",
        progress: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      act(() => {
        result.current.addTask(task);
      });

      act(() => {
        result.current.removeTask("non-existent-task");
      });

      expect(result.current.activeTasks).toHaveLength(1);
    });
  });

  describe("setCurrentTaskId", () => {
    it("should set current task id", () => {
      const { result } = renderHook(() => useResearchStore());

      act(() => {
        result.current.setCurrentTaskId("task-123");
      });

      expect(result.current.currentTaskId).toBe("task-123");
    });

    it("should clear current task id", () => {
      const { result } = renderHook(() => useResearchStore());

      act(() => {
        result.current.setCurrentTaskId("task-123");
      });

      act(() => {
        result.current.setCurrentTaskId(null);
      });

      expect(result.current.currentTaskId).toBeNull();
    });
  });

  describe("clearAllData", () => {
    it("should clear all tasks", () => {
      const { result } = renderHook(() => useResearchStore());

      const task: ResearchTask = {
        id: "task-1",
        query: "Test query",
        status: "pending",
        progress: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      act(() => {
        result.current.addTask(task);
      });

      act(() => {
        result.current.clearAllData();
      });

      expect(result.current.activeTasks).toEqual([]);
    });

    it("should clear current task id", () => {
      const { result } = renderHook(() => useResearchStore());

      act(() => {
        result.current.setCurrentTaskId("task-123");
      });

      act(() => {
        result.current.clearAllData();
      });

      expect(result.current.currentTaskId).toBeNull();
    });
  });
});

describe("useResearch (backward compatibility)", () => {
  it("should return store state and actions", () => {
    const { result } = renderHook(() => useResearch());

    expect(result.current).toHaveProperty("activeTasks");
    expect(result.current).toHaveProperty("currentTaskId");
    expect(result.current).toHaveProperty("addTask");
    expect(result.current).toHaveProperty("updateTask");
    expect(result.current).toHaveProperty("removeTask");
    expect(result.current).toHaveProperty("setCurrentTaskId");
  });

  it("should manage tasks through useResearch hook", () => {
    const { result } = renderHook(() => useResearch());

    const task: ResearchTask = {
      id: "task-1",
      query: "Test query",
      status: "pending",
      progress: 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    act(() => {
      result.current.addTask(task);
    });

    expect(result.current.activeTasks).toHaveLength(1);
  });
});
