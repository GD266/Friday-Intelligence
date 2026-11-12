import type { CSSProperties } from 'react';
import { cn } from '@/lib/utils';
import type { FridayMood } from '@/types';

export interface CoreOrbProps {
  mood?: FridayMood;
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'hero';
  audioLevel?: number;
  label?: string;
  className?: string;
  showWaveform?: boolean;
}

const sizeClasses = {
  xs: 'h-8 w-8',
  sm: 'h-12 w-12',
  md: 'h-40 w-40',
  lg: 'h-56 w-56',
  hero: 'h-[17.5rem] w-[17.5rem] sm:h-[21rem] sm:w-[21rem] xl:h-[23rem] xl:w-[23rem]',
};

const moodLabels: Record<FridayMood, string> = {
  idle: 'FRIDAY core idle',
  listening: 'FRIDAY core listening',
  thinking: 'FRIDAY core processing',
  speaking: 'FRIDAY core speaking',
  alert: 'FRIDAY core alert',
};

const WAVE_BARS = [0.42, 0.7, 1, 0.58, 0.86, 0.5, 0.76, 0.38, 0.62, 0.8, 0.46, 0.68];

export const CoreOrb = ({
  mood = 'idle',
  size = 'md',
  audioLevel = 0,
  label,
  className,
  showWaveform = true,
}: CoreOrbProps) => {
  const level = Math.min(1, Math.max(0, audioLevel));
  const waveformVisible = showWaveform && (mood === 'listening' || mood === 'speaking');

  return (
    <div
      className={cn('friday-orb flex-shrink-0', sizeClasses[size], className)}
      data-mood={mood}
      role="img"
      aria-label={label ?? moodLabels[mood]}
      style={{ '--orb-speed': `${1.9 - level * 0.8}s` } as CSSProperties}
    >
      <div className="friday-orb__halo" aria-hidden="true" />
      <div className="friday-orb__mesh" aria-hidden="true" />
      <div className="friday-orb__ring friday-orb__ring--outer" aria-hidden="true">
        <span className="friday-orb__node" />
      </div>
      <div className="friday-orb__ring friday-orb__ring--mid" aria-hidden="true">
        <span className="friday-orb__node" />
      </div>
      <div className="friday-orb__ring friday-orb__ring--inner" aria-hidden="true" />
      <div className="friday-orb__ticks" aria-hidden="true" />
      <div className="friday-orb__satellite friday-orb__satellite--a" aria-hidden="true" />
      <div className="friday-orb__satellite friday-orb__satellite--b" aria-hidden="true" />
      <div className="friday-orb__core" aria-hidden="true">
        <div className="friday-orb__plasma" />
        <div className="friday-orb__flare" />
        <div className="friday-orb__spark" />
      </div>

      {waveformVisible && (
        <div className="friday-orb__wave" aria-hidden="true">
          {WAVE_BARS.map((bar, index) => (
            <span
              key={index}
              style={{
                height: `${Math.round(24 + bar * (mood === 'listening' ? 30 + level * 46 : 60))}%`,
                animationDelay: `${index * 85}ms`,
                animationDuration: `${0.8 + (index % 3) * 0.16}s`,
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
};

CoreOrb.displayName = 'CoreOrb';

export default CoreOrb;
