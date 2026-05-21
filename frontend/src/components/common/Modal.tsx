import React from 'react';
import clsx from 'clsx';
import { X } from 'lucide-react';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  children: React.ReactNode;
}

const sizeStyles: Record<string, string> = {
  sm: 'max-w-md',
  md: 'max-w-lg',
  lg: 'max-w-2xl',
  xl: 'max-w-4xl',
};

export function Modal({ isOpen, onClose, title, size = 'md', children }: ModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-navy-950/80 backdrop-blur-sm"
        onClick={onClose}
      />
      <div
        className={clsx(
          'relative w-full mx-4 glass-card p-0 animate-fade-in',
          sizeStyles[size]
        )}
      >
        <div className="flex items-center justify-between p-5 border-b border-navy-700/30">
          <h2 className="font-display text-lg font-semibold text-navy-50">{title}</h2>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-navy-400 hover:text-navy-200 hover:bg-navy-800 transition-colors"
          >
            <X size={18} />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}