import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import clsx from 'clsx';
import {
  LayoutDashboard,
  Megaphone,
  Users,
  Bot,
  BarChart3,
  Settings,
  Zap,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { useUIStore } from '@/stores';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/campaigns', icon: Megaphone, label: 'Campaigns' },
  { to: '/leads', icon: Users, label: 'Leads' },
  { to: '/agents', icon: Bot, label: 'Agents' },
  { to: '/analytics', icon: BarChart3, label: 'Analytics' },
  { to: '/settings', icon: Settings, label: 'Settings' },
];

export function Sidebar() {
  const { sidebarCollapsed, toggleSidebarCollapse } = useUIStore();
  const location = useLocation();

  return (
    <aside
      className={clsx(
        'fixed left-0 top-0 h-full z-40 flex flex-col transition-all duration-300',
        'bg-navy-900/95 border-r border-navy-700/30 backdrop-blur-xl',
        sidebarCollapsed ? 'w-[68px]' : 'w-[240px]'
      )}
    >
      {/* Logo */}
      <div className={clsx(
        'flex items-center gap-3 px-4 py-5 border-b border-navy-700/30',
        sidebarCollapsed && 'justify-center px-2'
      )}>
        <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-gold-500 text-navy-950 flex-shrink-0">
          <Zap size={20} strokeWidth={2.5} />
        </div>
        {!sidebarCollapsed && (
          <div className="overflow-hidden">
            <h1 className="font-display font-bold text-navy-50 text-sm leading-tight">AI Outbound</h1>
            <p className="text-[10px] text-gold-400 font-medium tracking-wider uppercase">Operating System</p>
          </div>
        )}
      </div>

      {/* Nav Items */}
      <nav className="flex-1 py-4 px-2 space-y-1 overflow-y-auto">
        {navItems.map(({ to, icon: Icon, label }) => {
          const isActive = to === '/' ? location.pathname === '/' : location.pathname.startsWith(to);
          return (
            <NavLink
              key={to}
              to={to}
              className={clsx(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200',
                sidebarCollapsed && 'justify-center px-2',
                isActive
                  ? 'bg-gold-500/10 text-gold-400 border border-gold-500/20'
                  : 'text-navy-300 hover:text-navy-100 hover:bg-navy-800/50'
              )}
              title={sidebarCollapsed ? label : undefined}
            >
              <Icon size={20} className="flex-shrink-0" />
              {!sidebarCollapsed && <span>{label}</span>}
            </NavLink>
          );
        })}
      </nav>

      {/* Collapse Toggle */}
      <div className="px-2 py-3 border-t border-navy-700/30">
        <button
          onClick={toggleSidebarCollapse}
          className="flex items-center justify-center w-full py-2 rounded-lg text-navy-400 hover:text-navy-200 hover:bg-navy-800/50 transition-colors"
        >
          {sidebarCollapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
          {!sidebarCollapsed && <span className="ml-2 text-sm">Collapse</span>}
        </button>
      </div>
    </aside>
  );
}