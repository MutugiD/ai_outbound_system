import React from 'react';
import {
  Megaphone,
  Users,
  MessageSquare,
  Target,
  CalendarCheck,
  TrendingUp,
  Mail,
  Trophy,
} from 'lucide-react';
import { MetricCard, MetricCardSkeleton, Card, CardHeader, CardTitle } from '@/components/common';
import type { DashboardMetrics } from '@/types';

interface DashboardMetricsProps {
  metrics: DashboardMetrics | null;
  loading: boolean;
}

export function DashboardMetricsRow({ metrics, loading }: DashboardMetricsProps) {
  if (loading || !metrics) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => <MetricCardSkeleton key={i} />)}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <MetricCard
        label="Active Campaigns"
        value={metrics.active_campaigns}
        icon={<Megaphone size={20} />}
        accent="gold"
      />
      <MetricCard
        label="Messages Today"
        value={metrics.messages_sent_today}
        change={metrics.reply_rate}
        changeLabel="reply rate"
        icon={<MessageSquare size={20} />}
        accent="emerald"
      />
      <MetricCard
        label="Meetings Booked"
        value={metrics.meetings_today}
        icon={<CalendarCheck size={20} />}
        accent="gold"
      />
      <MetricCard
        label="Conversion Rate"
        value={`${(metrics.conversion_rate * 100).toFixed(1)}%`}
        icon={<Target size={20} />}
        accent="emerald"
      />
    </div>
  );
}

interface ActivityFeedProps {
  items: import('@/types').ActivityFeedItem[];
  loading: boolean;
}

const activityIcons: Record<string, React.ReactNode> = {
  message_sent: <Mail size={16} />,
  reply_received: <MessageSquare size={16} />,
  meeting_booked: <CalendarCheck size={16} />,
  deal_closed: <Trophy size={16} />,
  lead_added: <Users size={16} />,
  campaign_started: <Megaphone size={16} />,
  agent_action: <TrendingUp size={16} />,
};

const activityColors: Record<string, string> = {
  message_sent: 'bg-navy-700 text-navy-300',
  reply_received: 'bg-emerald-900/50 text-emerald-400',
  meeting_booked: 'bg-gold-900/50 text-gold-400',
  deal_closed: 'bg-emerald-800/50 text-emerald-300',
  lead_added: 'bg-navy-700 text-navy-200',
  campaign_started: 'bg-gold-900/50 text-gold-400',
  agent_action: 'bg-navy-700 text-navy-300',
};

const activityLabels: Record<string, string> = {
  message_sent: 'Message Sent',
  reply_received: 'Reply Received',
  meeting_booked: 'Meeting Booked',
  deal_closed: 'Deal Closed',
  lead_added: 'Lead Added',
  campaign_started: 'Campaign Started',
  agent_action: 'Agent Action',
};

function getRelativeTime(timestamp: string): string {
  const now = Date.now();
  const then = new Date(timestamp).getTime();
  const diffMs = now - then;
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${diffDays}d ago`;
}

export function ActivityFeed({ items, loading }: ActivityFeedProps) {
  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Activity Feed</CardTitle>
        </CardHeader>
        <div className="space-y-4">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="flex items-center gap-4 animate-pulse">
              <div className="w-10 h-10 rounded-full bg-navy-700/50 flex-shrink-0" />
              <div className="flex-1">
                <div className="h-3 w-3/4 rounded bg-navy-700/50 mb-2" />
                <div className="h-2 w-1/4 rounded bg-navy-700/50" />
              </div>
            </div>
          ))}
        </div>
      </Card>
    );
  }

  return (
    <Card>
      <div className="divide-y divide-navy-700/30">
        {items.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-sm text-navy-400">No recent activity</p>
          </div>
        ) : (
          items.map((item) => (
            <div key={item.id} className="flex items-center gap-4 px-5 py-4 hover:bg-navy-800/30 transition-colors">
              <div className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center ${activityColors[item.type] || 'bg-navy-700 text-navy-300'}`}>
                {activityIcons[item.type] || <MessageSquare size={16} />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-xs font-semibold text-navy-200 uppercase tracking-wider">
                    {activityLabels[item.type] || 'Activity'}
                  </span>
                </div>
                <p className="text-sm text-navy-300 truncate">
                  {item.description}
                </p>
              </div>
              <div className="flex-shrink-0 text-right">
                <span className="text-xs text-navy-400 whitespace-nowrap">
                  {getRelativeTime(item.timestamp)}
                </span>
              </div>
            </div>
          ))
        )}
      </div>
    </Card>
  );
}