import { AnimatedSpinner, PulseDots } from '../animations/LoadingAnimations';

interface LoadingFallbackProps {
  message?: string;
}

export function LoadingFallback({ message = 'Loading...' }: LoadingFallbackProps) {
  return (
    <div className="h-full flex flex-col items-center justify-center bg-background-primary">
      <AnimatedSpinner size="xl" />
      <div className="mt-6 flex flex-col items-center gap-2">
        <p className="text-text-secondary text-sm">{message}</p>
        <PulseDots count={3} />
      </div>
    </div>
  );
}
