import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface LayoutStoreState {
  sidebarCollapsed: boolean;
  contextPanelCollapsed: boolean;
  
  // Actions
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleContextPanel: () => void;
  setContextPanelCollapsed: (collapsed: boolean) => void;
}

export const useLayoutStore = create<LayoutStoreState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      contextPanelCollapsed: false,
      
      toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
      setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
      toggleContextPanel: () => set((state) => ({ contextPanelCollapsed: !state.contextPanelCollapsed })),
      setContextPanelCollapsed: (collapsed) => set({ contextPanelCollapsed: collapsed }),
    }),
    {
      name: 'arena-layout',
    }
  )
);
