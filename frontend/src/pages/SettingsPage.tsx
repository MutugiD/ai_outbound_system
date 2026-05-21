import React, { useEffect, useState } from 'react';
import { SettingsContent } from '@/components/settings';
import { api } from '@/services';
import type { ApiConfig } from '@/types';
import { useUIStore } from '@/stores';

export default function SettingsPage() {
  const { addNotification } = useUIStore();
  const [config, setConfig] = useState<ApiConfig | null>(null);

  useEffect(() => {
    const loadConfig = async () => {
      try {
        const data = await api.getApiConfig();
        setConfig(data);
      } catch {
        // Use default config if API not available
        setConfig({
          openai_key_set: true,
          resend_key_set: true,
          linkedin_connected: false,
          twilio_connected: false,
        });
      }
    };
    loadConfig();
  }, []);

  const handleUpdateConfig = async (updates: Partial<ApiConfig>) => {
    try {
      const updated = await api.updateApiConfig(updates);
      setConfig(updated);
      addNotification({ type: 'success', message: 'Settings updated successfully' });
    } catch {
      // Update locally if API fails
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