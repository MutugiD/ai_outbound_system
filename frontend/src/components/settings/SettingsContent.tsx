import React, { useState } from 'react';
import { Card, CardHeader, CardTitle, Badge, Button, Input } from '@/components/common';
import type { ApiConfig } from '@/types';
import { Key, Globe, Smartphone, Webhook, Eye, EyeOff, Check, X, Save } from 'lucide-react';

// ── SettingsContent ─────────────────────────────────────────────────────────
interface SettingsContentProps {
  config: ApiConfig | null;
  onUpdateConfig: (updates: Partial<ApiConfig>) => void;
}

export function SettingsContent({ config, onUpdateConfig }: SettingsContentProps) {
  const [openaiKey, setOpenaiKey] = useState('');
  const [resendKey, setResendKey] = useState('');
  const [webhookUrl, setWebhookUrl] = useState(config?.webhook_url || '');
  const [showOpenaiKey, setShowOpenaiKey] = useState(false);
  const [showResendKey, setShowResendKey] = useState(false);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      const updates: Partial<ApiConfig> = {};
      if (openaiKey) updates.openai_key_set = true;
      if (resendKey) updates.resend_key_set = true;
      if (webhookUrl) updates.webhook_url = webhookUrl;
      await onUpdateConfig(updates);
      setOpenaiKey('');
      setResendKey('');
    } finally {
      setSaving(false);
    }
  };

  const handleConnectLinkedIn = () => {
    onUpdateConfig({ linkedin_connected: true });
  };

  const handleConnectTwilio = () => {
    onUpdateConfig({ twilio_connected: true });
  };

  const StatusIcon = ({ connected }: { connected: boolean }) => (
    connected
      ? <Check size={14} className="text-emerald-400" />
      : <X size={14} className="text-coral-400" />
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-navy-50">Settings</h2>
        <Button icon={<Save size={14} />} loading={saving} onClick={handleSave}>
          Save Changes
        </Button>
      </div>

      {/* API Keys */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Key size={18} className="text-gold-400" />
            <CardTitle>API Keys</CardTitle>
          </div>
        </CardHeader>
        <div className="space-y-4">
          <div>
            <label className="text-sm font-medium text-navy-200 mb-1.5 block">OpenAI API Key</label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <input
                  type={showOpenaiKey ? 'text' : 'password'}
                  placeholder={config?.openai_key_set ? '•••••••• (key is set)' : 'sk-...'}
                  value={openaiKey}
                  onChange={(e) => setOpenaiKey(e.target.value)}
                  className="w-full px-3 py-2 bg-navy-800 border border-navy-700/30 rounded-lg text-sm text-navy-100 placeholder-navy-500 focus:outline-none focus:border-gold-500/50 pr-10"
                />
                <button
                  onClick={() => setShowOpenaiKey(!showOpenaiKey)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-navy-400 hover:text-navy-200"
                >
                  {showOpenaiKey ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
              <StatusIcon connected={config?.openai_key_set ?? false} />
            </div>
          </div>

          <div>
            <label className="text-sm font-medium text-navy-200 mb-1.5 block">Resend API Key</label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <input
                  type={showResendKey ? 'text' : 'password'}
                  placeholder={config?.resend_key_set ? '•••••••• (key is set)' : 're_...'}
                  value={resendKey}
                  onChange={(e) => setResendKey(e.target.value)}
                  className="w-full px-3 py-2 bg-navy-800 border border-navy-700/30 rounded-lg text-sm text-navy-100 placeholder-navy-500 focus:outline-none focus:border-gold-500/50 pr-10"
                />
                <button
                  onClick={() => setShowResendKey(!showResendKey)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-navy-400 hover:text-navy-200"
                >
                  {showResendKey ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
              <StatusIcon connected={config?.resend_key_set ?? false} />
            </div>
          </div>
        </div>
      </Card>

      {/* Integrations */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Globe size={18} className="text-gold-400" />
            <CardTitle>Integrations</CardTitle>
          </div>
        </CardHeader>
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-navy-800 text-navy-300">
                <Globe size={16} />
              </div>
              <div>
                <p className="text-sm font-medium text-navy-100">LinkedIn</p>
                <p className="text-xs text-navy-400">Connect for LinkedIn outreach</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <StatusIcon connected={config?.linkedin_connected ?? false} />
              {config?.linkedin_connected ? (
                <Badge variant="success" size="sm">Connected</Badge>
              ) : (
                <Button variant="secondary" size="sm" onClick={handleConnectLinkedIn}>Connect</Button>
              )}
            </div>
          </div>

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-navy-800 text-navy-300">
                <Smartphone size={16} />
              </div>
              <div>
                <p className="text-sm font-medium text-navy-100">Twilio</p>
                <p className="text-xs text-navy-400">Connect for SMS and phone calls</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <StatusIcon connected={config?.twilio_connected ?? false} />
              {config?.twilio_connected ? (
                <Badge variant="success" size="sm">Connected</Badge>
              ) : (
                <Button variant="secondary" size="sm" onClick={handleConnectTwilio}>Connect</Button>
              )}
            </div>
          </div>
        </div>
      </Card>

      {/* Webhook */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Webhook size={18} className="text-gold-400" />
            <CardTitle>Webhooks</CardTitle>
          </div>
        </CardHeader>
        <div>
          <label className="text-sm font-medium text-navy-200 mb-1.5 block">Webhook URL</label>
          <input
            type="url"
            placeholder="https://your-server.com/webhook"
            value={webhookUrl}
            onChange={(e) => setWebhookUrl(e.target.value)}
            className="w-full px-3 py-2 bg-navy-800 border border-navy-700/30 rounded-lg text-sm text-navy-100 placeholder-navy-500 focus:outline-none focus:border-gold-500/50"
          />
          <p className="text-xs text-navy-500 mt-1">Receive notifications for events like replies, meetings, and deal closures</p>
        </div>
      </Card>
    </div>
  );
}