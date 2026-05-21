import React from 'react';
import clsx from 'clsx';

interface CardProps {
  variant?: 'default' | 'glass' | 'bordered';
  hover?: boolean;
  padding?: 'none' | 'sm' | 'md' | 'lg';
  className?: string;
  children: React.ReactNode;
  onClick?: () => void;
}

const variantStyles: Record<string, string> = {
  default: 'bg-navy-900/80 border border-navy-700/30',
  glass: 'glass-card',
  bordered: 'bg-navy-900/60 border border-navy-600/40',
};

const paddingStyles: Record<string, string> = {
  none: '',
  sm: 'p-3',
  md: 'p-5',
  lg: 'p-8',
};

export function Card({ variant = 'default', hover = false, padding = 'md', className, children, onClick }: CardProps) {
  return (
    <div
      className={clsx(
        'rounded-xl transition-all duration-200',
        variantStyles[variant],
        paddingStyles[padding],
        hover && 'glass-card-hover cursor-pointer hover:shadow-lg hover:shadow-navy-950/50',
        className
      )}
      onClick={onClick}
    >
      {children}
    </div>
  );
}

export function CardHeader({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div className={clsx('flex items-center justify-between mb-4', className)}>
      {children}
    </div>
  );
}

export function CardTitle({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <h3 className={clsx('font-display text-lg font-semibold text-navy-50', className)}>
      {children}
    </h3>
  );
}