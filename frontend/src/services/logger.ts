/**
 * Production-ready logging service
 * 
 * In production, this would integrate with services like:
 * - Sentry (error tracking)
 * - LogRocket (session replay)
 * - Datadog (APM)
 * - Custom backend logging
 */

type LogLevel = 'debug' | 'info' | 'warn' | 'error';

interface LogEntry {
  level: LogLevel;
  message: string;
  context?: Record<string, unknown>;
  timestamp: string;
}

class Logger {
  private enabled: boolean;
  private minLevel: LogLevel;
  private logBuffer: LogEntry[] = [];
  private maxBufferSize = 1000;

  constructor() {
    // Disable logging in production
    this.enabled = import.meta.env.DEV;
    this.minLevel = import.meta.env.DEV ? 'debug' : 'error';
  }

  private shouldLog(level: LogLevel): boolean {
    if (!this.enabled) return false;

    const levels: LogLevel[] = ['debug', 'info', 'warn', 'error'];
    return levels.indexOf(level) >= levels.indexOf(this.minLevel);
  }

  private addToBuffer(entry: LogEntry) {
    this.logBuffer.push(entry);
    if (this.logBuffer.length > this.maxBufferSize) {
      this.logBuffer.shift();
    }
  }

  private formatMessage(level: LogLevel, message: string, context?: Record<string, unknown>): string {
    const timestamp = new Date().toISOString();
    const contextStr = context ? ` ${JSON.stringify(context)}` : '';
    return `[${timestamp}] [${level.toUpperCase()}] ${message}${contextStr}`;
  }

  debug(message: string, context?: Record<string, unknown>) {
    if (!this.shouldLog('debug')) return;

    const entry: LogEntry = {
      level: 'debug',
      message,
      context,
      timestamp: new Date().toISOString(),
    };

    this.addToBuffer(entry);
    console.debug(this.formatMessage('debug', message, context));
  }

  info(message: string, context?: Record<string, unknown>) {
    if (!this.shouldLog('info')) return;

    const entry: LogEntry = {
      level: 'info',
      message,
      context,
      timestamp: new Date().toISOString(),
    };

    this.addToBuffer(entry);
    console.info(this.formatMessage('info', message, context));
  }

  warn(message: string, context?: Record<string, unknown>) {
    if (!this.shouldLog('warn')) return;

    const entry: LogEntry = {
      level: 'warn',
      message,
      context,
      timestamp: new Date().toISOString(),
    };

    this.addToBuffer(entry);
    console.warn(this.formatMessage('warn', message, context));
  }

  error(message: string, error?: Error | unknown, context?: Record<string, unknown>) {
    // Always log errors, even in production
    const errorContext = {
      ...context,
      error: error instanceof Error ? {
        name: error.name,
        message: error.message,
        stack: error.stack,
      } : error,
    };

    const entry: LogEntry = {
      level: 'error',
      message,
      context: errorContext,
      timestamp: new Date().toISOString(),
    };

    this.addToBuffer(entry);
    console.error(this.formatMessage('error', message, errorContext));

    // In production, send to error tracking service
    if (!import.meta.env.DEV) {
      this.sendToErrorTracking(entry);
    }
  }

  private sendToErrorTracking(_entry: LogEntry) {
    // Placeholder for error tracking integration
    // In production, this would send to Sentry, LogRocket, etc.
    // Example:
    // Sentry.captureException(entry.context?.error);
  }

  getLogBuffer(): LogEntry[] {
    return [...this.logBuffer];
  }

  clearBuffer() {
    this.logBuffer = [];
  }

  setEnabled(enabled: boolean) {
    this.enabled = enabled;
  }

  setMinLevel(level: LogLevel) {
    this.minLevel = level;
  }
}

export const logger = new Logger();
