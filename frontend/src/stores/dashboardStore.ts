import { create } from 'zustand';
import type { DashboardMetrics, ActivityFeedItem } from '@/types';

interface DashboardStore {
  metrics: DashboardMetrics | null;
  activityFeed: ActivityFeedItem[];
  loading: boolean;
  error: string | null;
  
  setMetrics: (metrics: DashboardMetrics) => void;
  setActivityFeed: (items: ActivityFeedItem[]) => void;
  addActivityItem: (item: ActivityFeedItem) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
}

export const useDashboardStore = create<DashboardStore>((set) => ({
  metrics: null,
  activityFeed: [],
  loading: false,
  error: null,

  setMetrics: (metrics) => set({ metrics }),
  setActivityFeed: (activityFeed) => set({ activityFeed }),
  addActivityItem: (item) => set((state) => ({
    activityFeed: [item, ...state.activityFeed].slice(0, 50),
  })),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
}));