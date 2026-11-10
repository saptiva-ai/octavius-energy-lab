import { useLayoutEffect } from 'react'

export function useAutosizeTextArea(textarea: HTMLTextAreaElement | null, value: string, maxHeightPx = 176) {
  useLayoutEffect(() => {
    if (!textarea) return

    textarea.style.height = '0px'
    const next = Math.min(textarea.scrollHeight, maxHeightPx)
    textarea.style.height = `${next}px`
    textarea.style.overflowY = textarea.scrollHeight > maxHeightPx ? 'auto' : 'hidden'
  }, [textarea, value, maxHeightPx])
}
