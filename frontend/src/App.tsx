import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AppLayout } from '@/components/layout';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import DashboardPage from '@/pages/DashboardPage';
import CampaignsPage from '@/pages/CampaignsPage';
import LeadsPage from '@/pages/LeadsPage';
import AgentsPage from '@/pages/AgentsPage';
import AnalyticsPage from '@/pages/AnalyticsPage';
import SettingsPage from '@/pages/SettingsPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30000,
      retry: 1,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/campaigns" element={<CampaignsPage />} />
            <Route path="/leads" element={<LeadsPage />} />
            <Route path="/agents" element={<AgentsPage />} />
            <Route path="/analytics" element={<AnalyticsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}