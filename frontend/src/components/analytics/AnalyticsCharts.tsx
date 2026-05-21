import React from 'react';
import { Card, CardHeader, CardTitle } from '@/components/common';
import { TrendingUp, TrendingDown } from 'lucide-react';

interface AnalyticsChartProps {
  title: string;
  data: { label: string; value: number }[];
  type?: 'bar' | 'line' | 'area';
  color?: string;
}

export function SimpleBarChart({ title, data, color = '#fbbf24' }: AnalyticsChartProps) {
  const maxVal = Math.max(...data.map((d) => d.value), 1);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
      <div className="space-y-2">
        {data.map((item, i) => (
          <div key={i} className="flex items-center gap-3">
            <span className="text-xs text-navy-400 w-24 truncate">{item.label}</span>
            <div className="flex-1 h-6 bg-navy-800/50 rounded overflow-hidden">
              <div
                className="h-full rounded transition-all duration-500"
                style={{
                  width: `${(item.value / maxVal) * 100}%`,
                  backgroundColor: color,
                  opacity: 0.8,
                }}
              />
            </div>
            <span className="text-xs font-medium text-navy-200 w-12 text-right">{item.value}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}

interface DonutChartProps {
  title: string;
  segments: { label: string; value: number; color: string }[];
}

export function DonutChart({ title, segments }: DonutChartProps) {
  const total = segments.reduce((sum, s) => sum + s.value, 0);
  const radius = 40;
  const circumference = 2 * Math.PI * radius;
  let currentOffset = 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
      <div className="flex items-center gap-6">
        <div className="relative w-28 h-28 flex-shrink-0">
          <svg viewBox="0 0 100 100" className="transform -rotate-90">
            {segments.map((seg, i) => {
              const segmentLength = total > 0 ? (seg.value / total) * circumference : 0;
              const offset = currentOffset;
              currentOffset += segmentLength;
              return (
                <circle
                  key={i}
                  cx="50"
                  cy="50"
                  r={radius}
                  fill="none"
                  stroke={seg.color}
                  strokeWidth="12"
                  strokeDasharray={`${segmentLength} ${circumference - segmentLength}`}
                  strokeDashoffset={-offset}
                  className="transition-all duration-500"
                />
              );
            })}
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-lg font-display font-bold text-navy-50">{total}</span>
          </div>
        </div>
        <div className="space-y-2 flex-1">
          {segments.map((seg, i) => (
            <div key={i} className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: seg.color }} />
                <span className="text-navy-200">{seg.label}</span>
              </div>
              <span className="text-navy-400">{seg.value} ({total > 0 ? ((seg.value / total) * 100).toFixed(0) : 0}%)</span>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

interface ConversionFunnelProps {
  title: string;
  stages: { label: string; value: number; color?: string }[];
}

export function ConversionFunnel({ title, stages }: ConversionFunnelProps) {
  const maxVal = Math.max(...stages.map((s) => s.value), 1);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
      <div className="space-y-1.5">
        {stages.map((stage, i) => {
          const widthPercent = (stage.value / maxVal) * 100;
          const dropoff = i > 0 ? ((1 - stage.value / stages[i - 1].value) * 100).toFixed(0) : null;
          return (
            <div key={i} className="flex items-center gap-3">
              <span className="text-xs text-navy-400 w-20 text-right truncate">{stage.label}</span>
              <div className="flex-1 relative h-8 bg-navy-800/30 rounded overflow-hidden">
                <div
                  className="h-full rounded transition-all duration-500 flex items-center justify-center"
                  style={{
                    width: `${widthPercent}%`,
                    backgroundColor: stage.color || '#fbbf24',
                    opacity: 0.7 + (0.3 * (1 - i / stages.length)),
                  }}
                >
                  <span className="text-xs font-medium text-navy-950">{stage.value}</span>
                </div>
              </div>
              {dropoff !== null && (
                <span className="text-xs text-coral-400 w-14">
                  ↓ {dropoff}% drop
                </span>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}

// Demo analytics data
export const demoAnalyticsData = {
  channelPerformance: [
    { label: 'Email', value: 847 },
    { label: 'LinkedIn', value: 523 },
    { label: 'Phone', value: 312 },
    { label: 'SMS', value: 189 },
    { label: 'WhatsApp', value: 76 },
  ],
  leadPipeline: [
    { label: 'New', value: 156, color: '#829ab1' },
    { label: 'Contacted', value: 89, color: '#fbbf24' },
    { label: 'Qualified', value: 42, color: '#68d391' },
    { label: 'Proposal', value: 18, color: '#f59e0b' },
    { label: 'Negotiation', value: 8, color: '#d97706' },
    { label: 'Closed Won', value: 12, color: '#38a169' },
  ],
  conversionFunnel: [
    { label: 'Leads', value: 299, color: '#829ab1' },
    { label: 'Contacted', value: 189, color: '#fbbf24' },
    { label: 'Responded', value: 87, color: '#fcd34d' },
    { label: 'Meeting', value: 34, color: '#68d391' },
    { label: 'Closed', value: 12, color: '#38a169' },
  ],
  weeklyActivity: [
    { label: 'Mon', value: 234 },
    { label: 'Tue', value: 312 },
    { label: 'Wed', value: 278 },
    { label: 'Thu', value: 345 },
    { label: 'Fri', value: 289 },
    { label: 'Sat', value: 67 },
    { label: 'Sun', value: 12 },
  ],
};