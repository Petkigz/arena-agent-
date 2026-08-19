import { Outlet } from 'react-router-dom';
import { Sidebar } from '../../components/layout/Sidebar';
import { ContextPanel } from '../../components/layout/ContextPanel';
import { ConnectionBanner } from '../../components/ui/ConnectionBanner';

export function DesktopLayout() {
  return (
    <div className="h-screen flex flex-col bg-background-primary">
      <ConnectionBanner />
      <div className="flex-1 flex overflow-hidden">
        {/* Left sidebar */}
        <Sidebar />

        {/* Main content area */}
        <main id="main-content" className="flex-1 flex flex-col overflow-hidden" tabIndex={-1}>
          <Outlet />
        </main>

        {/* Right context panel */}
        <ContextPanel />
      </div>
    </div>
  );
}
