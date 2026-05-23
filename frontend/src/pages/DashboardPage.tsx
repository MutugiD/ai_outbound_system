import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { DashboardMetricsRow, QuickStatsGrid, ActivityFeed, MiniChart } from '@/components/dashboard';
import { useDashboardStore } from '@/stores';
import { api } from '@/services';
import type { DashboardMetrics, ActivityFeedItem } from '@/types';
import { ArrowRight, BarChart3, Activity } from 'lucide-react';

interface PipelineStageData {
  stage: string;
  count: number;
}

export default function DashboardPage() {
  const { setMetrics, setActivityFeed, metrics, activityFeed } = useDashboardStore();
  const [loading, setLoading] = useState(true);
  const [pipelineStages, setPipelineStages] = useState<PipelineStageData[]>([]);
  const navigate = useNavigate();

  useEffect(() => {
    const loadData = async () => {
      try {
        const [overviewData, activityData] = await Promise.all([
          api.analytics.overview(),
          api.getActivityFeed(),
        ]);

        // Map backend overview to dashboard metrics
        const dashboardMetrics: DashboardMetrics = {
          ...overviewData,
          total_campaigns: 0,
          active_campaigns: 0,
          messages_sent_today: overviewData.messages_sent,
          responses_today: overviewData.interested_replies,
          meetings_today: overviewData.booked_calls,
        };
        setMetrics(dashboardMetrics);
        setActivityFeed(activityData as ActivityFeedItem[]);

        // Fetch pipeline data
        const pipelineData = await api.analytics.pipeline();
        setPipelineStages(pipelineData.stages || []);
      } catch (err) {
        console.error('Failed to load dashboard data:', err);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, [setMetrics, setActivityFeed]);

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Hero header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-3xl font-bold text-navy-50 tracking-tight">Dashboard</h1>
          <p className="text-sm text-navy-400 mt-1">Your AI outbound operations at a glance</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-xs text-navy-400 bg-navy-900/60 px-3 py-1.5 rounded-full border border-navy-700/40">
            <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            Live
          </div>
          <button
            onClick={() => navigate('/campaigns')}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gold-500 text-navy-950 text-sm font-semibold hover:bg-gold-400 transition-colors"
          >
            View Campaigns
            <ArrowRight size={14} />
          </button>
        </div>
      </div>

      {/* Top-level KPI metrics */}
      <section>
        <DashboardMetricsRow metrics={metrics} loading={loading} />
      </section>

      {/* Pipeline stats with progress bars */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-display text-lg font-semibold text-navy-50">Pipeline Overview</h2>
          <button
            onClick={() => navigate('/leads')}
            className="text-sm text-navy-400 hover:text-gold-400 transition-colors flex items-center gap-1"
          >
            View leads <ArrowRight size={12} />
          </button>
        </div>
        <QuickStatsGrid metrics={metrics} pipelineStages={pipelineStages} loading={loading} />
      </section>

      {/* Charts section — show pipeline stage counts as bar values */}
      {pipelineStages.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-4">
            <BarChart3 size={18} className="text-gold-400" />
            <h2 className="font-display text-lg font-semibold text-navy-50">Pipeline Distribution</h2>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {pipelineStages.slice(0, 4).map((stage, idx) => {
              const colors = ['#fbbf24', '#68d391', '#fbbf24', '#68d391'];
              return (
                <MiniChart
                  key={stage.stage}
                  title={stage.stage.charAt(0).toUpperCase() + stage.stage.slice(1).replace('_', ' ')}
                  data={[{ date: 'now', value: stage.count }]}
                  color={colors[idx % colors.length]}
                />
              );
            })}
          </div>
        </section>
      )}

      {/* Activity Feed — full width */}
      <section>
        <div className="flex items-center gap-2 mb-4">
          <Activity size={18} className="text-emerald-400" />
          <h2 className="font-display text-lg font-semibold text-navy-50">Recent Activity</h2>
        </div>
        <ActivityFeed items={activityFeed} loading={loading} />
      </section>
    </div>
  );
}