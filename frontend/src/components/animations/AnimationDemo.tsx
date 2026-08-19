import { useState } from 'react';
import { motion } from 'framer-motion';
import {
  FadeIn,
  SlideUp,
  SlideDown,
  SlideLeft,
  SlideRight,
  ScaleIn,
  StaggerList,
  StaggerItem,
  InteractiveButton,
  InteractiveCard,
  AnimatedSpinner,
  PulseDots,
  BouncingDots,
  SkeletonLoader,
  TypingIndicator,
  ProgressBar,
} from './index';

export function AnimationDemo() {
  const [progress, setProgress] = useState(0);
  const [showCard, setShowCard] = useState(true);

  return (
    <div className="p-8 space-y-12 max-w-4xl mx-auto">
      <h1 className="text-3xl font-bold text-text-primary mb-8">Animation System Demo</h1>

      {/* Page Transitions */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold text-text-primary">Page Transitions</h2>
        <p className="text-text-secondary">Smooth fade and slide transitions between pages</p>
        <div className="bg-background-secondary p-6 rounded-lg">
          <FadeIn>
            <p className="text-text-primary">This content fades in smoothly</p>
          </FadeIn>
        </div>
      </section>

      {/* Directional Animations */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold text-text-primary">Directional Animations</h2>
        <div className="grid grid-cols-2 gap-4">
          <SlideUp>
            <InteractiveCard>
              <p className="text-text-primary">Slide Up</p>
            </InteractiveCard>
          </SlideUp>
          <SlideDown>
            <InteractiveCard>
              <p className="text-text-primary">Slide Down</p>
            </InteractiveCard>
          </SlideDown>
          <SlideLeft>
            <InteractiveCard>
              <p className="text-text-primary">Slide Left</p>
            </InteractiveCard>
          </SlideLeft>
          <SlideRight>
            <InteractiveCard>
              <p className="text-text-primary">Slide Right</p>
            </InteractiveCard>
          </SlideRight>
        </div>
      </section>

      {/* Scale Animation */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold text-text-primary">Scale Animation</h2>
        <ScaleIn>
          <InteractiveCard>
            <p className="text-text-primary">This card scales in smoothly</p>
          </InteractiveCard>
        </ScaleIn>
      </section>

      {/* Stagger List */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold text-text-primary">Stagger List</h2>
        <p className="text-text-secondary">Items animate in sequence with staggered delays</p>
        <StaggerList className="space-y-2">
          {[1, 2, 3, 4, 5].map((item) => (
            <StaggerItem key={item}>
              <InteractiveCard>
                <p className="text-text-primary">List Item {item}</p>
              </InteractiveCard>
            </StaggerItem>
          ))}
        </StaggerList>
      </section>

      {/* Interactive Elements */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold text-text-primary">Interactive Elements</h2>
        <p className="text-text-secondary">Hover and tap for micro-interactions</p>
        <div className="flex gap-4">
          <InteractiveButton className="px-4 py-2 bg-accent-primary text-white rounded-lg">
            Hover & Tap Me
          </InteractiveButton>
          <InteractiveButton className="px-4 py-2 bg-background-surface text-text-primary rounded-lg">
            Secondary Button
          </InteractiveButton>
        </div>
      </section>

      {/* Toggle Animation */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold text-text-primary">Toggle Animation</h2>
        <InteractiveButton
          onClick={() => setShowCard(!showCard)}
          className="px-4 py-2 bg-accent-primary text-white rounded-lg"
        >
          {showCard ? 'Hide Card' : 'Show Card'}
        </InteractiveButton>
        <motion.div
          initial={false}
          animate={{ height: showCard ? 'auto' : 0, opacity: showCard ? 1 : 0 }}
          transition={{ duration: 0.3 }}
          className="overflow-hidden"
        >
          <InteractiveCard>
            <p className="text-text-primary">This card animates in and out smoothly</p>
          </InteractiveCard>
        </motion.div>
      </section>

      {/* Loading Animations */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold text-text-primary">Loading Animations</h2>
        
        <div className="space-y-6">
          <div>
            <h3 className="text-lg font-medium text-text-primary mb-2">Animated Spinner</h3>
            <div className="flex gap-4 items-center">
              <AnimatedSpinner size="sm" />
              <AnimatedSpinner size="md" />
              <AnimatedSpinner size="lg" />
              <AnimatedSpinner size="xl" />
            </div>
          </div>

          <div>
            <h3 className="text-lg font-medium text-text-primary mb-2">Pulse Dots</h3>
            <PulseDots count={3} />
          </div>

          <div>
            <h3 className="text-lg font-medium text-text-primary mb-2">Bouncing Dots</h3>
            <BouncingDots count={3} />
          </div>

          <div>
            <h3 className="text-lg font-medium text-text-primary mb-2">Typing Indicator</h3>
            <TypingIndicator />
          </div>

          <div>
            <h3 className="text-lg font-medium text-text-primary mb-2">Skeleton Loader</h3>
            <SkeletonLoader lines={4} />
          </div>

          <div>
            <h3 className="text-lg font-medium text-text-primary mb-2">Progress Bar</h3>
            <ProgressBar progress={progress} />
            <InteractiveButton
              onClick={() => setProgress((p) => (p >= 100 ? 0 : p + 10))}
              className="mt-2 px-4 py-2 bg-accent-primary text-white rounded-lg"
            >
              Increment Progress
            </InteractiveButton>
          </div>
        </div>
      </section>
    </div>
  );
}
