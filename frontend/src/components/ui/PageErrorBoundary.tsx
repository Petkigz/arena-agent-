import { ErrorBoundary } from './ErrorBoundary';
import { Button } from './Button';
import { AlertTriangle, Home } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import type { ReactNode, ErrorInfo } from 'react';
import { logger } from '../../services/logger';

interface PageErrorBoundaryProps {
  children: ReactNode;
  pageName: string;
}

export function PageErrorBoundary({ children, pageName }: PageErrorBoundaryProps) {
  const navigate = useNavigate();

  const handleError = (error: Error, errorInfo: ErrorInfo) => {
    logger.error(`Error in ${pageName}`, error, { 
      pageName,
      componentStack: errorInfo.componentStack 
    });
  };

  const handleGoHome = () => {
    navigate('/');
  };

  const fallback = (
    <div className="min-h-[60vh] flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-background-secondary rounded-lg p-6 text-center">
        <AlertTriangle className="w-12 h-12 text-accent-error mx-auto mb-4" />
        <h2 className="text-xl font-semibold text-text-primary mb-2">
          Page Error
        </h2>
        <p className="text-text-secondary mb-4">
          Something went wrong while loading this page.
        </p>
        <div className="flex gap-2">
          <Button 
            onClick={() => window.location.reload()} 
            variant="secondary" 
            className="flex-1"
          >
            Reload
          </Button>
          <Button 
            onClick={handleGoHome} 
            variant="primary" 
            className="flex-1"
          >
            <Home className="w-4 h-4 mr-2" />
            Go Home
          </Button>
        </div>
      </div>
    </div>
  );

  return (
    <ErrorBoundary 
      fallback={fallback} 
      onError={handleError}
      resetOnPropsChange={true}
    >
      {children}
    </ErrorBoundary>
  );
}
