import { logger } from '../../services/logger';
import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertTriangle } from 'lucide-react';
import { Button } from './Button';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
  resetOnPropsChange?: boolean;
}

interface State {
  hasError: boolean;
  error?: Error;
  errorInfo?: ErrorInfo;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    logger.error('Uncaught error', error, { errorInfo });
    this.setState({ errorInfo });
    
    if (this.props.onError) {
      this.props.onError(error, errorInfo);
    }
  }

  public componentDidUpdate(prevProps: Props) {
    // Reset error state if props change and resetOnPropsChange is true
    if (this.props.resetOnPropsChange && this.state.hasError && prevProps.children !== this.props.children) {
      this.setState({ hasError: false, error: undefined, errorInfo: undefined });
    }
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: undefined, errorInfo: undefined });
  };

  private handleReload = () => {
    window.location.reload();
  };

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="min-h-screen bg-background-primary flex items-center justify-center p-4">
          <div className="max-w-md w-full bg-background-secondary rounded-lg p-6 text-center">
            <AlertTriangle className="w-12 h-12 text-accent-error mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-text-primary mb-2">
              Something went wrong
            </h2>
            <p className="text-text-secondary mb-4">
              {this.state.error?.message || 'An unexpected error occurred'}
            </p>
            
            {import.meta.env.MODE === 'development' && this.state.error && (
              <details className="mb-4 text-left">
                <summary className="cursor-pointer text-sm text-text-muted hover:text-text-primary">
                  Error Details
                </summary>
                <pre className="mt-2 p-3 bg-background-primary rounded text-xs text-text-muted overflow-auto max-h-48">
                  {this.state.error.stack}
                </pre>
              </details>
            )}
            
            <div className="flex gap-2">
              <Button onClick={this.handleReset} variant="secondary" className="flex-1">
                Try Again
              </Button>
              <Button onClick={this.handleReload} variant="primary" className="flex-1">
                Reload Page
              </Button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
