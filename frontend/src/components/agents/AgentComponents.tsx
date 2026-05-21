import React, { useState } from 'react';
import { Card, CardHeader, CardTitle, Badge, Button, Input, Textarea, Modal, Select } from '@/components/common';
import { useStatusStyles } from '@/hooks';
import type { Agent, AgentStatus } from '@/types';
import { Plus, Cpu, Zap, Clock, Target, Users, MessageSquare, Trophy, Settings, Play, Pause, AlertCircle, Bot, Radio, Phone, Mail, MessageCircle } from 'lucide-react';

// ── AgentCard ──────────────────────────────────────────────────────────────
interface AgentCardProps {
  agent: Agent;
  onSelect: (agent: Agent) => void;
}

const agentTypeIcons: Record<string, React.ReactNode> = {
  outbound: <Radio size={18} />,
  inbound: <MessageCircle size={18} />,
  sdr: <Zap size={18} />,
  bdr: <Phone size={18} />,
  closer: <Trophy size={18} />,
};

const agentStatusVariant: Record<AgentStatus, 'success' | 'warning' | 'danger' | 'default'> = {
  running: 'success',
  idle: 'default',
  paused: 'warning',
  error: 'danger',
};

export function AgentCard({ agent, onSelect }: AgentCardProps) {
  const { getStatusStyle } = useStatusStyles();

  return (
    <Card hover onClick={() => onSelect(agent)}>
      <CardHeader>
        <div className="flex items-center gap-2">
          <div className={`p-1.5 rounded-lg ${agent.status === 'running' ? 'bg-emerald-900/50 text-emerald-400' : agent.status === 'error' ? 'bg-coral-900/50 text-coral-400' : 'bg-navy-700/50 text-navy-300'}`}>
            {agentTypeIcons[agent.type] || <Cpu size={18} />}
          </div>
          <CardTitle>{agent.name}</CardTitle>
        </div>
        <Badge variant={agentStatusVariant[agent.status]} dot>{agent.status}</Badge>
      </CardHeader>
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-xs text-navy-400">
          <span className="uppercase font-medium">{agent.type}</span>
          <span>•</span>
          <span>{agent.model}</span>
        </div>
        <div className="grid grid-cols-3 gap-2 text-xs">
          <div className="text-center">
            <p className="text-navy-400">Sent</p>
            <p className="text-navy-100 font-medium">{agent.stats.messages_sent}</p>
          </div>
          <div className="text-center">
            <p className="text-navy-400">Replied</p>
            <p className="text-navy-100 font-medium">{agent.stats.responses_received}</p>
          </div>
          <div className="text-center">
            <p className="text-navy-400">Deals</p>
            <p className="text-navy-100 font-medium">{agent.stats.deals_closed}</p>
          </div>
        </div>
        <div className="flex gap-1.5 flex-wrap">
          {agent.channel.map((ch) => (
            <Badge key={ch} size="sm">{ch}</Badge>
          ))}
        </div>
      </div>
    </Card>
  );
}

// ── AgentGrid ─────────────────────────────────────────────────────────────
interface AgentGridProps {
  agents: Agent[];
  onSelect: (agent: Agent) => void;
  onCreateNew: () => void;
  loading: boolean;
}

export function AgentGrid({ agents, onSelect, onCreateNew, loading }: AgentGridProps) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold text-navy-50">AI Agents</h2>
          <span className="text-sm text-navy-400">({agents.length})</span>
        </div>
        <Button icon={<Plus size={14} />} onClick={onCreateNew}>
          New Agent
        </Button>
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
      ) : agents.length === 0 ? (
        <Card>
          <div className="text-center py-12">
            <Bot size={32} className="mx-auto text-navy-500 mb-3" />
            <p className="text-navy-300">No agents configured</p>
            <p className="text-sm text-navy-500 mt-1">Create an AI agent to automate outreach</p>
          </div>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {agents.map((agent) => (
            <AgentCard key={agent.id} agent={agent} onSelect={onSelect} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── CreateAgentModal ───────────────────────────────────────────────────────
interface CreateAgentModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function CreateAgentModal({ isOpen, onClose }: CreateAgentModalProps) {
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    name: '',
    type: 'sdr' as Agent['type'],
    model: 'gpt-4o',
    system_prompt: '',
    daily_limit: 100,
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      // Would call API here
      onClose();
      setForm({ name: '', type: 'sdr', model: 'gpt-4o', system_prompt: '', daily_limit: 100 });
    } catch (err) {
      console.error('Failed to create agent:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Create New AI Agent" size="lg">
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label="Agent Name"
          placeholder="e.g., Enterprise SDR Agent"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          required
        />
        <Select
          label="Agent Type"
          value={form.type}
          onChange={(e) => setForm({ ...form, type: e.target.value as Agent['type'] })}
          options={[
            { value: 'outbound', label: 'Outbound' },
            { value: 'inbound', label: 'Inbound' },
            { value: 'sdr', label: 'SDR' },
            { value: 'bdr', label: 'BDR' },
            { value: 'closer', label: 'Closer' },
          ]}
        />
        <Select
          label="AI Model"
          value={form.model}
          onChange={(e) => setForm({ ...form, model: e.target.value })}
          options={[
            { value: 'gpt-4o', label: 'GPT-4o' },
            { value: 'gpt-4o-mini', label: 'GPT-4o Mini' },
            { value: 'claude-3.5-sonnet', label: 'Claude 3.5 Sonnet' },
          ]}
        />
        <Input
          label="Daily Limit"
          type="number"
          value={form.daily_limit}
          onChange={(e) => setForm({ ...form, daily_limit: parseInt(e.target.value) || 0 })}
          min={1}
          max={500}
          hint="Maximum actions per day"
        />
        <Textarea
          label="System Prompt"
          placeholder="You are an AI sales development representative..."
          value={form.system_prompt}
          onChange={(e) => setForm({ ...form, system_prompt: e.target.value })}
          hint="Instructions that define the agent's behavior"
        />
        <div className="flex justify-end gap-3 pt-2">
          <Button variant="secondary" onClick={onClose} type="button">Cancel</Button>
          <Button type="submit" loading={loading} icon={<Plus size={14} />}>
            Create Agent
          </Button>
        </div>
      </form>
    </Modal>
  );
}