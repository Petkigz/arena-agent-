import type { ReactNode } from 'react';
import type { FieldError } from 'react-hook-form';

interface FormFieldProps {
  label: string;
  required?: boolean;
  error?: FieldError;
  children: ReactNode;
  helpText?: string;
}

export function FormField({ label, required, error, children, helpText }: FormFieldProps) {
  return (
    <div>
      <label className="block text-sm font-medium text-text-secondary mb-1">
        {label} {required && <span className="text-accent-error">*</span>}
      </label>
      {children}
      {error && (
        <p className="mt-1 text-sm text-accent-error">
          {error.message}
        </p>
      )}
      {helpText && !error && (
        <p className="mt-1 text-xs text-text-muted">
          {helpText}
        </p>
      )}
    </div>
  );
}
