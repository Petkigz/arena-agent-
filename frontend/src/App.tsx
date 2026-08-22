import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Suspense, lazy, useEffect, useState } from 'react';
import { Toaster } from 'react-hot-toast';
import { MotionConfig } from 'framer-motion';
import { ErrorBoundary, PageErrorBoundary, LoadingFallback, KeyboardShortcutsModal, HelpCenter, SkipLink } from './components/ui';
import { OnboardingFlow } from './components/onboarding';
import {
  MobileLayout,
  DesktopLayout,
} from './app/routes';
import { useMediaQuery } from './hooks/useMediaQuery';
import { useThemeApplication } from './utils/themeApplication';
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts';
import { useAccessibility, useSkipToContent } from './hooks/useAccessibility';
import { useConversationSync } from './hooks/useConversationSync';
import { useOnboardingStore } from './stores/onboardingStore';
import { useAppearanceSettingsStore } from './stores/appearanceSettingsStore';
import { webSocketService } from './services/websocket';
import { registerServiceWorker } from './utils/serviceWorker';

// Lazy load all pages
const BeaniePage = lazy(() => import('./app/routes/BeaniePage').then(m => ({ default: m.BeaniePage })));
const ChatPage = lazy(() => import('./app/routes/ChatPage').then(m => ({ default: m.ChatPage })));
const PansophyPage = lazy(() => import('./app/routes/PansophyPage').then(m => ({ default: m.PansophyPage })));
const FilesPage = lazy(() => import('./app/routes/FilesPage').then(m => ({ default: m.FilesPage })));
const CodeExecutionPage = lazy(() => import('./app/routes/CodeExecutionPage').then(m => ({ default: m.CodeExecutionPage })));
const ImagesPage = lazy(() => import('./app/routes/ImagesPage').then(m => ({ default: m.ImagesPage })));
const SettingsPage = lazy(() => import('./app/routes/SettingsPage').then(m => ({ default: m.SettingsPage })));
const VoiceSettingsPage = lazy(() => import('./app/routes/VoiceSettingsPage').then(m => ({ default: m.VoiceSettingsPage })));
const ModelSettingsPage = lazy(() => import('./app/routes/ModelSettingsPage').then(m => ({ default: m.ModelSettingsPage })));
const PrivacySettingsPage = lazy(() => import('./app/routes/PrivacySettingsPage').then(m => ({ default: m.PrivacySettingsPage })));
const AppearanceSettingsPage = lazy(() => import('./app/routes/AppearanceSettingsPage').then(m => ({ default: m.AppearanceSettingsPage })));
const AccessibilitySettingsPage = lazy(() => import('./app/routes/AccessibilitySettingsPage').then(m => ({ default: m.AccessibilitySettingsPage })));
const ProjectDetailPage = lazy(() => import('./app/routes/ProjectDetailPage').then(m => ({ default: m.ProjectDetailPage })));
const NotFoundPage = lazy(() => import('./app/routes/NotFoundPage').then(m => ({ default: m.NotFoundPage })));

/**
 * Inner app component that runs inside the Router context.
 * All hooks that use useNavigate/useLocation must be here.
 */
