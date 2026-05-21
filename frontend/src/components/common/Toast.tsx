import React from 'react';
import clsx from 'clsx';
import { CheckCircle, AlertCircle, AlertTriangle, Info, X } from 'lucide-react';
import { useUIStore } from '@/stores';

const iconMap = {
  success: CheckCircle,
  error: AlertCircle,
  warning: AlertTriangle,
  info: Info,
};

const styleMap = {
  success: 'border-emerald-700/30 bg-emerald-900/20 text-emerald-300',
  error: 'border-coral-700/30 bg-coral-900/20 text-coral-300',
  warning: 'border-gold-700/30 bg-gold-900/20 text-gold-300',
  info: 'border-navy-600/30 bg-navy-800/30 text-navy-200',
};

export function ToastContainer() {
  const { notifications, removeNotification } = useUIStore();

  if (notifications.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
      {notifications.map((n) => {
        const Icon = iconMap[n.type];
        return (
          <div
            key={n.id}
            className={clsx(
              'flex items-start gap-3 p-3 rounded-lg border animate-slide-in-right',
              styleMap[n.type]
            )}
          >
            <Icon size={18} className="flex-shrink-0 mt-0.5" />
            <p className="text-sm flex-1">{n.message}</p>
            <button
              onClick={() => removeNotification(n.id)}
              className="flex-shrink-0 p-0.5 hover:opacity-70"
            >
              <X size={14} />
            </button>
          </div>
        );
      })}
    </div>
  );
}