import { useEffect } from 'react';
import { useSystemStore } from '@/stores';
import { invokeCommand, isTauriRuntime } from '@/lib/runtime';
import type { SystemSnapshot } from '@/types';

const DEFAULT_INTERVAL = 5_000;

/**
 * Polls native Windows telemetry while the FRIDAY desktop app is running.
 * The browser preview simply leaves the last known values in place.
 */
export function useTelemetry(intervalMs = DEFAULT_INTERVAL) {
  const setStatus = useSystemStore((state) => state.setStatus);

  useEffect(() => {
    if (!isTauriRuntime()) return;

    let disposed = false;
    let timer: number | undefined;

    const schedule = () => {
      if (!disposed) {
        timer = window.setTimeout(poll, intervalMs);
      }
    };

    const poll = async () => {
      try {
        const snapshot = await invokeCommand<SystemSnapshot>('get_system_snapshot');
        if (!disposed) {
          setStatus({
            cpuUsage: snapshot.cpuUsage,
            memoryUsage: snapshot.memoryUsage,
            memoryTotal: snapshot.memoryTotal,
            uptime: snapshot.uptime,
            hostname: snapshot.hostname,
            os: snapshot.os,
            cpuName: snapshot.cpuName,
            version: '0.2.0',
          });
        }
      } catch {
        // Telemetry is best effort; the HUD keeps its last known values.
      }
      schedule();
    };

    void poll();

    return () => {
      disposed = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [intervalMs, setStatus]);

  return { isDesktop: isTauriRuntime() };
}
