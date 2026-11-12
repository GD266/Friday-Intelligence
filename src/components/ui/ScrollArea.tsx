import { type HTMLAttributes, forwardRef, useImperativeHandle } from 'react';

export interface ScrollAreaProps extends HTMLAttributes<HTMLDivElement> {
  className?: string;
}

export const ScrollArea = forwardRef<HTMLDivElement, ScrollAreaProps>(
  ({ className, children, ...props }, ref) => {
    const scrollRef = useImperativeHandle(ref, () => ({
      scrollTo: (options?: ScrollIntoViewOptions) => {
        scrollRef.current?.scrollIntoView({ block: 'start' });
      },
      scrollTop: scrollRef.current?.scrollTop ?? 0,
      scrollLeft: scrollRef.current?.scrollLeft ?? 0,
      scrollHeight: scrollRef.current?.scrollHeight ?? 0,
      scrollWidth: scrollRef.current?.scrollWidth ?? 0,
      clientHeight: scrollRef.current?.clientHeight ?? 0,
      clientWidth: scrollRef.current?.clientWidth ?? 0,
    }));

    return (
      <div
        ref={scrollRef}
        className={cn('overflow-auto', className)}
        {...props}
      >
        {children}
      </div>
    );
  }
);

ScrollArea.displayName = 'ScrollArea';