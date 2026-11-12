import { forwardRef, type ButtonHTMLAttributes } from 'react';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'icon';
  size?: 'sm' | 'md' | 'lg';
  isLoading?: boolean;
}

const variantClasses = {
  primary: 'inline-flex items-center justify-center gap-2 px-3 py-1.5 text-sm font-medium rounded bg-accent-blue text-white hover:bg-accent-blue/90 active:bg-accent-blue shadow-glow-blue',
  secondary: 'inline-flex items-center justify-center gap-2 px-3 py-1.5 text-sm font-medium rounded bg-surface-elevated text-graphite-100 hover:bg-surface-overlay border border-border-primary',
  ghost: 'inline-flex items-center justify-center gap-2 px-3 py-1.5 text-sm font-medium rounded bg-transparent text-graphite-300 hover:bg-graphite-800 hover:text-graphite-100',
  danger: 'inline-flex items-center justify-center gap-2 px-3 py-1.5 text-sm font-medium rounded bg-red-600/20 text-red-400 hover:bg-red-600/30 hover:text-red-300 border border-red-600/30',
  icon: 'inline-flex items-center justify-center gap-2 p-1.5',
};

const sizeClasses = {
  sm: 'px-2.5 py-1 text-xs',
  md: 'px-3 py-1.5 text-sm',
  lg: 'px-4 py-2 text-base',
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'secondary', size = 'md', isLoading, children, disabled, ...props }, ref) => {
    const baseClasses = 'inline-flex items-center justify-center gap-2 font-medium rounded transition-all duration-fast ease-out focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-blue/50 focus-visible:ring-offset-2 focus-visible:ring-offset-graphite-950 disabled:opacity-40 disabled:cursor-not-allowed';
    const vn = variantClasses[variant] || variantClasses.secondary;
    const sn = sizeClasses[size] || sizeClasses.md;
    const fullClassName = `${baseClasses} ${vn} ${sn} ${className || ''}`.trim();

    return (
      <button
        ref={ref}
        className={fullClassName}
        disabled={disabled || isLoading}
        {...props}
      >
        {isLoading && (
          <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
        )}
        {children}
      </button>
    );
  }
);

Button.displayName = 'Button';