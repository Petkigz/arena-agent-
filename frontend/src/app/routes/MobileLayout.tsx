import { Outlet } from 'react-router-dom';
import { BottomNavigation } from '../../components/layout/BottomNavigation';
import { ConnectionBanner } from '../../components/ui/ConnectionBanner';

export function MobileLayout() {
  return (
    <div className="h-screen flex flex-col bg-background-primary">
      <ConnectionBanner />
      {/* Main content area */}
      <main id="main-content" className="flex-1 overflow-hidden" tabIndex={-1}>
        <Outlet />
      </main>

      {/* Bottom navigation */}
      <BottomNavigation />
    </div>
  );
}
