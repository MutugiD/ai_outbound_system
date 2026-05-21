import React from 'react';
import clsx from 'clsx';

interface BadgeProps {
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info';
  size?: 'sm' | 'md';
  dot?: boolean;
  children: React.ReactNode;
  className?: string;
}

const variantStyles: Record<string, string> = {
  default: 'bg-navy-700/50 text-navy-200 border-navy-600/30',
  success: 'bg-emerald-900/50 text-emerald-300 border-emerald-700/30',
  warning: 'bg-gold-900/50 text-gold-300 border-gold-700/30',
  danger: 'bg-coral-900/50 text-coral-300 border-coral-700/30',
  info: 'bg-navy-700/50 text-gold-300 border-navy-600/30',
};

const dotStyles: Record<string, string> = {
  default: 'bg-navy-400',
  success: 'bg-emerald-400',
  warning: 'bg-gold-400',
  danger: 'bg-coral-400',
  info: 'bg-gold-400',
};

export function Badge({ variant = 'default', size = 'sm', dot = false, children, className }: BadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full border font-medium',
        variantStyles[variant],
        size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm',
        className
      )}
    >
      {dot && <span className={clsx('status-dot', dotStyles[variant])} />}
      {children}
    </span>
  );
}