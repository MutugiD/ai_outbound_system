import React from 'react';
import clsx from 'clsx';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
  icon?: React.ReactNode;
}

export function Input({ label, error, hint, icon, className, id, ...props }: InputProps) {
  const inputId = id || label?.toLowerCase().replace(/\s+/g, '-');
  return (
    <div className="w-full">
      {label && (
        <label htmlFor={inputId} className="block text-sm font-medium text-navy-200 mb-1.5">
          {label}
        </label>
      )}
      <div className="relative">
        {icon && (
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-navy-400">
            {icon}
          </div>
        )}
        <input
          id={inputId}
          className={clsx(
            'w-full rounded-lg bg-navy-800 border border-navy-600/40 text-navy-50 placeholder-navy-400',
            'focus:outline-none focus:ring-2 focus:ring-gold-500/50 focus:border-gold-500/50',
            'transition-all duration-200',
            icon ? 'pl-10' : 'pl-3',
            'pr-3 py-2 text-sm',
            error && 'border-coral-500/50 focus:ring-coral-500/50 focus:border-coral-500/50',
            className
          )}
          {...props}
        />
      </div>
      {error && <p className="mt-1 text-xs text-coral-400">{error}</p>}
      {hint && !error && <p className="mt-1 text-xs text-navy-400">{hint}</p>}
    </div>
  );
}

interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  hint?: string;
}

export function Textarea({ label, error, hint, className, id, ...props }: TextareaProps) {
  const inputId = id || label?.toLowerCase().replace(/\s+/g, '-');
  return (
    <div className="w-full">
      {label && (
        <label htmlFor={inputId} className="block text-sm font-medium text-navy-200 mb-1.5">
          {label}
        </label>
      )}
      <textarea
        id={inputId}
        className={clsx(
          'w-full rounded-lg bg-navy-800 border border-navy-600/40 text-navy-50 placeholder-navy-400',
          'focus:outline-none focus:ring-2 focus:ring-gold-500/50 focus:border-gold-500/50',
          'transition-all duration-200 px-3 py-2 text-sm min-h-[100px] resize-y',
          error && 'border-coral-500/50 focus:ring-coral-500/50',
          className
        )}
        {...props}
      />
      {error && <p className="mt-1 text-xs text-coral-400">{error}</p>}
      {hint && !error && <p className="mt-1 text-xs text-navy-400">{hint}</p>}
    </div>
  );
}

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  options: { value: string; label: string }[];
}

export function Select({ label, error, options, className, id, ...props }: SelectProps) {
  const inputId = id || label?.toLowerCase().replace(/\s+/g, '-');
  return (
    <div className="w-full">
      {label && (
        <label htmlFor={inputId} className="block text-sm font-medium text-navy-200 mb-1.5">
          {label}
        </label>
      )}
      <select
        id={inputId}
        className={clsx(
          'w-full rounded-lg bg-navy-800 border border-navy-600/40 text-navy-50',
          'focus:outline-none focus:ring-2 focus:ring-gold-500/50 focus:border-gold-500/50',
          'transition-all duration-200 px-3 py-2 text-sm',
          error && 'border-coral-500/50',
          className
        )}
        {...props}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>
      {error && <p className="mt-1 text-xs text-coral-400">{error}</p>}
    </div>
  );
}