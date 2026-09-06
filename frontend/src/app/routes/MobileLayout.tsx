import { Outlet, useLocation } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { BottomNavigation } from '../../components/layout/BottomNavigation';
import { ConnectionBanner } from '../../components/ui/ConnectionBanner';
import { OfflineBanner } from '../../components/ui/OfflineBanner';
import { MOTION } from '../../design/tokens';

export function MobileLayout() {
  const location = useLocation();

  return (
    <div className="h-screen flex flex-col bg-background-primary">
      <ConnectionBanner />
      <OfflineBanner />
      {/* Main content area */}
      <main id="main-content" className="flex-1 overflow-hidden" tabIndex={-1}>
        <AnimatePresence mode="wait">
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: MOTION.base_ms / 1000, ease: 'easeOut' }}
            className="h-full"
          >
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </main>

      {/* Bottom navigation */}
      <BottomNavigation />
    </div>
  );
}
