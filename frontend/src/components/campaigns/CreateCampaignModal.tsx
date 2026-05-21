import React, { useState } from 'react';
import { Modal, Input, Select, Textarea, Button } from '@/components/common';
import { useCampaignStore } from '@/stores';
import { api } from '@/services';
import { Plus } from 'lucide-react';
import type { ChannelType, Campaign } from '@/types';

interface CreateCampaignModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function CreateCampaignModal({ isOpen, onClose }: CreateCampaignModalProps) {
  const { addCampaign } = useCampaignStore();
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    name: '',
    channel: 'email' as ChannelType,
    daily_limit: 100,
    message_template: '',
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const campaign = await api.createCampaign({
        name: form.name,
        channel: form.channel,
        daily_limit: form.daily_limit,
        status: 'draft',
      } as Partial<Campaign>);
      addCampaign(campaign as Campaign);
      onClose();
      setForm({ name: '', channel: 'email', daily_limit: 100, message_template: '' });
    } catch (err) {
      console.error('Failed to create campaign:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Create New Campaign" size="lg">
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label="Campaign Name"
          placeholder="e.g., Q2 SaaS Outreach - Enterprise"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          required
        />
        <Select
          label="Channel"
          value={form.channel}
          onChange={(e) => setForm({ ...form, channel: e.target.value as ChannelType })}
          options={[
            { value: 'email', label: 'Email' },
            { value: 'linkedin', label: 'LinkedIn' },
            { value: 'phone', label: 'Phone' },
            { value: 'sms', label: 'SMS' },
            { value: 'whatsapp', label: 'WhatsApp' },
          ]}
        />
        <Input
          label="Daily Limit"
          type="number"
          value={form.daily_limit}
          onChange={(e) => setForm({ ...form, daily_limit: parseInt(e.target.value) || 0 })}
          min={1}
          max={1000}
          hint="Maximum messages per day"
        />
        <Textarea
          label="Message Template"
          placeholder="Hi {{first_name}}, I noticed..."
          value={form.message_template}
          onChange={(e) => setForm({ ...form, message_template: e.target.value })}
          hint="Use {{variable}} for personalization"
        />
        <div className="flex justify-end gap-3 pt-2">
          <Button variant="secondary" onClick={onClose} type="button">Cancel</Button>
          <Button type="submit" loading={loading} icon={<Plus size={14} />}>
            Create Campaign
          </Button>
        </div>
      </form>
    </Modal>
  );
}