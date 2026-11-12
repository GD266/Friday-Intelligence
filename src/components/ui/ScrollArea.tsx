import { forwardRef, type HTMLAttributes } from 'react';
import { cn } from '../../lib/utils';

export interface ScrollAreaProps extends HTMLAttributes<HTMLDivElement> {
  className?: string;
}

export const ScrollArea = forwardRef<HTMLDivElement, ScrollAreaProps>(
  ({ className, children, ...props }, ref) => (
    <div ref={ref} className={cn('overflow-auto', className)} {...props}>
      {children}
    </div>
  )
);

ScrollArea.displayName = 'ScrollArea';
