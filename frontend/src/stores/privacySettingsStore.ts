import { logger } from '../services/logger';
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface PrivacySettingsState {
  // Data retention
  dataRetentionDays: number;
  autoDeleteOldData: boolean;
  
  // Telemetry
  enableTelemetry: boolean;
  shareUsageStats: boolean;
  
  // Security
  requireApprovalForSensitiveActions: boolean;
  logAllActions: boolean;
  
  // Actions
  setDataRetentionDays: (days: number) => void;
  setAutoDeleteOldData: (enabled: boolean) => void;
  setEnableTelemetry: (enabled: boolean) => void;
  setShareUsageStats: (enabled: boolean) => void;
  setRequireApprovalForSensitiveActions: (enabled: boolean) => void;
  setLogAllActions: (enabled: boolean) => void;
  
  // Backup/Restore
  exportSettings: () => string;
  importSettings: (data: string) => boolean;
}

export const usePrivacySettingsStore = create<PrivacySettingsState>()(
  persist(
    (set, get) => ({
      // Data retention
      dataRetentionDays: 90,
      autoDeleteOldData: true,
      
      // Telemetry
      enableTelemetry: false,
      shareUsageStats: false,
      
      // Security
      requireApprovalForSensitiveActions: true,
      logAllActions: true,
      
      // Actions
      setDataRetentionDays: (days) => set({ dataRetentionDays: days }),
      setAutoDeleteOldData: (enabled) => set({ autoDeleteOldData: enabled }),
      setEnableTelemetry: (enabled) => set({ enableTelemetry: enabled }),
      setShareUsageStats: (enabled) => set({ shareUsageStats: enabled }),
      setRequireApprovalForSensitiveActions: (enabled) => set({ requireApprovalForSensitiveActions: enabled }),
      setLogAllActions: (enabled) => set({ logAllActions: enabled }),
      
      // Backup/Restore
      exportSettings: () => {
        const state = get();
        const exportData = {
          dataRetentionDays: state.dataRetentionDays,
          autoDeleteOldData: state.autoDeleteOldData,
          enableTelemetry: state.enableTelemetry,
          shareUsageStats: state.shareUsageStats,
          requireApprovalForSensitiveActions: state.requireApprovalForSensitiveActions,
          logAllActions: state.logAllActions,
          exportedAt: new Date().toISOString(),
        };
        return JSON.stringify(exportData, null, 2);
      },
      
      importSettings: (data: string) => {
        try {
          const imported = JSON.parse(data);
          set({
            dataRetentionDays: imported.dataRetentionDays ?? 90,
            autoDeleteOldData: imported.autoDeleteOldData ?? true,
            enableTelemetry: imported.enableTelemetry ?? false,
            shareUsageStats: imported.shareUsageStats ?? false,
            requireApprovalForSensitiveActions: imported.requireApprovalForSensitiveActions ?? true,
            logAllActions: imported.logAllActions ?? true,
          });
          return true;
        } catch (error) {
          logger.error('Failed to import settings:', error);
          return false;
        }
      },
    }),
    {
      name: 'arena-privacy-settings',
    }
  )
);
