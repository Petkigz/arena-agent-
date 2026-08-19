import { NavLink } from 'react-router-dom';
import { MessageCircle, Brain, User } from 'lucide-react';
import { motion } from 'framer-motion';
import { cn } from '../../utils/cn';

export function BottomNavigation() {
  const links = [
    { to: '/beanie', icon: User, label: 'Beanie' },
    { to: '/chat', icon: MessageCircle, label: 'Chat' },
    { to: '/pansophy', icon: Brain, label: 'Pansophy' },
  ];

  return (
    <motion.nav
      initial={{ y: 20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="bg-background-secondary border-t border-background-surface"
    >
      <div className="flex justify-around items-center h-16">
        {links.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                'flex flex-col items-center justify-center gap-1 px-4 py-2 transition-colors',
                isActive ? 'text-accent-primary' : 'text-text-muted hover:text-text-secondary'
              )}
            >
            <Icon className="w-6 h-6" />
            <span className="text-xs font-medium">{label}</span>
          </NavLink>
        ))}
      </div>
    </motion.nav>
  );
}
