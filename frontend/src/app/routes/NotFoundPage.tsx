import { useNavigate } from 'react-router-dom';
import { Button } from '../../components/ui';
import { Home, AlertTriangle } from 'lucide-react';

export function NotFoundPage() {
  const navigate = useNavigate();

  return (
    <div className="h-full flex items-center justify-center bg-background-primary">
      <div className="max-w-md w-full px-6 py-8 text-center">
        <div className="mb-6">
          <AlertTriangle className="w-20 h-20 text-accent-warning mx-auto" />
        </div>
        
        <h1 className="text-6xl font-bold text-text-primary mb-4">404</h1>
        
        <h2 className="text-2xl font-semibold text-text-primary mb-3">
          Page Not Found
        </h2>
        
        <p className="text-text-secondary mb-8">
          The page you're looking for doesn't exist or has been moved.
        </p>
        
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Button
            variant="primary"
            onClick={() => navigate(-1)}
          >
            Go Back
          </Button>
          
          <Button
            variant="secondary"
            onClick={() => navigate('/')}
            className="flex items-center gap-2"
          >
            <Home className="w-4 h-4" />
            Home
          </Button>
        </div>
      </div>
    </div>
  );
}
