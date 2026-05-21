import React from 'react';
import { Search, Bell, User, ChevronDown } from 'lucide-react';
import { useUIStore } from '@/stores';
import { Input } from '@/components/common';

export function TopBar() {
  const { addNotification } = useUIStore();

  return (
    <header className="h-14 flex items-center justify-between px-6 border-b border-navy-700/30 bg-navy-900/50 backdrop-blur-sm sticky top-0 z-30">
      <div className="flex items-center gap-4 flex-1 max-w-md">
        <Search size={18} className="text-navy-400 flex-shrink-0" />
        <input
          type="text"
          placeholder="Search campaigns, leads, agents..."
          className="w-full bg-transparent text-sm text-navy-200 placeholder-navy-500 focus:outline-none border-none"
        />
      </div>

      <div className="flex items-center gap-3">
        {/* Notifications */}
        <button
          onClick={() => addNotification({ type: 'info', message: 'No new notifications' })}
          className="relative p-2 rounded-lg text-navy-400 hover:text-navy-200 hover:bg-navy-800/50 transition-colors"
        >
          <Bell size={18} />
          <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-gold-500" />
        </button>

        {/* User menu */}
        <div className="flex items-center gap-2 pl-3 border-l border-navy-700/30">
          <div className="w-8 h-8 rounded-lg bg-navy-700 flex items-center justify-center text-gold-400">
            <User size={16} />
          </div>
          <div className="hidden sm:block">
            <p className="text-sm font-medium text-navy-100">Admin</p>
            <p className="text-xs text-navy-400">admin@company.com</p>
          </div>
          <ChevronDown size={14} className="text-navy-400" />
        </div>
      </div>
    </header>
  );
}