import { create } from 'zustand';
import type { Lead, LeadStatus } from '@/types';

interface LeadStore {
  leads: Lead[];
  selectedLead: Lead | null;
  loading: boolean;
  error: string | null;
  searchQuery: string;
  statusFilter: LeadStatus | 'all';
  
  setLeads: (leads: Lead[]) => void;
  selectLead: (lead: Lead | null) => void;
  addLead: (lead: Lead) => void;
  updateLead: (id: string, data: Partial<Lead>) => void;
  removeLead: (id: string) => void;
  setSearchQuery: (query: string) => void;
  setStatusFilter: (status: LeadStatus | 'all') => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
}

export const useLeadStore = create<LeadStore>((set) => ({
  leads: [],
  selectedLead: null,
  loading: false,
  error: null,
  searchQuery: '',
  statusFilter: 'all',

  setLeads: (leads) => set({ leads }),
  selectLead: (lead) => set({ selectedLead: lead }),
  addLead: (lead) => set((state) => ({ leads: [...state.leads, lead] })),
  updateLead: (id, data) => set((state) => ({
    leads: state.leads.map((l) => l.id === id ? { ...l, ...data } : l),
    selectedLead: state.selectedLead?.id === id ? { ...state.selectedLead, ...data } : state.selectedLead,
  })),
  removeLead: (id) => set((state) => ({
    leads: state.leads.filter((l) => l.id !== id),
    selectedLead: state.selectedLead?.id === id ? null : state.selectedLead,
  })),
  setSearchQuery: (searchQuery) => set({ searchQuery }),
  setStatusFilter: (statusFilter) => set({ statusFilter }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
}));