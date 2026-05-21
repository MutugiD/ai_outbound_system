import React from 'react';
import { Card, CardHeader, CardTitle } from '@/components/common';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface ChartDataPoint {
  date: string;
  value: number;
}

interface MiniChartProps {
  title: string;
  data: ChartDataPoint[];
  color?: string;
  change?: number;
  format?: 'number' | 'percent' | 'currency';
}

export function MiniChart({ title, data, color = '#fbbf24', change, format = 'number' }: MiniChartProps) {
  const latest = data.length > 0 ? data[data.length - 1].value : 0;
  const previous = data.length > 1 ? data[data.length - 2].value : 0;

  const formatValue = (val: number) => {
    switch (format) {
      case 'percent': return `${val}%`;
      case 'currency': return `$${val.toLocaleString()}`;
      default: return val.toLocaleString();
    }
  };

  // Build SVG path
  const width = 220;
  const height = 60;
  const padding = 4;

  const maxVal = Math.max(...data.map((d) => d.value), 1);
  const minVal = Math.min(...data.map((d) => d.value), 0);
  const range = maxVal - minVal || 1;

  const points = data.map((d, i) => {
    const x = padding + (i / (data.length - 1 || 1)) * (width - 2 * padding);
    const y = height - padding - ((d.value - minVal) / range) * (height - 2 * padding);
    return `${x},${y}`;
  });

  const linePath = points.join(' ');
  const areaPath = `${linePath} ${width - padding},${height} ${padding},${height}`;

  return (
    <Card hover className="group">
      <CardHeader className="mb-2">
        <CardTitle className="text-sm">{title}</CardTitle>
        {change !== undefined && (
          <div className="flex items-center gap-1 text-xs">
            {change > 0 ? (
              <TrendingUp size={12} className="text-emerald-400" />
            ) : change < 0 ? (
              <TrendingDown size={12} className="text-coral-400" />
            ) : (
              <Minus size={12} className="text-navy-400" />
            )}
            <span className={change > 0 ? 'text-emerald-400' : change < 0 ? 'text-coral-400' : 'text-navy-400'}>
              {Math.abs(change).toFixed(1)}%
            </span>
          </div>
        )}
      </CardHeader>
      <div className="text-2xl font-display font-bold text-navy-50 mb-4">
        {formatValue(latest)}
      </div>
      {data.length > 1 && (
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-14" preserveAspectRatio="none">
          <defs>
            <linearGradient id={`gradient-${title.replace(/\s/g, '')}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity="0.25" />
              <stop offset="100%" stopColor={color} stopOpacity="0" />
            </linearGradient>
          </defs>
          <polygon
            points={areaPath}
            fill={`url(#gradient-${title.replace(/\s/g, '')})`}
          />
          <polyline
            points={linePath}
            fill="none"
            stroke={color}
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {data.length > 0 && (
            <circle
              cx={width - padding}
              cy={height - padding - ((latest - minVal) / range) * (height - 2 * padding)}
              r="4"
              fill={color}
              stroke="var(--color-navy-900, #102a43)"
              strokeWidth="2"
            />
          )}
        </svg>
      )}
    </Card>
  );
}

// Demo chart data
export const demoChartData: Record<string, ChartDataPoint[]> = {
  messages: [
    { date: '2026-05-15', value: 145 },
    { date: '2026-05-16', value: 178 },
    { date: '2026-05-17', value: 198 },
    { date: '2026-05-18', value: 234 },
    { date: '2026-05-19', value: 210 },
    { date: '2026-05-20', value: 267 },
    { date: '2026-05-21', value: 289 },
  ],
  replies: [
    { date: '2026-05-15', value: 12 },
    { date: '2026-05-16', value: 15 },
    { date: '2026-05-17', value: 18 },
    { date: '2026-05-18', value: 22 },
    { date: '2026-05-19', value: 19 },
    { date: '2026-05-20', value: 28 },
    { date: '2026-05-21', value: 31 },
  ],
  conversion: [
    { date: '2026-05-15', value: 8.2 },
    { date: '2026-05-16', value: 9.1 },
    { date: '2026-05-17', value: 10.5 },
    { date: '2026-05-18', value: 11.2 },
    { date: '2026-05-19', value: 10.8 },
    { date: '2026-05-20', value: 12.1 },
    { date: '2026-05-21', value: 12.4 },
  ],
  meetings: [
    { date: '2026-05-15', value: 2 },
    { date: '2026-05-16', value: 3 },
    { date: '2026-05-17', value: 1 },
    { date: '2026-05-18', value: 4 },
    { date: '2026-05-19', value: 2 },
    { date: '2026-05-20', value: 5 },
    { date: '2026-05-21', value: 3 },
  ],
};