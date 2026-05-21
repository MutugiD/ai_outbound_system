import React from 'react';
import { Card, CardHeader, CardTitle, Badge, Button } from '@/components/common';
import { useCampaignStore } from '@/stores';
import { useStatusStyles, useChannelIcon } from '@/hooks';
import type { Campaign, CampaignStatus } from '@/types';
import { Plus, Megaphone, Users, MessageSquare, Target, CalendarCheck, Mail, Trophy, TrendingUp, Pause, Play, Edit2, Trash2, ArrowLeft, BarChart3, Info, Sparkles } from 'lucide-react';

// ── CampaignCard ──────────────────────────────────────────────────────────
interface CampaignCardProps {
  campaign: Campaign;
  onSelect: (campaign: Campaign) => void;
}

export function CampaignCard({ campaign, onSelect }: CampaignCardProps) {
  const { getStatusStyle } = useStatusStyles();
  const { getChannelIcon } = useChannelIcon();
  const style = getStatusStyle(campaign.status);

  return (
    <Card hover onClick={() => onSelect(campaign)}>
      <CardHeader>
        <CardTitle>{campaign.name}</CardTitle>
        <Badge variant={campaign.status === 'active' ? 'success' : campaign.status === 'paused' ? 'warning' : 'default'} dot>
          {campaign.status}
        </Badge>
      </CardHeader>
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm text-navy-300">
          <span className="capitalize">{campaign.channel}</span>
          <span className="text-navy-600">•</span>
          <span>{campaign.stats.total_leads} leads</span>
        </div>
        <div className="grid grid-cols-3 gap-2 text-xs">
          <div className="text-center">
            <p className="text-navy-400">Contacted</p>
            <p className="text-navy-100 font-medium">{campaign.stats.contacted}</p>
          </div>
          <div className="text-center">
            <p className="text-navy-400">Responded</p>
            <p className="text-navy-100 font-medium">{campaign.stats.responded}</p>
          </div>
          <div className="text-center">
            <p className="text-navy-400">Meetings</p>
            <p className="text-navy-100 font-medium">{campaign.stats.meetings_booked}</p>
          </div>
        </div>
      </div>
    </Card>
  );
}

// ── CampaignList ──────────────────────────────────────────────────────────
interface CampaignListProps {
  campaigns: Campaign[];
  onSelect: (campaign: Campaign) => void;
  onCreateNew: () => void;
  loading: boolean;
}

