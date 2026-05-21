import React, { useState } from 'react';
import { SimpleBarChart, DonutChart, ConversionFunnel, demoAnalyticsData } from '@/components/analytics';
import { Card, CardHeader, CardTitle } from '@/components/common';
import { MetricCard } from '@/components/common';
import { TrendingUp, MessageSquare, Users, Target, CalendarCheck, DollarSign } from 'lucide-react';

export default function AnalyticsPage() {
  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-navy-50">Analytics</h1>
          <p className="text-sm text-navy-400 mt-1">Performance insights and conversion metrics</p>
        </div>
        <div className="flex items-center gap-2">
          <select className="px-3 py-1.5 bg-navy-800 border border-navy-600/40 rounded-lg text-xs text-navy-200 focus:outline-none focus:ring-2 focus:ring-gold-500/50">
            <option>Last 7 days</option>
            <option>Last 30 days</option>
            <option>Last 90 days</option>
            <option>All time</option>
          </select>
        </div>
      </div>

      {/* High-level KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <MetricCard
          label="Total Messages Sent"
          value="1,947"
          change={15.3}
          changeLabel="vs last week"
          icon={<MessageSquare size={18} />}
          accent="gold"
        />
        <MetricCard
          label="Avg Response Time"
          value="4.2h"
          change={-8.1}
          changeLabel="faster"
          icon={<TrendingUp size={18} />}
          accent="emerald"
        />
        <MetricCard
          label="Pipeline Value"
          value="$284K"
          change={12.5}
          changeLabel="vs last week"
          icon={<DollarSign size={18} />}
          accent="gold"
        />
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Channel Performance */}
        <SimpleBarChart
          title="Channel Performance"
          data={demoAnalyticsData.channelPerformance}
          color="#fbbf24"
        />

        {/* Lead Pipeline Donut */}
        <DonutChart
          title="Lead Pipeline Distribution"
          segments={demoAnalyticsData.leadPipeline}
        />
      </div>

      {/* Conversion Funnel */}
      <ConversionFunnel
        title="Conversion Funnel"
        stages={demoAnalyticsData.conversionFunnel}
      />

      {/* Weekly Activity */}
      <SimpleBarChart
        title="Weekly Activity"
        data={demoAnalyticsData.weeklyActivity}
        color="#68d391"
      />
    </div>
  );
}