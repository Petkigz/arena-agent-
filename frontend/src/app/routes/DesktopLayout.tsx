import { Outlet, useLocation } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import { motion } from 'framer-motion';
import { Sidebar } from '../../components/layout/Sidebar';
import { ContextPanel } from '../../components/layout/ContextPanel';
import { ConnectionBanner } from '../../components/ui/ConnectionBanner';
import { OfflineBanner } from '../../components/ui/OfflineBanner';

export function DesktopLayout() {
  const location = useLocation();

  return (
    <div className="h-screen flex flex-col bg-background-primary">
      <ConnectionBanner />
      <OfflineBanner />
      <div className="flex-1 flex overflow-hidden">
        {/* Left sidebar */}
        <Sidebar />

        {/* Main content area */}
        <main id="main-content" className="flex-1 flex flex-col overflow-hidden" tabIndex={-1}>
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
              className="flex-1 flex flex-col overflow-hidden"
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </main>

        {/* Right context panel */}
        <ContextPanel />
      </div>
    </div>
  );
}
