import React, { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardHeader, CardTitle } from '@/components/common';
import { Megaphone, Users, MessageSquare, Target, ArrowRight } from 'lucide-react';
import type { DashboardMetrics } from '@/types';

interface PipelineStageData {
  stage: string;
  count: number;
}

interface QuickStatsGridProps {
  metrics: DashboardMetrics | null;
  pipelineStages?: PipelineStageData[];
  loading?: boolean;
}

export function QuickStatsGrid({ metrics, pipelineStages = [], loading }: QuickStatsGridProps) {
  const navigate = useNavigate();

  // Derive pipeline data
  const stageMap = useMemo(() => {
    const map: Record<string, number> = {};
    for (const s of pipelineStages) {
      map[s.stage] = s.count;
    }
    return map;
  }, [pipelineStages]);

  const totalLeads = metrics?.total_leads ?? 0;
  const newLeads = stageMap['new'] ?? metrics?.new_leads_today ?? 0;
  const contacted = stageMap['contacted'] ?? 0;
  const qualified = stageMap['qualified'] ?? 0;
  const messagesSent = metrics?.messages_sent ?? 0;
  const conversionRate = metrics?.conversion_rate ?? 0;
  const bookedCalls = metrics?.booked_calls ?? 0;

  if (loading || !metrics) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <Card key={i}>
            <div className="animate-pulse space-y-3">
              <div className="h-3 w-20 rounded bg-navy-700/50" />
              <div className="h-8 w-16 rounded bg-navy-700/50" />
              <div className="h-2 w-24 rounded bg-navy-700/50" />
            </div>
          </Card>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
      <QuickStatCard
        title="Active Campaigns"
        value={metrics.active_campaigns ?? 0}
        subtitle={`${metrics.new_leads_today ?? 0} new leads today`}
        icon={<Megaphone size={20} />}
        color="gold"
        barSegments={[
          { value: metrics.active_campaigns ?? 0, color: 'bg-gold-400', label: 'Active' },
          ...(pipelineStages.length > 0 ? [{ value: Math.max(1, Math.round(totalLeads / 50)), color: 'bg-navy-500', label: 'Running' }] : []),
        ]}
        onClick={() => navigate('/campaigns')}
      />
      <QuickStatCard
        title="Total Leads"
        value={totalLeads}
        subtitle={`${contacted} contacted`}
        icon={<Users size={20} />}
        color="emerald"
        barSegments={[
          { value: newLeads, color: 'bg-navy-400', label: 'New' },
          { value: contacted, color: 'bg-gold-400', label: 'Contacted' },
          { value: qualified, color: 'bg-emerald-400', label: 'Qualified' },
        ]}
        onClick={() => navigate('/leads')}
      />
      <QuickStatCard
        title="Messages Sent"
        value={messagesSent}
        subtitle={`${metrics.interested_replies ?? 0} interested replies`}
        icon={<MessageSquare size={20} />}
        color="gold"
        barSegments={[
          { value: Math.round(messagesSent * (metrics.reply_rate || 0.13)), color: 'bg-gold-400', label: 'Sent' },
          { value: Math.round(messagesSent * (metrics.reply_rate || 0.05)), color: 'bg-emerald-400', label: 'Replied' },
        ]}
        onClick={() => navigate('/campaigns')}
      />
      <QuickStatCard
        title="Conversion Rate"
        value={`${(conversionRate * 100).toFixed(1)}%`}
        subtitle={`${bookedCalls} calls booked`}
        icon={<Target size={20} />}
        color="emerald"
        barSegments={[
          { value: conversionRate * 100, color: 'bg-emerald-400', label: 'Rate' },
        ]}
        onClick={() => navigate('/analytics')}
      />
    </div>
  );
}

interface BarSegment {
  value: number;
  color: string;
  label: string;
}

interface QuickStatCardProps {
  title: string;
  value: string | number;
  subtitle: string;
  icon: React.ReactNode;
  color: 'gold' | 'emerald' | 'coral';
  barSegments: BarSegment[];
  onClick?: () => void;
}

export function QuickStatCard({ title, value, subtitle, icon, color, barSegments, onClick }: QuickStatCardProps) {
  const totalBar = useMemo(() => {
    return barSegments.reduce((sum, s) => sum + s.value, 0);
  }, [barSegments]);

  const colorMap = {
    gold: 'text-gold-400 bg-gold-500/10',
    emerald: 'text-emerald-400 bg-emerald-500/10',
    coral: 'text-coral-400 bg-coral-500/10',
  };

  return (
    <Card
      hover
      onClick={onClick}
      className="group"
    >
      <div className="flex items-start justify-between mb-4">
        <div>
          <p className="text-xs text-navy-400 font-medium uppercase tracking-wider">{title}</p>
          <p className="text-3xl font-display font-bold text-navy-50 mt-2">{value}</p>
          <p className="text-xs text-navy-400 mt-1.5">{subtitle}</p>
        </div>
        <div className={`p-2.5 rounded-xl ${colorMap[color]}`}>
          {icon}
        </div>
      </div>
      {barSegments.length > 0 && totalBar > 0 && (
        <div className="mt-4">
          <div className="flex h-2 rounded-full overflow-hidden bg-navy-800 gap-0.5">
            {barSegments.map((seg, i) => (
              <div
                key={i}
                className={`${seg.color} rounded-full transition-all duration-500`}
                style={{ width: `${(seg.value / totalBar) * 100}%`, minWidth: '3px' }}
                title={seg.label}
              />
            ))}
          </div>
          <div className="flex justify-between mt-2">
            {barSegments.slice(0, 3).map((seg, i) => (
              <span key={i} className="text-[10px] text-navy-400 flex items-center gap-1.5">
                <span className={`w-2 h-2 rounded-full ${seg.color}`} />
                {seg.label}
              </span>
            ))}
          </div>
        </div>
      )}
      {onClick && (
        <div className="flex items-center justify-end mt-3 opacity-0 group-hover:opacity-100 transition-opacity">
          <span className="text-xs text-gold-400 flex items-center gap-1">
            View details <ArrowRight size={10} />
          </span>
        </div>
      )}
    </Card>
  );
}