import React from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { ToastContainer } from '@/components/common';
import { useUIStore } from '@/stores';

export function AppLayout() {
  const { sidebarCollapsed } = useUIStore();

  return (
    <div className="min-h-screen bg-navy-950">
      <Sidebar />
      <div
        className="transition-all duration-300"
        style={{ marginLeft: sidebarCollapsed ? 68 : 240 }}
      >
        <TopBar />
        <main className="p-6 lg:p-8 max-w-[1600px] mx-auto">
          <Outlet />
        </main>
      </div>
      <ToastContainer />
    </div>
  );
}