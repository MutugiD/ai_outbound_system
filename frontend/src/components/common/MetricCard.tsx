import React from 'react';
import clsx from 'clsx';

interface MetricCardProps {
  label: string;
  value: string | number;
  change?: number;
  changeLabel?: string;
  icon: React.ReactNode;
  accent?: 'gold' | 'emerald' | 'coral' | 'navy';
  className?: string;
  onClick?: () => void;
}

const accentStyles: Record<string, { bg: string; border: string; icon: string; glow: string; change: { positive: string; negative: string } }> = {
  gold: {
    bg: 'bg-gold-500/10',
    border: 'border-gold-700/30',
    icon: 'text-gold-400',
    glow: 'shadow-gold-500/5',
    change: { positive: 'text-emerald-400', negative: 'text-coral-400' },
  },
  emerald: {
    bg: 'bg-emerald-500/10',
    border: 'border-emerald-700/30',
    icon: 'text-emerald-400',
    glow: 'shadow-emerald-500/5',
    change: { positive: 'text-emerald-400', negative: 'text-coral-400' },
  },
  coral: {
    bg: 'bg-coral-500/10',
    border: 'border-coral-700/30',
    icon: 'text-coral-400',
    glow: 'shadow-coral-500/5',
    change: { positive: 'text-emerald-400', negative: 'text-coral-400' },
  },
  navy: {
    bg: 'bg-navy-700/30',
    border: 'border-navy-600/30',
    icon: 'text-navy-300',
    glow: '',
    change: { positive: 'text-emerald-400', negative: 'text-coral-400' },
  },
};

export function MetricCard({ label, value, change, changeLabel, icon, accent = 'gold', className, onClick }: MetricCardProps) {
  const styles = accentStyles[accent];
  const isPositive = change !== undefined && change >= 0;

  return (
    <div
      onClick={onClick}
      className={clsx(
        'rounded-2xl border p-6 transition-all duration-200',
        styles.bg,
        styles.border,
        styles.glow,
        onClick && 'cursor-pointer hover:scale-[1.02] hover:shadow-lg active:scale-[0.98]',
        className
      )}
    >
      <div className="flex items-center justify-between mb-4">
        <span className="text-sm font-medium text-navy-300 uppercase tracking-wider">{label}</span>
        <div className={clsx('p-2.5 rounded-xl', styles.bg, styles.icon)}>
          {icon}
        </div>
      </div>
      <div className="text-4xl font-display font-bold text-navy-50 mb-1">{value}</div>
      {change !== undefined && (
        <div className="flex items-center gap-1.5 text-sm mt-2">
          <span className={clsx(
            'inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md text-xs font-semibold',
            isPositive ? 'bg-emerald-500/15 text-emerald-400' : 'bg-coral-500/15 text-coral-400'
          )}>
            {isPositive ? '↑' : '↓'} {Math.abs(change).toFixed(1)}%
          </span>
          {changeLabel && <span className="text-navy-400">{changeLabel}</span>}
        </div>
      )}
    </div>
  );
}

interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className }: SkeletonProps) {
  return (
    <div className={clsx('animate-pulse rounded-lg bg-navy-700/50', className)} />
  );
}

export function MetricCardSkeleton() {
  return (
    <div className="glass-card p-6">
      <div className="flex items-start justify-between mb-4">
        <Skeleton className="h-4 w-28" />
        <Skeleton className="h-10 w-10 rounded-xl" />
      </div>
      <Skeleton className="h-10 w-24 mb-2" />
      <Skeleton className="h-3 w-36" />
    </div>
  );
}