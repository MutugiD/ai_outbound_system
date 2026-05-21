import { useCallback } from 'react';
import type { CampaignStatus, ChannelType, AgentStatus, MessageStatus, LeadStatus } from '@/types';

const statusColors: Record<string, { bg: string; text: string; dot: string }> = {
  // Campaign
  draft: { bg: 'bg-navy-700/50', text: 'text-navy-200', dot: 'bg-navy-400' },
  active: { bg: 'bg-emerald-900/50', text: 'text-emerald-300', dot: 'bg-emerald-400' },
  paused: { bg: 'bg-gold-900/50', text: 'text-gold-300', dot: 'bg-gold-400' },
  completed: { bg: 'bg-navy-700/50', text: 'text-navy-300', dot: 'bg-navy-400' },
  archived: { bg: 'bg-navy-800/50', text: 'text-navy-400', dot: 'bg-navy-500' },
  // Agent
  idle: { bg: 'bg-navy-700/50', text: 'text-navy-300', dot: 'bg-navy-400' },
  running: { bg: 'bg-emerald-900/50', text: 'text-emerald-300', dot: 'bg-emerald-400' },
  error: { bg: 'bg-coral-900/50', text: 'text-coral-300', dot: 'bg-coral-400' },
  // Lead
  new: { bg: 'bg-navy-700/50', text: 'text-navy-200', dot: 'bg-navy-300' },
  contacted: { bg: 'bg-gold-900/50', text: 'text-gold-300', dot: 'bg-gold-400' },
  qualified: { bg: 'bg-emerald-900/50', text: 'text-emerald-300', dot: 'bg-emerald-400' },
  proposal: { bg: 'bg-gold-900/50', text: 'text-gold-300', dot: 'bg-gold-500' },
  negotiation: { bg: 'bg-gold-800/50', text: 'text-gold-200', dot: 'bg-gold-400' },
  closed_won: { bg: 'bg-emerald-900/50', text: 'text-emerald-200', dot: 'bg-emerald-400' },
  closed_lost: { bg: 'bg-coral-900/50', text: 'text-coral-300', dot: 'bg-coral-400' },
  unreachable: { bg: 'bg-navy-800/50', text: 'text-navy-400', dot: 'bg-navy-500' },
  // Message
  pending: { bg: 'bg-navy-700/50', text: 'text-navy-300', dot: 'bg-navy-400' },
  sent: { bg: 'bg-gold-900/50', text: 'text-gold-300', dot: 'bg-gold-400' },
  delivered: { bg: 'bg-gold-800/50', text: 'text-gold-200', dot: 'bg-gold-500' },
  opened: { bg: 'bg-emerald-900/50', text: 'text-emerald-300', dot: 'bg-emerald-400' },
  replied: { bg: 'bg-emerald-800/50', text: 'text-emerald-200', dot: 'bg-emerald-300' },
  bounced: { bg: 'bg-coral-900/50', text: 'text-coral-300', dot: 'bg-coral-400' },
  failed: { bg: 'bg-coral-900/50', text: 'text-coral-300', dot: 'bg-coral-500' },
};

export function useStatusStyles() {
  const getStatusStyle = useCallback((status: CampaignStatus | AgentStatus | LeadStatus | MessageStatus | string) => {
    return statusColors[status] || statusColors.draft;
  }, []);

  return { getStatusStyle, statusColors };
}

const channelIcons: Record<ChannelType, string> = {
  email: 'Mail',
  linkedin: 'LinkedIn',
  phone: 'Phone',
  sms: 'MessageSquare',
  whatsapp: 'MessageCircle',
};

export function useChannelIcon() {
  const getChannelIcon = useCallback((channel: ChannelType): string => {
    return channelIcons[channel] || 'MessageSquare';
  }, []);

  return { getChannelIcon };
}

export function useRelativeTime() {
  const formatRelativeTime = useCallback((dateStr: string): string => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffSeconds = Math.floor(diffMs / 1000);
    const diffMinutes = Math.floor(diffSeconds / 60);
    const diffHours = Math.floor(diffMinutes / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffSeconds < 60) return 'just now';
    if (diffMinutes < 60) return `${diffMinutes}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  }, []);

  return { formatRelativeTime };
}