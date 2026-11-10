'use client'

import * as React from 'react'
import { cn } from '../../lib/utils'

type ButtonVariant = 'default' | 'destructive' | 'outline' | 'secondary' | 'ghost' | 'link'
type ButtonSize = 'default' | 'sm' | 'lg' | 'icon'

const getButtonClasses = (variant: ButtonVariant, size: ButtonSize) => {
  const baseClasses = 'whitespace-nowrap focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 disabled:pointer-events-none disabled:opacity-50'
  
  const variantClasses = {
    default: 'bg-primary text-white hover:bg-primary-600',
    destructive: 'bg-danger text-white hover:bg-danger/90',
    outline: 'border border-border bg-surface hover:bg-surface-2 text-text',
    secondary: 'bg-surface-2 text-text hover:bg-surface',
    ghost: 'hover:bg-surface-2 text-text',
    link: 'text-link underline-offset-4 hover:underline',
  }
  
  const sizeClasses = {
    default: 'btn-md', // Use SAPTIVA token (44px height, 16px padding, 1rem font)
    sm: 'btn-sm',      // Use SAPTIVA token (36px height, 12px padding, 0.875rem font)
    lg: 'btn-lg',      // Use SAPTIVA token (52px height, 20px padding, 1.125rem font)
    icon: 'h-10 w-10',
  }
  
  return `${baseClasses} ${variantClasses[variant]} ${sizeClasses[size]}`
}

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
  leftIcon?: React.ReactNode
  rightIcon?: React.ReactNode
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'default', size = 'default', loading, leftIcon, rightIcon, children, disabled, ...props }, ref) => {
    const isDisabled = disabled || loading

    return (
      <button
        className={cn(getButtonClasses(variant, size), className)}
        ref={ref}
        disabled={isDisabled}
        {...props}
      >
        {loading ? (
          <>
            <svg
              className="mr-2 h-4 w-4 animate-spin"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
            Loading...
          </>
        ) : (
          <>
            {leftIcon && <span className="mr-2">{leftIcon}</span>}
            {children}
            {rightIcon && <span className="ml-2">{rightIcon}</span>}
          </>
        )}
      </button>
    )
  }
)

Button.displayName = 'Button'

export { Button }