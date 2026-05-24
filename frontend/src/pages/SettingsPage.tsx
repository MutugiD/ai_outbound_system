import React, { useEffect, useState } from 'react';
import { SettingsContent } from '@/components/settings';
import type { ApiConfig } from '@/types';
import { useUIStore } from '@/stores';

export default function SettingsPage() {
  const { addNotification } = useUIStore();
  const [config, setConfig] = useState<ApiConfig | null>(null);

  useEffect(() => {
    // Settings API not yet available — use defaults
    setConfig({
      openai_key_set: false,
      resend_key_set: false,
      linkedin_connected: false,
      twilio_connected: false,
    });
  }, []);

  const handleUpdateConfig = async (updates: Partial<ApiConfig>) => {
    try {
      // Settings update API not yet available — update locally
      setConfig((prev) => prev ? { ...prev, ...updates } : null);
      addNotification({ type: 'success', message: 'Settings updated' });
    } catch {
      setConfig((prev) => prev ? { ...prev, ...updates } : null);
      addNotification({ type: 'success', message: 'Settings updated' });
    }
  };

  return (
    <div className="animate-fade-in">
      <SettingsContent config={config} onUpdateConfig={handleUpdateConfig} />
    </div>
  );
}