export function CampaignList({ campaigns, onSelect, onCreateNew, loading }: CampaignListProps) {
  const { filter, setFilter } = useCampaignStore();

  const filteredCampaigns = filter === 'all'
    ? campaigns
    : campaigns.filter((c) => c.status === filter);

  const statusFilters: (CampaignStatus | 'all')[] = ['all', 'active', 'paused', 'draft', 'completed', 'archived'];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold text-navy-50">Campaigns</h2>
          <span className="text-sm text-navy-400">({campaigns.length})</span>
        </div>
        <Button icon={<Plus size={14} />} onClick={onCreateNew}>
          New Campaign
        </Button>
      </div>

      <div className="flex gap-2 flex-wrap">
        {statusFilters.map((status) => (
          <button
            key={status}
            onClick={() => setFilter(status)}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              filter === status
                ? 'bg-gold-500 text-navy-950'
                : 'bg-navy-800 text-navy-300 hover:bg-navy-700'
            }`}
          >
            {status === 'all' ? 'All' : status.charAt(0).toUpperCase() + status.slice(1)}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => (
            <Card key={i}>
              <div className="animate-pulse space-y-4">
                <div className="h-5 w-2/3 rounded bg-navy-700/50" />
                <div className="h-4 w-1/3 rounded bg-navy-700/50" />
                <div className="grid grid-cols-3 gap-2">
                  {[...Array(3)].map((_, j) => (
                    <div key={j}>
                      <div className="h-3 w-12 rounded bg-navy-700/50 mb-1" />
                      <div className="h-4 w-8 rounded bg-navy-700/50" />
                    </div>
                  ))}
                </div>
              </div>
            </Card>
          ))}
        </div>
      ) : filteredCampaigns.length === 0 ? (
        <Card>
          <div className="text-center py-12">
            <Megaphone size={32} className="mx-auto text-navy-500 mb-3" />
            <p className="text-navy-300">No campaigns found</p>
            <p className="text-sm text-navy-500 mt-1">Create a new campaign to get started</p>
          </div>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filteredCampaigns.map((campaign) => (
            <CampaignCard key={campaign.id} campaign={campaign} onSelect={onSelect} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Progress Bar Helper ──────────────────────────────────────────────────
function ProgressBar({ value, max, color = 'gold' }: { value: number; max: number; color?: 'gold' | 'emerald' | 'coral' }) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  const barColor = color === 'gold' ? 'bg-gold-400' : color === 'emerald' ? 'bg-emerald-400' : 'bg-coral-400';
  return (
    <div className="w-full h-1.5 rounded-full bg-navy-800 overflow-hidden">
      <div className={`h-full rounded-full transition-all duration-500 ${barColor}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

// ── Stat Helper ──────────────────────────────────────────────────────────
function StatItem({ label, value, subtext, icon, color }: {
  label: string;
  value: string | number;
  subtext?: string;
  icon: React.ReactNode;
  color: 'gold' | 'emerald';
}) {
  const bgClass = color === 'gold' ? 'bg-gold-900/50 text-gold-400' : 'bg-emerald-900/50 text-emerald-400';
  return (
    <div className="flex items-center gap-4 p-4 rounded-xl bg-navy-800/50 border border-navy-700/50">
      <div className={`flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center ${bgClass}`}>
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs text-navy-400 uppercase tracking-wider">{label}</p>
        <p className="text-xl font-display font-bold text-navy-50">{value}</p>
        {subtext && <p className="text-xs text-navy-400 mt-0.5">{subtext}</p>}
      </div>
    </div>
  );
}

// ── CampaignDetail ────────────────────────────────────────────────────────
interface CampaignDetailProps {
  campaign: Campaign;
  onBack: () => void;
  onEdit: () => void;
  onToggleStatus: () => void;
  onDelete: () => void;
}

export function CampaignDetail({ campaign, onBack, onEdit, onToggleStatus, onDelete }: CampaignDetailProps) {
  const { getStatusStyle } = useStatusStyles();
  const style = getStatusStyle(campaign.status);

  const contactedPct = campaign.stats.total_leads > 0
    ? ((campaign.stats.contacted / campaign.stats.total_leads) * 100).toFixed(0)
    : '0';
  const respondedPct = campaign.stats.contacted > 0
    ? ((campaign.stats.responded / campaign.stats.contacted) * 100).toFixed(0)
    : '0';
  const qualifiedPct = campaign.stats.responded > 0
    ? ((campaign.stats.qualified / campaign.stats.responded) * 100).toFixed(0)
    : '0';
  const meetingPct = campaign.stats.qualified > 0
    ? ((campaign.stats.meetings_booked / campaign.stats.qualified) * 100).toFixed(0)
    : '0';

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-4">
          <button onClick={onBack} className="text-navy-300 hover:text-navy-50 transition-colors p-1">
            <ArrowLeft size={20} />
          </button>
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-display font-bold text-navy-50">{campaign.name}</h2>
              <Badge variant={campaign.status === 'active' ? 'success' : campaign.status === 'paused' ? 'warning' : 'default'} dot>
                {campaign.status}
              </Badge>
            </div>
            <p className="text-sm text-navy-400 mt-0.5 capitalize">{campaign.channel} campaign</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" icon={<Edit2 size={14} />} onClick={onEdit}>Edit</Button>
          <Button variant="ghost" size="sm" icon={campaign.status === 'active' ? <Pause size={14} /> : <Play size={14} />} onClick={onToggleStatus}>
            {campaign.status === 'active' ? 'Pause' : 'Start'}
          </Button>
          <Button variant="danger" size="sm" icon={<Trash2 size={14} />} onClick={onDelete}>Delete</Button>
        </div>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatItem
          label="Total Leads"
          value={campaign.stats.total_leads}
          subtext={`${campaign.stats.contacted} contacted`}
          icon={<Users size={18} />}
          color="gold"
        />
        <StatItem
          label="Responded"
          value={campaign.stats.responded}
          subtext={`${respondedPct}% reply rate`}
          icon={<MessageSquare size={18} />}
          color="emerald"
        />
        <StatItem
          label="Meetings"
          value={campaign.stats.meetings_booked}
          subtext={`${campaign.stats.qualified} qualified`}
          icon={<CalendarCheck size={18} />}
          color="gold"
        />
        <StatItem
          label="Deals Closed"
          value={campaign.stats.deals_closed}
          subtext={`${(campaign.stats.conversion_rate * 100).toFixed(1)}% conversion`}
          icon={<Trophy size={18} />}
          color="emerald"
        />
      </div>

      {/* Pipeline Funnel */}
      <Card>
        <CardHeader>
          <CardTitle>
            <div className="flex items-center gap-2">
              <BarChart3 size={16} className="text-gold-400" />
              Pipeline Funnel
            </div>
          </CardTitle>
        </CardHeader>
        <div className="space-y-4">
          <FunnelStep
            label="Leads"
            value={campaign.stats.total_leads}
            max={campaign.stats.total_leads}
            color="gold"
          />
          <FunnelStep
            label="Contacted"
            value={campaign.stats.contacted}
            max={campaign.stats.total_leads}
            color="gold"
          />
          <FunnelStep
            label="Responded"
            value={campaign.stats.responded}
            max={campaign.stats.total_leads}
            color="emerald"
          />
          <FunnelStep
            label="Qualified"
            value={campaign.stats.qualified}
            max={campaign.stats.total_leads}
            color="emerald"
          />
          <FunnelStep
            label="Meetings"
            value={campaign.stats.meetings_booked}
            max={campaign.stats.total_leads}
            color="gold"
          />
          <FunnelStep
            label="Deals"
            value={campaign.stats.deals_closed}
            max={campaign.stats.total_leads}
            color="emerald"
          />
        </div>
      </Card>

      {/* Performance + Details side-by-side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Performance */}
        <Card>
          <CardHeader>
            <CardTitle>
              <div className="flex items-center gap-2">
                <Sparkles size={16} className="text-emerald-400" />
                Performance
              </div>
            </CardTitle>
          </CardHeader>
          <div className="space-y-4">
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-navy-300">Response Rate</span>
                <span className="font-medium text-navy-50">{(campaign.stats.response_rate * 100).toFixed(0)}%</span>
              </div>
              <ProgressBar value={campaign.stats.response_rate * 100} max={100} color="emerald" />
            </div>
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-navy-300">Conversion Rate</span>
                <span className="font-medium text-navy-50">{(campaign.stats.conversion_rate * 100).toFixed(1)}%</span>
              </div>
              <ProgressBar value={campaign.stats.conversion_rate * 100} max={100} color="gold" />
            </div>
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-navy-300">Lead → Contact</span>
                <span className="font-medium text-navy-50">{contactedPct}%</span>
              </div>
              <ProgressBar value={campaign.stats.contacted} max={campaign.stats.total_leads} color="gold" />
            </div>
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-navy-300">Contact → Reply</span>
                <span className="font-medium text-navy-50">{respondedPct}%</span>
              </div>
              <ProgressBar value={campaign.stats.responded} max={campaign.stats.contacted} color="emerald" />
            </div>
          </div>
        </Card>

        {/* Details */}
        <Card>
          <CardHeader>
            <CardTitle>
              <div className="flex items-center gap-2">
                <Info size={16} className="text-navy-300" />
                Campaign Details
              </div>
            </CardTitle>
          </CardHeader>
          <div className="space-y-3">
            <DetailRow label="Agent ID" value={campaign.agent_id} />
            <DetailRow label="Channel" value={campaign.channel.charAt(0).toUpperCase() + campaign.channel.slice(1)} />
            <DetailRow label="Daily Limit" value={`${campaign.daily_limit} messages/day`} />
            <DetailRow label="Start Date" value={new Date(campaign.start_date).toLocaleDateString()} />
            {campaign.end_date && (
              <DetailRow label="End Date" value={new Date(campaign.end_date).toLocaleDateString()} />
            )}
            <DetailRow label="Created" value={new Date(campaign.created_at).toLocaleDateString()} />
            <DetailRow label="Last Updated" value={new Date(campaign.updated_at).toLocaleDateString()} />
          </div>
        </Card>
      </div>
    </div>
  );
}

// ── FunnelStep ────────────────────────────────────────────────────────────
function FunnelStep({ label, value, max, color }: { label: string; value: number; max: number; color: 'gold' | 'emerald' }) {
  const pct = max > 0 ? (value / max) * 100 : 0;
  const barClass = color === 'gold' ? 'bg-gold-400' : 'bg-emerald-400';
  const textClass = color === 'gold' ? 'text-gold-400' : 'text-emerald-400';

  return (
    <div className="flex items-center gap-4">
      <div className="w-24 text-sm text-navy-300 text-right">{label}</div>
      <div className="flex-1">
        <div className="w-full h-6 rounded-md bg-navy-800 overflow-hidden">
          <div
            className={`h-full rounded-md ${barClass} transition-all duration-700 flex items-center justify-end pr-2`}
            style={{ width: `${Math.max(pct, 3)}%` }}
          >
            {pct > 15 && <span className="text-[10px] font-bold text-navy-950">{value}</span>}
          </div>
        </div>
      </div>
      <div className="w-14 text-right">
        <span className={`text-sm font-semibold ${textClass}`}>{value}</span>
      </div>
    </div>
  );
}

// ── DetailRow ─────────────────────────────────────────────────────────────
function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between items-center py-2 border-b border-navy-700/50 last:border-0">
      <span className="text-sm text-navy-400">{label}</span>
      <span className="text-sm text-navy-100 font-medium">{value}</span>
    </div>
  );
}