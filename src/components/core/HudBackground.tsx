const PARTICLES = Array.from({ length: 42 }, (_, index) => {
  const seed = (index + 1) * 97;
  return {
    left: `${(seed * 37) % 100}%`,
    top: `${(seed * 61) % 100}%`,
    size: index % 7 === 0 ? 2 : 1,
    delay: `${(index % 13) * 0.65}s`,
    duration: `${5 + (index % 9)}s`,
    opacity: 0.18 + ((index % 5) * 0.12),
  };
});

export const HudBackground = () => (
  <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
    <div className="hud-grid absolute inset-0" />
    <div className="hud-horizon" />
    <div className="hud-radar" />
    <div className="hud-aurora hud-aurora--blue" />
    <div className="hud-aurora hud-aurora--violet" />
    <div className="hud-aurora hud-aurora--cyan" />

    <div className="hud-particles">
      {PARTICLES.map((particle, index) => (
        <span
          key={index}
          style={{
            left: particle.left,
            top: particle.top,
            width: particle.size,
            height: particle.size,
            opacity: particle.opacity,
            animationDelay: particle.delay,
            animationDuration: particle.duration,
          }}
        />
      ))}
    </div>

    <div className="hud-crosshair hud-crosshair--x" />
    <div className="hud-crosshair hud-crosshair--y" />
    <div className="hud-vignette absolute inset-0" />
    <div className="hud-noise absolute inset-0" />
    <div className="hud-scanline" />
    <div className="hud-edge hud-edge--top" />
    <div className="hud-edge hud-edge--bottom" />

    <div className="hud-corner hud-corner--tl" />
    <div className="hud-corner hud-corner--tr" />
    <div className="hud-corner hud-corner--bl" />
    <div className="hud-corner hud-corner--br" />
  </div>
);

HudBackground.displayName = 'HudBackground';

export default HudBackground;
