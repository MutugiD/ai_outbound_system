import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { DashboardMetricsRow, QuickStatsGrid, ActivityFeed, MiniChart, demoChartData } from '@/components/dashboard';
import { Card, CardHeader, CardTitle } from '@/components/common';
import { useDashboardStore } from '@/stores';
import { api } from '@/services';
import type { DashboardMetrics, ActivityFeedItem } from '@/types';
import { ArrowRight, BarChart3, Activity } from 'lucide-react';

// Demo data for initial display
const demoMetrics: DashboardMetrics = {
  total_campaigns: 15,
  active_campaigns: 4,
  total_leads: 299,
  messages_sent_today: 234,
  responses_today: 31,
  meetings_today: 3,
  conversion_rate: 0.124,
  reply_rate: 0.132,
};

const demoActivity: ActivityFeedItem[] = [
  { id: '1', type: 'meeting_booked', description: 'Meeting booked with Sarah Kim at Acme Corp', timestamp: new Date().toISOString(), metadata: { agent: 'SDR Agent 1' } },
  { id: '2', type: 'reply_received', description: 'Reply from John Martinez at Techflow - interested in demo', timestamp: new Date(Date.now() - 3600000).toISOString() },
  { id: '3', type: 'message_sent', description: '50 personalized emails sent via Enterprise Outreach campaign', timestamp: new Date(Date.now() - 7200000).toISOString() },
  { id: '4', type: 'deal_closed', description: 'Deal closed! $45K ARR with CloudScale Systems', timestamp: new Date(Date.now() - 14400000).toISOString() },
  { id: '5', type: 'lead_added', description: '23 new leads imported from LinkedIn Sales Navigator', timestamp: new Date(Date.now() - 21600000).toISOString() },
  { id: '6', type: 'campaign_started', description: 'Q2 SaaS Outreach campaign started', timestamp: new Date(Date.now() - 28800000).toISOString() },
  { id: '7', type: 'reply_received', description: 'Reply from Lisa Wang at DataSync - requesting pricing', timestamp: new Date(Date.now() - 36000000).toISOString() },
  { id: '8', type: 'meeting_booked', description: 'Meeting booked with David Chen at NextGen AI', timestamp: new Date(Date.now() - 43200000).toISOString() },
];

export default function DashboardPage() {
  const { setMetrics, setActivityFeed, metrics } = useDashboardStore();
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    const loadData = async () => {
      try {
        const [metricsData, activityData] = await Promise.all([
          api.getDashboardMetrics(),
          api.getActivityFeed(),
        ]);
        setMetrics(metricsData);
        setActivityFeed(activityData);
      } catch {
        setMetrics(demoMetrics);
        setActivityFeed(demoActivity);
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
        <QuickStatsGrid />
      </section>

      {/* Charts section */}
      <section>
        <div className="flex items-center gap-2 mb-4">
          <BarChart3 size={18} className="text-gold-400" />
          <h2 className="font-display text-lg font-semibold text-navy-50">Trends (7d)</h2>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <MiniChart
            title="Messages Sent"
            data={demoChartData.messages}
            color="#fbbf24"
            change={9.7}
          />
          <MiniChart
            title="Replies Received"
            data={demoChartData.replies}
            color="#68d391"
            change={12.9}
          />
          <MiniChart
            title="Conversion Rate"
            data={demoChartData.conversion}
            color="#fbbf24"
            change={1.4}
            format="percent"
          />
          <MiniChart
            title="Meetings Booked"
            data={demoChartData.meetings}
            color="#68d391"
            change={50}
          />
        </div>
      </section>

      {/* Activity Feed — full width */}
      <section>
        <div className="flex items-center gap-2 mb-4">
          <Activity size={18} className="text-emerald-400" />
          <h2 className="font-display text-lg font-semibold text-navy-50">Recent Activity</h2>
        </div>
        <ActivityFeed items={demoActivity} loading={loading} />
      </section>
    </div>
  );
}