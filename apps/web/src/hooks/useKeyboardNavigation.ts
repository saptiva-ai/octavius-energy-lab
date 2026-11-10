/**
 * Custom hook for keyboard navigation in lists
 * Provides arrow key navigation, Enter to select, and Escape to cancel
 */

import { useEffect, useState, useRef, useCallback } from 'react'

export interface UseKeyboardNavigationOptions<T> {
  items: T[]
  onSelect: (item: T) => void
  activeItemId?: string | null
  getItemId: (item: T) => string
  isEnabled?: boolean
  loop?: boolean // Whether to loop from end to start
  onEscape?: () => void
}

export function useKeyboardNavigation<T>({
  items,
  onSelect,
  activeItemId,
  getItemId,
  isEnabled = true,
  loop = true,
  onEscape,
}: UseKeyboardNavigationOptions<T>) {
  // Track focused index (keyboard focus, different from activeItemId which is selected item)
  const [focusedIndex, setFocusedIndex] = useState<number>(-1)
  const listRef = useRef<HTMLElement>(null)

  // Find index of active item
  const activeIndex = items.findIndex((item) => getItemId(item) === activeItemId)

  // Initialize focused index to active item
  useEffect(() => {
    if (activeIndex >= 0 && focusedIndex === -1) {
      setFocusedIndex(activeIndex)
    }
  }, [activeIndex, focusedIndex])

  // Get focused item
  const focusedItem = focusedIndex >= 0 && focusedIndex < items.length
    ? items[focusedIndex]
    : null

  // Move focus up
  const moveFocusUp = useCallback(() => {
    setFocusedIndex((prev) => {
      if (prev <= 0) {
        return loop ? items.length - 1 : 0
      }
      return prev - 1
    })
  }, [items.length, loop])

  // Move focus down
  const moveFocusDown = useCallback(() => {
    setFocusedIndex((prev) => {
      if (prev >= items.length - 1) {
        return loop ? 0 : items.length - 1
      }
      return prev + 1
    })
  }, [items.length, loop])

  // Select focused item
  const selectFocusedItem = useCallback(() => {
    if (focusedItem) {
      onSelect(focusedItem)
    }
  }, [focusedItem, onSelect])

  // Keyboard event handler
  useEffect(() => {
    if (!isEnabled) return

    const handleKeyDown = (e: KeyboardEvent) => {
      // Only handle if not in an input/textarea
      const target = e.target as HTMLElement
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
        return
      }

      switch (e.key) {
        case 'ArrowUp':
          e.preventDefault()
          moveFocusUp()
          break
        case 'ArrowDown':
          e.preventDefault()
          moveFocusDown()
          break
        case 'Enter':
          e.preventDefault()
          selectFocusedItem()
          break
        case 'Escape':
          e.preventDefault()
          if (onEscape) {
            onEscape()
          }
          break
        case 'Home':
          e.preventDefault()
          setFocusedIndex(0)
          break
        case 'End':
          e.preventDefault()
          setFocusedIndex(items.length - 1)
          break
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isEnabled, moveFocusUp, moveFocusDown, selectFocusedItem, onEscape, items.length])

  // Scroll focused item into view
  useEffect(() => {
    if (focusedIndex >= 0 && listRef.current) {
      const focusedElement = listRef.current.querySelector(
        `[data-keyboard-index="${focusedIndex}"]`
      ) as HTMLElement

      if (focusedElement) {
        focusedElement.scrollIntoView({
          block: 'nearest',
          behavior: 'smooth',
        })
      }
    }
  }, [focusedIndex])

  return {
    focusedIndex,
    focusedItem,
    setFocusedIndex,
    listRef,
    // Helper to check if an item is focused
    isFocused: (item: T) => {
      const itemId = getItemId(item)
      return focusedItem ? getItemId(focusedItem) === itemId : false
    },
    // ARIA props for the list container
    listProps: {
      ref: listRef,
      role: 'listbox',
      'aria-activedescendant': focusedItem ? getItemId(focusedItem) : undefined,
      tabIndex: 0,
    },
    // Function to get ARIA props for each item
    getItemProps: (item: T, index: number) => ({
      role: 'option',
      'aria-selected': getItemId(item) === activeItemId,
      'data-keyboard-index': index,
      id: getItemId(item),
      tabIndex: -1, // Items are not directly focusable, list container handles focus
    }),
  }
}