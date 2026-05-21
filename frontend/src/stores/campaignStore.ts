import { create } from 'zustand';
import type { Campaign, CampaignStatus } from '@/types';

interface CampaignStore {
  campaigns: Campaign[];
  selectedCampaign: Campaign | null;
  loading: boolean;
  error: string | null;
  filter: CampaignStatus | 'all';
  
  setCampaigns: (campaigns: Campaign[]) => void;
  selectCampaign: (campaign: Campaign | null) => void;
  addCampaign: (campaign: Campaign) => void;
  updateCampaign: (id: string, data: Partial<Campaign>) => void;
  removeCampaign: (id: string) => void;
  setFilter: (filter: CampaignStatus | 'all') => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
}

export const useCampaignStore = create<CampaignStore>((set) => ({
  campaigns: [],
  selectedCampaign: null,
  loading: false,
  error: null,
  filter: 'all',

  setCampaigns: (campaigns) => set({ campaigns }),
  
  selectCampaign: (campaign) => set({ selectedCampaign: campaign }),
  
  addCampaign: (campaign) => set((state) => ({
    campaigns: [...state.campaigns, campaign],
  })),
  
  updateCampaign: (id, data) => set((state) => ({
    campaigns: state.campaigns.map((c) => c.id === id ? { ...c, ...data } : c),
    selectedCampaign: state.selectedCampaign?.id === id 
      ? { ...state.selectedCampaign, ...data } 
      : state.selectedCampaign,
  })),
  
  removeCampaign: (id) => set((state) => ({
    campaigns: state.campaigns.filter((c) => c.id !== id),
    selectedCampaign: state.selectedCampaign?.id === id ? null : state.selectedCampaign,
  })),
  
  setFilter: (filter) => set({ filter }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
}));