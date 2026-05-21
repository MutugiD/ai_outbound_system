import { useCallback, useMemo } from 'react';
import type { Lead, LeadStatus } from '@/types';

export function useLeadFilter(leads: Lead[], searchQuery: string, statusFilter: LeadStatus | 'all') {
  const filteredLeads = useMemo(() => {
    let result = leads;

    if (statusFilter !== 'all') {
      result = result.filter((lead) => lead.status === statusFilter);
    }

    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      result = result.filter(
        (lead) =>
          lead.first_name.toLowerCase().includes(query) ||
          lead.last_name.toLowerCase().includes(query) ||
          lead.email.toLowerCase().includes(query) ||
          lead.company.toLowerCase().includes(query) ||
          lead.title.toLowerCase().includes(query)
      );
    }

    return result;
  }, [leads, searchQuery, statusFilter]);

  return filteredLeads;
}

export function useLeadSort(leads: Lead[], sortField: keyof Lead, sortDir: 'asc' | 'desc') {
  return useMemo(() => {
    return [...leads].sort((a, b) => {
      const aVal = a[sortField];
      const bVal = b[sortField];
      if (aVal == null || bVal == null) return 0;
      const comparison = String(aVal).localeCompare(String(bVal));
      return sortDir === 'asc' ? comparison : -comparison;
    });
  }, [leads, sortField, sortDir]);
}

export function useLeadStats(leads: Lead[]) {
  return useMemo(() => {
    const byStatus: Record<LeadStatus, number> = {
      new: 0, contacted: 0, qualified: 0, proposal: 0,
      negotiation: 0, closed_won: 0, closed_lost: 0, unreachable: 0,
    };
    
    leads.forEach((lead) => {
      byStatus[lead.status]++;
    });

    const totalScore = leads.reduce((sum, l) => sum + l.score, 0);
    const avgScore = leads.length > 0 ? totalScore / leads.length : 0;

    return { byStatus, avgScore, total: leads.length };
  }, [leads]);
}

export function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);
    return () => clearTimeout(handler);
  }, [value, delay]);

  return debouncedValue;
}

// Need to import useState and useEffect for useDebounce
import { useState, useEffect } from 'react';

export function useFormatNumber() {
  return useCallback((num: number): string => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return num.toLocaleString();
  }, []);
}

export function useFormatPercent() {
  return useCallback((num: number): string => {
    return `${(num * 100).toFixed(1)}%`;
  }, []);
}