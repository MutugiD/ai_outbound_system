import React, { useEffect, useState, useCallback } from 'react';
import { SimpleBarChart, DonutChart, ConversionFunnel } from '@/components/analytics';
import { Card, MetricCard, MetricCardSkeleton } from '@/components/common';
import { TrendingUp, MessageSquare, Users, Target, CalendarCheck, DollarSign, AlertCircle, RefreshCw } from 'lucide-react';
import { api } from '@/services/api';
import type { OverviewStats, PipelineAnalyticsResponse, ChannelAnalyticsResponse, CampaignAnalyticsResponse, SourceAnalyticsResponse, ScoreDistributionResponse } from '@/services/api';

// Color palette for donut/funnel segments
const STAGE_COLORS = [
  '#829ab1', // slate
  '#fbbf24', // gold
  '#68d391', // emerald
  '#f59e0b', // amber
  '#d97706', // orange
  '#38a169', // green
  '#e53e3e', // red
  '#805ad5', // purple
];

export default function AnalyticsPage() {
  const [overview, setOverview] = useState<OverviewStats | null>(null);
  const [pipeline, setPipeline] = useState<PipelineAnalyticsResponse | null>(null);
  const [channels, setChannels] = useState<ChannelAnalyticsResponse | null>(null);
  const [campaigns, setCampaigns] = useState<CampaignAnalyticsResponse | null>(null);
  const [sources, setSources] = useState<SourceAnalyticsResponse | null>(null);
  const [scores, setScores] = useState<ScoreDistributionResponse | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [overviewData, pipelineData, channelsData, campaignsData, sourcesData, scoresData] = await Promise.all([
        api.analytics.overview(),
        api.analytics.pipeline(),
        api.analytics.channels(),
        api.analytics.campaigns(),
        api.analytics.sources(),
        api.analytics.scores(),
      ]);
      setOverview(overviewData);
      setPipeline(pipelineData);
      setChannels(channelsData);
      setCampaigns(campaignsData);
      setSources(sourcesData);
      setScores(scoresData);
    } catch (err: any) {
      setError(err?.message || 'Failed to load analytics data. Please try again.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Helper to format large numbers compactly
  const formatValue = (val: number): string => {
    if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(1)}M`;
    if (val >= 1_000) return val >= 10_000 ? `$${(val / 1_000).toFixed(0)}K` : `$${(val / 1_000).toFixed(1)}K`;
    return val.toLocaleString();
  };

  // Transform pipeline data for DonutChart
  const pipelineDonutSegments = pipeline
    ? pipeline.stages.map((s, i) => ({
        label: s.stage,
        value: s.count,
        color: STAGE_COLORS[i % STAGE_COLORS.length],
      }))
    : [];

  // Transform pipeline data for ConversionFunnel
  const conversionFunnelStages = pipeline
    ? pipeline.stages.map((s, i) => ({
        label: s.stage,
        value: s.count,
        color: STAGE_COLORS[i % STAGE_COLORS.length],
      }))
    : [];

  // Transform channels data for SimpleBarChart
  const channelChartData = channels
    ? channels.channels.map((c) => ({ label: c.channel, value: c.messages }))
    : [];

  // Transform sources data for SimpleBarChart
  const sourceChartData = sources
    ? sources.sources.map((s) => ({ label: s.source, value: s.leads }))
    : [];

  // Transform scores data for SimpleBarChart
  const scoreChartData = scores
    ? scores.distribution.map((s) => ({ label: s.score_band, value: s.count }))
    : [];

  // Error state
  if (error && !loading) {
    return (
      <div className="space-y-6 animate-fade-in">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="font-display text-2xl font-bold text-navy-50">Analytics</h1>
            <p className="text-sm text-navy-400 mt-1">Performance insights and conversion metrics</p>
          </div>
        </div>
        <Card className="p-8 text-center">
          <AlertCircle className="mx-auto mb-3 text-coral-400" size={32} />
          <p className="text-navy-200 mb-4">{error}</p>
          <button
            onClick={fetchData}
            className="inline-flex items-center gap-2 px-4 py-2 bg-gold-500 text-navy-950 rounded-lg text-sm font-medium hover:bg-gold-400 transition-colors"
          >
            <RefreshCw size={14} />
            Retry
          </button>
        </Card>
      </div>
    );
  }

  // Loading skeleton
  if (loading) {
    return (
      <div className="space-y-6 animate-fade-in">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="font-display text-2xl font-bold text-navy-50">Analytics</h1>
            <p className="text-sm text-navy-400 mt-1">Performance insights and conversion metrics</p>
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => <MetricCardSkeleton key={i} />)}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="rounded-2xl border border-navy-700/30 bg-navy-900/80 p-6 h-64 animate-pulse" />
          <div className="rounded-2xl border border-navy-700/30 bg-navy-900/80 p-6 h-64 animate-pulse" />
        </div>
        <div className="rounded-2xl border border-navy-700/30 bg-navy-900/80 p-6 h-48 animate-pulse" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="rounded-2xl border border-navy-700/30 bg-navy-900/80 p-6 h-48 animate-pulse" />
          <div className="rounded-2xl border border-navy-700/30 bg-navy-900/80 p-6 h-48 animate-pulse" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-navy-50">Analytics</h1>
          <p className="text-sm text-navy-400 mt-1">Performance insights and conversion metrics</p>
        </div>
        <button
          onClick={fetchData}
          className="p-2 text-navy-400 hover:text-navy-200 transition-colors"
          title="Refresh data"
        >
          <RefreshCw size={16} />
        </button>
      </div>

      {/* High-level KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <MetricCard
          label="Total Leads"
          value={overview ? overview.total_leads.toLocaleString() : '—'}
          icon={<Users size={18} />}
          accent="gold"
        />
        <MetricCard
          label="Messages Sent"
          value={overview ? overview.messages_sent.toLocaleString() : '—'}
          icon={<MessageSquare size={18} />}
          accent="gold"
        />
        <MetricCard
          label="Reply Rate"
          value={overview ? `${(overview.reply_rate * 100).toFixed(1)}%` : '—'}
          icon={<Target size={18} />}
          accent="emerald"
        />
        <MetricCard
          label="Booked Calls"
          value={overview ? overview.booked_calls.toLocaleString() : '—'}
          icon={<CalendarCheck size={18} />}
          accent="gold"
        />
        <MetricCard
          label="Pipeline Value"
          value={overview ? formatValue(overview.pipeline_value) : '—'}
          icon={<DollarSign size={18} />}
          accent="gold"
        />
        <MetricCard
          label="Conversion Rate"
          value={overview ? `${(overview.conversion_rate * 100).toFixed(1)}%` : '—'}
          icon={<TrendingUp size={18} />}
          accent="emerald"
        />
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Channel Performance */}
        {channelChartData.length > 0 && (
          <SimpleBarChart
            title="Channel Performance"
            data={channelChartData}
            color="#fbbf24"
          />
        )}

        {/* Lead Pipeline Donut */}
        {pipelineDonutSegments.length > 0 && (
          <DonutChart
            title="Lead Pipeline Distribution"
            segments={pipelineDonutSegments}
          />
        )}
      </div>

      {/* Conversion Funnel */}
      {conversionFunnelStages.length > 0 && (
        <ConversionFunnel
          title="Conversion Funnel"
          stages={conversionFunnelStages}
        />
      )}

      {/* Secondary Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Lead Sources */}
        {sourceChartData.length > 0 && (
          <SimpleBarChart
            title="Lead Sources"
            data={sourceChartData}
            color="#68d391"
          />
        )}

        {/* Score Distribution */}
        {scoreChartData.length > 0 && (
          <SimpleBarChart
            title="Score Distribution"
            data={scoreChartData}
            color="#fbbf24"
          />
        )}
      </div>
    </div>
  );
}