function AppContent() {
  const isMobile = useMediaQuery('(max-width: 768px)');
  const { shortcuts, showShortcutsModal, setShowShortcutsModal } = useKeyboardShortcuts();
  const { completed: onboardingCompleted } = useOnboardingStore();
  const [showHelpCenter, setShowHelpCenter] = useState(false);
  const prefersReducedMotion = useMediaQuery('(prefers-reduced-motion: reduce)');
  const showAnimations = useAppearanceSettingsStore((s) => s.showAnimations);

  // Apply theme, font, compact mode, animations, and contrast settings to the DOM
  useThemeApplication();
  
  // Apply accessibility settings
  useAccessibility();
  
  // Enable skip to content link
  useSkipToContent();

  // Sync conversations with the backend (SQLite-persisted history)
  useConversationSync();

  // Connect WebSocket on app startup (URL resolved from env or hostname)
  useEffect(() => {
    try {
      webSocketService.connect();
    } catch (error) {
      console.warn('WebSocket connection failed (non-fatal):', error);
    }
    return () => {
      try {
        webSocketService.disconnect();
      } catch (error) {
        console.warn('WebSocket disconnect failed (non-fatal):', error);
      }
    };
  }, []);

  // Register service worker for offline support
  useEffect(() => {
    registerServiceWorker();
  }, []);

  // Show tutorial on first visit after onboarding
  useEffect(() => {
    if (onboardingCompleted && !localStorage.getItem('arena-tutorial-completed')) {
      setTimeout(() => {
        setShowHelpCenter(true);
      }, 1000);
    }
  }, [onboardingCompleted]);

  // Show onboarding flow if not completed
  if (!onboardingCompleted) {
    return (
      <>
        <OnboardingFlow onComplete={() => {
          // Onboarding completed, app will re-render with main interface
        }} />
        <Toaster
          position="top-right"
          toastOptions={{
            style: {
              background: 'var(--color-background-secondary)',
              color: 'var(--color-text-primary)',
              border: '1px solid var(--color-background-surface)',
            },
          }}
        />
      </>
    );
  }

  return (
    <>
      {/* Configure Framer Motion to respect reduced motion preferences */}
      <MotionConfig reducedMotion={prefersReducedMotion || !showAnimations ? 'always' : 'never'}>
      {/* Skip to content link for screen readers */}
      <SkipLink />
      
      <Suspense fallback={<LoadingFallback message="Loading Arena..." />}>
        <Routes>
        {/* Mobile routes */}
        {isMobile ? (
          <Route element={<MobileLayout />}>
            <Route path="/beanie" element={<PageErrorBoundary pageName="BeaniePage"><BeaniePage /></PageErrorBoundary>} />
            <Route path="/chat" element={<PageErrorBoundary pageName="ChatPage"><ChatPage /></PageErrorBoundary>} />
            <Route path="/pansophy" element={<PageErrorBoundary pageName="PansophyPage"><PansophyPage /></PageErrorBoundary>} />
            <Route path="/files" element={<PageErrorBoundary pageName="FilesPage"><FilesPage /></PageErrorBoundary>} />
            <Route path="/images" element={<PageErrorBoundary pageName="ImagesPage"><ImagesPage /></PageErrorBoundary>} />
            <Route path="/code" element={<PageErrorBoundary pageName="CodeExecutionPage"><CodeExecutionPage /></PageErrorBoundary>} />
            <Route path="/settings" element={<PageErrorBoundary pageName="SettingsPage"><SettingsPage /></PageErrorBoundary>} />
            <Route path="/settings/voice" element={<PageErrorBoundary pageName="VoiceSettingsPage"><VoiceSettingsPage /></PageErrorBoundary>} />
            <Route path="/settings/models" element={<PageErrorBoundary pageName="ModelSettingsPage"><ModelSettingsPage /></PageErrorBoundary>} />
            <Route path="/settings/privacy" element={<PageErrorBoundary pageName="PrivacySettingsPage"><PrivacySettingsPage /></PageErrorBoundary>} />
            <Route path="/settings/appearance" element={<PageErrorBoundary pageName="AppearanceSettingsPage"><AppearanceSettingsPage /></PageErrorBoundary>} />
            <Route path="/settings/accessibility" element={<PageErrorBoundary pageName="AccessibilitySettingsPage"><AccessibilitySettingsPage /></PageErrorBoundary>} />
            <Route path="/projects/:projectId" element={<PageErrorBoundary pageName="ProjectDetailPage"><ProjectDetailPage /></PageErrorBoundary>} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        ) : (
          /* Desktop routes */
          <Route element={<DesktopLayout />}>
            <Route path="/beanie" element={<PageErrorBoundary pageName="BeaniePage"><BeaniePage /></PageErrorBoundary>} />
            <Route path="/chat" element={<PageErrorBoundary pageName="ChatPage"><ChatPage /></PageErrorBoundary>} />
            <Route path="/pansophy" element={<PageErrorBoundary pageName="PansophyPage"><PansophyPage /></PageErrorBoundary>} />
            <Route path="/files" element={<PageErrorBoundary pageName="FilesPage"><FilesPage /></PageErrorBoundary>} />
            <Route path="/images" element={<PageErrorBoundary pageName="ImagesPage"><ImagesPage /></PageErrorBoundary>} />
            <Route path="/code" element={<PageErrorBoundary pageName="CodeExecutionPage"><CodeExecutionPage /></PageErrorBoundary>} />
            <Route path="/settings" element={<PageErrorBoundary pageName="SettingsPage"><SettingsPage /></PageErrorBoundary>} />
            <Route path="/settings/voice" element={<PageErrorBoundary pageName="VoiceSettingsPage"><VoiceSettingsPage /></PageErrorBoundary>} />
            <Route path="/settings/models" element={<PageErrorBoundary pageName="ModelSettingsPage"><ModelSettingsPage /></PageErrorBoundary>} />
            <Route path="/settings/privacy" element={<PageErrorBoundary pageName="PrivacySettingsPage"><PrivacySettingsPage /></PageErrorBoundary>} />
            <Route path="/settings/appearance" element={<PageErrorBoundary pageName="AppearanceSettingsPage"><AppearanceSettingsPage /></PageErrorBoundary>} />
            <Route path="/settings/accessibility" element={<PageErrorBoundary pageName="AccessibilitySettingsPage"><AccessibilitySettingsPage /></PageErrorBoundary>} />
            <Route path="/projects/:projectId" element={<PageErrorBoundary pageName="ProjectDetailPage"><ProjectDetailPage /></PageErrorBoundary>} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        )}
        </Routes>
      </Suspense>
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: 'var(--color-background-secondary)',
            color: 'var(--color-text-primary)',
            border: '1px solid var(--color-background-surface)',
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
      </MotionConfig>
    </>
  );
}

/**
 * Root App component.
 * BrowserRouter is at the top level so ALL hooks (including useNavigate)
 * have access to the Router context regardless of which screen is shown.
 */
function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <AppContent />
      </BrowserRouter>
    </ErrorBoundary>
  );
}

export default App;
