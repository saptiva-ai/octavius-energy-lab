'use client'

import * as React from 'react'
import { cn } from '../../lib/utils'

type BadgeVariant = 'default' | 'secondary' | 'success' | 'warning' | 'error' | 'info'
type BadgeSize = 'sm' | 'md' | 'lg'

const getBadgeClasses = (variant: BadgeVariant, size: BadgeSize) => {
  const baseClasses = 'inline-flex items-center font-medium rounded-full border'
  
  const variantClasses = {
    default: 'bg-gray-100 text-gray-800 border-gray-200',
    secondary: 'bg-gray-50 text-gray-600 border-gray-200',
    success: 'bg-green-100 text-green-800 border-green-200',
    warning: 'bg-yellow-100 text-yellow-800 border-yellow-200',
    error: 'bg-red-100 text-red-800 border-red-200',
    info: 'bg-blue-100 text-blue-800 border-blue-200',
  }
  
  const sizeClasses = {
    sm: 'px-2 py-1 text-xs',
    md: 'px-2.5 py-1.5 text-sm',
    lg: 'px-3 py-2 text-base',
  }
  
  return `${baseClasses} ${variantClasses[variant]} ${sizeClasses[size]}`
}

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant
  size?: BadgeSize
  icon?: React.ReactNode
}

const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant = 'default', size = 'md', icon, children, ...props }, ref) => {
    return (
      <span
        className={cn(getBadgeClasses(variant, size), className)}
        ref={ref}
        {...props}
      >
        {icon && <span className="mr-1">{icon}</span>}
        {children}
      </span>
    )
  }
)

Badge.displayName = 'Badge'

export { Badge }