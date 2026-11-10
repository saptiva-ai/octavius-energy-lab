import { useCallback, useState } from 'react'
import type { ToolId } from '@/types/tools'

export function useSelectedTools(initial: ToolId[] = []) {
  const [selected, setSelected] = useState<ToolId[]>(initial)

  const addTool = useCallback((id: ToolId) => {
    setSelected((prev) => (prev.includes(id) ? prev : [...prev, id]))
  }, [])

  const removeTool = useCallback((id: ToolId) => {
    setSelected((prev) => prev.filter((toolId) => toolId !== id))
  }, [])

  const toggleTool = useCallback((id: ToolId) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((toolId) => toolId !== id) : [...prev, id]))
  }, [])

  const clearTools = useCallback(() => setSelected([]), [])

  return { selected, addTool, removeTool, toggleTool, clearTools }
}
