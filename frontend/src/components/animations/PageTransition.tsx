import { motion, AnimatePresence } from 'framer-motion';
import type { ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { pageVariants } from './variants';
import { MOTION } from '../../design/tokens';

interface PageTransitionProps {
  children: ReactNode;
  className?: string;
}

export function PageTransition({ children, className }: PageTransitionProps) {
  const location = useLocation();

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={location.pathname}
        variants={pageVariants}
        initial="initial"
        animate="animate"
        exit="exit"
        className={className}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}

// Simple page transition wrapper that doesn't require location key
interface AnimatePageProps {
  children: ReactNode;
  className?: string;
}

export function AnimatePage({ children, className }: AnimatePageProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: MOTION.base_ms / 1000, ease: 'easeOut' }}
      className={className}
    >
      {children}
    </motion.div>
  );
}
