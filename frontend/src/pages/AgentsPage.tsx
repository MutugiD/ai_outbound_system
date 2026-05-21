import React, { useEffect, useState } from 'react';
import { AgentGrid, CreateAgentModal } from '@/components/agents';
import { useAgentStore, useUIStore } from '@/stores';
import { api } from '@/services';
import type { Agent } from '@/types';

// Demo agents data
const demoAgents: Agent[] = [
  {
    id: 'agent-1', name: 'Enterprise SDR Agent', type: 'sdr', status: 'running', model: 'gpt-4o',
    system_prompt: 'You are an AI sales development rep targeting enterprise accounts...', channel: ['email', 'linkedin'],
    current_campaigns: ['1', '2'],
    stats: { messages_sent: 1847, responses_received: 234, meetings_booked: 34, deals_closed: 8, avg_response_time: 4.2, success_rate: 0.126 },
    config: { temperature: 0.7, max_tokens: 2048, daily_limit: 100, follow_up_delay: 86400, max_follow_ups: 3, working_hours_start: '09:00', working_hours_end: '17:00', timezone: 'UTC' },
    created_at: '2026-04-01T10:00:00Z', updated_at: '2026-05-21T08:00:00Z',
  },
  {
    id: 'agent-2', name: 'LinkedIn Outreach Bot', type: 'outbound', status: 'running', model: 'gpt-4o',
    system_prompt: 'You handle LinkedIn connection requests and follow-ups...', channel: ['linkedin'],
    current_campaigns: ['2'],
    stats: { messages_sent: 523, responses_received: 87, meetings_booked: 12, deals_closed: 3, avg_response_time: 6.1, success_rate: 0.057 },
    config: { temperature: 0.8, max_tokens: 1024, daily_limit: 50, follow_up_delay: 172800, max_follow_ups: 2, working_hours_start: '08:00', working_hours_end: '18:00', timezone: 'UTC' },
    created_at: '2026-04-15T14:00:00Z', updated_at: '2026-05-21T07:30:00Z',
  },
  {
    id: 'agent-3', name: 'Phone Follow-up Agent', type: 'bdr', status: 'paused', model: 'gpt-4o-mini',
    system_prompt: 'You make follow-up calls after email responses...', channel: ['phone'],
    current_campaigns: [],
    stats: { messages_sent: 312, responses_received: 45, meetings_booked: 8, deals_closed: 1, avg_response_time: 2.8, success_rate: 0.003 },
    config: { temperature: 0.6, max_tokens: 2048, daily_limit: 30, follow_up_delay: 43200, max_follow_ups: 2, working_hours_start: '10:00', working_hours_end: '16:00', timezone: 'UTC' },
    created_at: '2026-05-01T09:00:00Z', updated_at: '2026-05-19T14:00:00Z',
  },
  {
    id: 'agent-4', name: 'Closer Agent', type: 'closer', status: 'idle', model: 'claude-3.5-sonnet',
    system_prompt: 'You are an AI closer that handles deal negotiation...', channel: ['email', 'phone'],
    current_campaigns: [],
    stats: { messages_sent: 89, responses_received: 45, meetings_booked: 15, deals_closed: 7, avg_response_time: 1.5, success_rate: 0.078 },
    config: { temperature: 0.5, max_tokens: 4096, daily_limit: 20, follow_up_delay: 86400, max_follow_ups: 5, working_hours_start: '09:00', working_hours_end: '17:00', timezone: 'UTC' },
    created_at: '2026-04-20T16:00:00Z', updated_at: '2026-05-18T11:00:00Z',
  },
  {
    id: 'agent-5', name: 'WhatsApp Nurture Bot', type: 'inbound', status: 'error', model: 'gpt-4o-mini',
    system_prompt: 'You handle WhatsApp nurture sequences...', channel: ['whatsapp'],
    current_campaigns: [],
    stats: { messages_sent: 0, responses_received: 0, meetings_booked: 0, deals_closed: 0, avg_response_time: 0, success_rate: 0 },
    config: { temperature: 0.7, max_tokens: 1024, daily_limit: 200, follow_up_delay: 86400, max_follow_ups: 4, working_hours_start: '08:00', working_hours_end: '20:00', timezone: 'UTC' },
    created_at: '2026-05-20T11:00:00Z', updated_at: '2026-05-20T11:00:00Z',
  },
];

export default function AgentsPage() {
  const { agents, setAgents } = useAgentStore();
  const { addNotification } = useUIStore();
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadAgents = async () => {
      try {
        const data = await api.getAgents();
        setAgents(data);
      } catch {
        setAgents(demoAgents);
      } finally {
        setLoading(false);
      }
    };
    loadAgents();
  }, [setAgents]);

  return (
    <div className="animate-fade-in">
      <AgentGrid
        agents={agents}
        onSelect={(agent) => addNotification({ type: 'info', message: `Agent: ${agent.name}` })}
        onCreateNew={() => setShowCreateModal(true)}
        loading={loading}
      />
      <CreateAgentModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
      />
    </div>
  );
}