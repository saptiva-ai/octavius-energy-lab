import * as React from 'react'
import { cn } from '../../lib/utils'

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string
  error?: string
  helperText?: string
  autoResize?: boolean
}

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, label, error, helperText, autoResize = false, id, rows = 3, onChange, ...props }, ref) => {
    const textareaRef = React.useRef<HTMLTextAreaElement>(null)
    const generatedId = React.useId()
    const inputId = id || generatedId

    React.useImperativeHandle(ref, () => textareaRef.current as HTMLTextAreaElement);

    // Auto-resize functionality
    const adjustHeight = React.useCallback(() => {
      const textarea = textareaRef.current
      if (textarea && autoResize) {
        textarea.style.height = 'auto'
        textarea.style.height = `${textarea.scrollHeight}px`
      }
    }, [autoResize])

    // Handle change with auto-resize
    const handleChange = React.useCallback(
      (e: React.ChangeEvent<HTMLTextAreaElement>) => {
        onChange?.(e)
        if (autoResize) {
          adjustHeight()
        }
      },
      [onChange, adjustHeight, autoResize]
    )

    // Auto-resize on mount
    React.useEffect(() => {
      if (autoResize) {
        adjustHeight()
      }
    }, [adjustHeight, autoResize])

    return (
      <div className="w-full">
        {label && (
          <label htmlFor={inputId} className="block text-sm font-bold text-text mb-1">
            {label}
          </label>
        )}
        <textarea
          id={inputId}
          rows={rows}
          className={cn(
            'flex min-h-[80px] w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-text placeholder:text-text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 disabled:cursor-not-allowed disabled:opacity-50',
            autoResize && 'resize-none',
            error && 'border-danger focus-visible:ring-danger/60',
            className
          )}
          ref={textareaRef}
          onChange={handleChange}
          {...props}
        />
        {error && (
          <p className="mt-1 text-sm text-danger">{error}</p>
        )}
        {helperText && !error && (
          <p className="mt-1 text-sm text-text-muted">{helperText}</p>
        )}
      </div>
    )
  }
)

Textarea.displayName = 'Textarea'

export { Textarea }
