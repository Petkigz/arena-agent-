import { Spinner } from './Spinner';

interface LoadingFallbackProps {
  message?: string;
}

export function LoadingFallback({ message = 'Loading...' }: LoadingFallbackProps) {
  return (
    <div className="h-full flex flex-col items-center justify-center bg-background-primary">
      <Spinner size="lg" />
      <p className="mt-4 text-text-secondary text-sm">{message}</p>
    </div>
  );
}
