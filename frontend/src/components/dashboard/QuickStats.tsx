import React, { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardHeader, CardTitle } from '@/components/common';
import { Megaphone, Users, MessageSquare, Target, ArrowRight } from 'lucide-react';

// Demo data for the pipeline stats on dashboard
const miniChartData = {
  campaigns: {
    active: 4,
    draft: 2,
    completed: 8,
    paused: 1,
  },
  leads: {
    new: 156,
    contacted: 89,
    qualified: 42,
    closed_won: 12,
  },
};

export function QuickStatsGrid() {
  const navigate = useNavigate();

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
      <QuickStatCard
        title="Active Campaigns"
        value={4}
        subtitle="2 drafts waiting"
        icon={<Megaphone size={20} />}
        color="gold"
        barSegments={[
          { value: 4, color: 'bg-gold-400', label: 'Active' },
          { value: 2, color: 'bg-navy-500', label: 'Draft' },
          { value: 1, color: 'bg-navy-600', label: 'Paused' },
        ]}
        onClick={() => navigate('/campaigns')}
      />
      <QuickStatCard
        title="Total Leads"
        value={299}
        subtitle="89 contacted this week"
        icon={<Users size={20} />}
        color="emerald"
        barSegments={[
          { value: 156, color: 'bg-navy-400', label: 'New' },
          { value: 89, color: 'bg-gold-400', label: 'Contacted' },
          { value: 42, color: 'bg-emerald-400', label: 'Qualified' },
        ]}
        onClick={() => navigate('/leads')}
      />
      <QuickStatCard
        title="Messages Sent"
        value="1,847"
        subtitle="+234 today"
        icon={<MessageSquare size={20} />}
        color="gold"
        barSegments={[
          { value: 70, color: 'bg-gold-400', label: 'Sent' },
          { value: 20, color: 'bg-emerald-400', label: 'Opened' },
          { value: 10, color: 'bg-navy-500', label: 'Bounced' },
        ]}
        onClick={() => navigate('/campaigns')}
      />
      <QuickStatCard
        title="Conversion Rate"
        value="12.4%"
        subtitle="3 deals closed"
        icon={<Target size={20} />}
        color="emerald"
        barSegments={[
          { value: 12.4, color: 'bg-emerald-400', label: 'Rate' },
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
      {barSegments.length > 0 && (
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