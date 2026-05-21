import { create } from 'zustand';

interface UIStore {
  sidebarOpen: boolean;
  sidebarCollapsed: boolean;
  activeModal: string | null;
  modalData: unknown;
  notifications: Notification[];
  
  toggleSidebar: () => void;
  toggleSidebarCollapse: () => void;
  openModal: (modal: string, data?: unknown) => void;
  closeModal: () => void;
  addNotification: (notification: Omit<Notification, 'id'>) => void;
  removeNotification: (id: string) => void;
}

interface Notification {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  message: string;
  duration?: number;
}

export const useUIStore = create<UIStore>((set) => ({
  sidebarOpen: true,
  sidebarCollapsed: false,
  activeModal: null,
  modalData: null,
  notifications: [],

  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  toggleSidebarCollapse: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  
  openModal: (modal, data = null) => set({ activeModal: modal, modalData: data }),
  closeModal: () => set({ activeModal: null, modalData: null }),
  
  addNotification: (notification) => {
    const id = Math.random().toString(36).substr(2, 9);
    set((state) => ({
      notifications: [...state.notifications, { ...notification, id }],
    }));
    if (notification.duration !== 0) {
      setTimeout(() => {
        set((state) => ({
          notifications: state.notifications.filter((n) => n.id !== id),
        }));
      }, notification.duration || 5000);
    }
  },
  
  removeNotification: (id) => set((state) => ({
    notifications: state.notifications.filter((n) => n.id !== id),
  })),
}));