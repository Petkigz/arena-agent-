/**
 * Notification service for user-facing messages
 * 
 * Wraps react-hot-toast with consistent API and styling
 */

import toast from 'react-hot-toast';


interface NotificationOptions {
  duration?: number;
  icon?: string;
}

class NotificationService {
  private defaultDuration = 4000;

  success(message: string, options?: NotificationOptions) {
    toast.success(message, {
      duration: options?.duration ?? this.defaultDuration,
      icon: options?.icon ?? '✅',
    });
  }

  error(message: string, options?: NotificationOptions) {
    toast.error(message, {
      duration: options?.duration ?? this.defaultDuration + 2000, // Errors stay longer
      icon: options?.icon ?? '❌',
    });
  }

  info(message: string, options?: NotificationOptions) {
    toast(message, {
      duration: options?.duration ?? this.defaultDuration,
      icon: options?.icon ?? 'ℹ️',
    });
  }

  warning(message: string, options?: NotificationOptions) {
    toast(message, {
      duration: options?.duration ?? this.defaultDuration,
      icon: options?.icon ?? '⚠️',
    });
  }

  loading(message: string): string {
    return toast.loading(message);
  }

  dismiss(toastId?: string) {
    if (toastId) {
      toast.dismiss(toastId);
    } else {
      toast.dismiss();
    }
  }

  successOrError(success: boolean, successMessage: string, errorMessage: string) {
    if (success) {
      this.success(successMessage);
    } else {
      this.error(errorMessage);
    }
  }
}

export const notifications = new NotificationService();
