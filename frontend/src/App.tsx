import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Suspense, useEffect, useState } from 'react';
import { Toaster } from 'react-hot-toast';
import { ErrorBoundary, LoadingFallback, KeyboardShortcutsModal, HelpCenter } from './components/ui';
import { OnboardingFlow } from './components/onboarding';
import {
  MobileLayout,
  DesktopLayout,
  BeaniePage,
  ChatPage,
  PansophyPage,
  FilesPage,
  CodeExecutionPage,
  SettingsPage,
  VoiceSettingsPage,
  ModelSettingsPage,
  PrivacySettingsPage,
  AppearanceSettingsPage,
  AccessibilitySettingsPage,
  ProjectDetailPage,
  NotFoundPage,
} from './app/routes';
import { useMediaQuery } from './hooks/useMediaQuery';
import { useThemeApplication } from './utils/themeApplication';
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts';
import { useAccessibility, useSkipToContent } from './hooks/useAccessibility';
import { useOnboardingStore } from './stores/onboardingStore';
import { webSocketService } from './services/websocket';

function App() {
  const isMobile = useMediaQuery('(max-width: 768px)');
  const { shortcuts, showShortcutsModal, setShowShortcutsModal } = useKeyboardShortcuts();
  const { completed: onboardingCompleted } = useOnboardingStore();
  const [showHelpCenter, setShowHelpCenter] = useState(false);

  // Apply theme, font, compact mode, animations, and contrast settings to the DOM
  useThemeApplication();
  
  // Apply accessibility settings
  useAccessibility();
  
  // Enable skip to content link
  useSkipToContent();

  // Connect WebSocket on app startup
  useEffect(() => {
    const wsUrl = `ws://${window.location.hostname}:8000/ws`;
    webSocketService.connect(wsUrl);
    return () => {
      webSocketService.disconnect();
    };
  }, []);

  // Show tutorial on first visit after onboarding
  useEffect(() => {
    if (onboardingCompleted && !localStorage.getItem('arena-tutorial-completed')) {
      // Delay showing tutorial to let the app render
      setTimeout(() => {
        setShowHelpCenter(true);
      }, 1000);
    }
  }, [onboardingCompleted]);

  // Show onboarding flow if not completed
  if (!onboardingCompleted) {
    return (
      <ErrorBoundary>
        <OnboardingFlow onComplete={() => {
          // Onboarding completed, app will re-render with main interface
        }} />
      </ErrorBoundary>
    );
  }

  return (
    <ErrorBoundary>
      {/* Skip to content link for screen readers */}
      <a href="#main-content" className="skip-to-content">
        Skip to main content
      </a>
      
      <BrowserRouter>
        <Suspense fallback={<LoadingFallback message="Loading Arena..." />}>
          <Routes>
          {/* Mobile routes */}
          {isMobile ? (
            <Route element={<MobileLayout />}>
              <Route path="/beanie" element={<BeaniePage />} />
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/pansophy" element={<PansophyPage />} />
              <Route path="/files" element={<FilesPage />} />
              <Route path="/code" element={<CodeExecutionPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/settings/voice" element={<VoiceSettingsPage />} />
              <Route path="/settings/models" element={<ModelSettingsPage />} />
              <Route path="/settings/privacy" element={<PrivacySettingsPage />} />
              <Route path="/settings/appearance" element={<AppearanceSettingsPage />} />
              <Route path="/settings/accessibility" element={<AccessibilitySettingsPage />} />
              <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
              <Route path="*" element={<NotFoundPage />} />
            </Route>
          ) : (
            /* Desktop routes */
            <Route element={<DesktopLayout />}>
              <Route path="/beanie" element={<BeaniePage />} />
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/pansophy" element={<PansophyPage />} />
              <Route path="/files" element={<FilesPage />} />
              <Route path="/code" element={<CodeExecutionPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/settings/voice" element={<VoiceSettingsPage />} />
              <Route path="/settings/models" element={<ModelSettingsPage />} />
              <Route path="/settings/privacy" element={<PrivacySettingsPage />} />
              <Route path="/settings/appearance" element={<AppearanceSettingsPage />} />
              <Route path="/settings/accessibility" element={<AccessibilitySettingsPage />} />
              <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
              <Route path="*" element={<NotFoundPage />} />
            </Route>
          )}
          </Routes>
        </Suspense>
      </BrowserRouter>
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: '#1E293B',
            color: '#F1F5F9',
          },
        }}
      />
      <KeyboardShortcutsModal
        isOpen={showShortcutsModal}
        onClose={() => setShowShortcutsModal(false)}
        shortcuts={shortcuts}
      />
      <HelpCenter
        isOpen={showHelpCenter}
        onClose={() => setShowHelpCenter(false)}
      />
    </ErrorBoundary>
  );
}

export default App;
