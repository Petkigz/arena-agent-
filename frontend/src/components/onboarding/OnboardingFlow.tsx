import { useEffect } from 'react';
import { useOnboardingStore, type OnboardingStep } from '../../stores/onboardingStore';
import { WelcomeScreen } from './steps/WelcomeScreen';
import { WakeWordTraining } from './steps/WakeWordTraining';
import { PermissionRequests } from './steps/PermissionRequests';
import { DevicePairing } from './steps/DevicePairing';
import { TutorialConversation } from './steps/TutorialConversation';
import { OnboardingComplete } from './steps/OnboardingComplete';
import { useMediaQuery } from '../../hooks/useMediaQuery';

interface OnboardingFlowProps {
  onComplete: () => void;
}

export function OnboardingFlow({ onComplete }: OnboardingFlowProps) {
  const { currentStep, completeStep, setCurrentStep, finishOnboarding } = useOnboardingStore();
  const isMobile = useMediaQuery('(max-width: 768px)');

  const steps: OnboardingStep[] = isMobile
    ? ['welcome', 'wake-word', 'permissions', 'pairing', 'tutorial', 'complete']
    : ['welcome', 'wake-word', 'permissions', 'tutorial', 'complete'];

  const currentIndex = steps.indexOf(currentStep);

  const handleNext = () => {
    completeStep(currentStep);
    const nextIndex = currentIndex + 1;
    if (nextIndex < steps.length) {
      setCurrentStep(steps[nextIndex]);
    }
  };

  const handleBack = () => {
    const prevIndex = currentIndex - 1;
    if (prevIndex >= 0) {
      setCurrentStep(steps[prevIndex]);
    }
  };

  const handleFinish = () => {
    finishOnboarding();
    onComplete();
  };

  const handleSkip = () => {
    finishOnboarding();
    onComplete();
  };

  useEffect(() => {
    // Scroll to top on step change
    window.scrollTo(0, 0);
  }, [currentStep]);

  return (
    <div className="min-h-screen bg-background-primary">
      {/* Progress bar */}
      <div className="fixed top-0 left-0 right-0 h-1 bg-background-surface z-50">
        <div
          className="h-full bg-accent-primary transition-all duration-300"
          style={{ width: `${((currentIndex + 1) / steps.length) * 100}%` }}
        />
      </div>

      {/* Step content */}
      <div className="pt-8">
        {currentStep === 'welcome' && (
          <WelcomeScreen onNext={handleNext} onSkip={handleSkip} />
        )}
        {currentStep === 'wake-word' && (
          <WakeWordTraining onNext={handleNext} onBack={handleBack} onSkip={handleSkip} />
        )}
        {currentStep === 'permissions' && (
          <PermissionRequests onNext={handleNext} onBack={handleBack} onSkip={handleSkip} />
        )}
        {currentStep === 'pairing' && isMobile && (
          <DevicePairing onNext={handleNext} onBack={handleBack} onSkip={handleSkip} />
        )}
        {currentStep === 'tutorial' && (
          <TutorialConversation onNext={handleNext} onBack={handleBack} onSkip={handleSkip} />
        )}
        {currentStep === 'complete' && (
          <OnboardingComplete onFinish={handleFinish} />
        )}
      </div>
    </div>
  );
}
