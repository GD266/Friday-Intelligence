import { describe, expect, it } from 'vitest';
import {
  bufferToBase64,
  downmixToMono,
  encodeWav,
  isSilent,
  peakAmplitude,
  resampleMono,
  TARGET_SAMPLE_RATE,
} from './wav';
import { describeMicrophoneError } from './recorder';

function readAscii(view: DataView, offset: number, length: number): string {
  let text = '';
  for (let index = 0; index < length; index += 1) {
    text += String.fromCharCode(view.getUint8(offset + index));
  }
  return text;
}

describe('WAV encoding', () => {
  it('writes a canonical mono 16-bit PCM header', () => {
    const samples = new Float32Array([0, 0.5, -0.5, 1]);
    const buffer = encodeWav(samples, TARGET_SAMPLE_RATE);
    const view = new DataView(buffer);

    expect(buffer.byteLength).toBe(44 + samples.length * 2);
    expect(readAscii(view, 0, 4)).toBe('RIFF');
    expect(readAscii(view, 8, 4)).toBe('WAVE');
    expect(readAscii(view, 12, 4)).toBe('fmt ');
    expect(readAscii(view, 36, 4)).toBe('data');

    expect(view.getUint32(4, true)).toBe(36 + samples.length * 2);
    expect(view.getUint16(20, true)).toBe(1); // PCM
    expect(view.getUint16(22, true)).toBe(1); // mono
    expect(view.getUint32(24, true)).toBe(TARGET_SAMPLE_RATE);
    expect(view.getUint32(28, true)).toBe(TARGET_SAMPLE_RATE * 2);
    expect(view.getUint16(32, true)).toBe(2);
    expect(view.getUint16(34, true)).toBe(16);
    expect(view.getUint32(40, true)).toBe(samples.length * 2);

    // 16 kHz mono 16-bit = 32 kB per second of speech.
    expect(buffer.byteLength).toBe(44 + 8);
  });

  it('clamps out-of-range samples instead of wrapping', () => {
    const buffer = encodeWav(new Float32Array([3, -3]), TARGET_SAMPLE_RATE);
    const view = new DataView(buffer);
    expect(view.getInt16(44, true)).toBe(32767);
    expect(view.getInt16(46, true)).toBe(-32768);
  });
});

describe('resampling', () => {
  it('converts 48 kHz audio to 16 kHz at one third of the length', () => {
    const source = new Float32Array(4800);
    source.fill(0.25);
    const resampled = resampleMono(source, 48_000);

    expect(resampled.length).toBe(1600);
    expect(resampled[10]).toBeCloseTo(0.25, 5);
  });

  it('keeps already-correct sample rates untouched', () => {
    const source = new Float32Array([0.1, 0.2, 0.3]);
    expect(resampleMono(source, 16_000)).toBe(source);
  });

  it('rejects invalid sample rates', () => {
    expect(() => resampleMono(new Float32Array(4), 0)).toThrow();
    expect(() => resampleMono(new Float32Array(4), 48_000, -1)).toThrow();
  });

  it('produces at least one sample for a single-frame input', () => {
    const resampled = resampleMono(new Float32Array([0.5]), 48_000);
    expect(resampled.length).toBe(1);
  });
});

describe('channel handling', () => {
  it('averages stereo channels into mono', () => {
    const left = new Float32Array([1, 0.5, -1]);
    const right = new Float32Array([-1, 0.5, 1]);
    const mono = downmixToMono([left, right]);

    expect(Array.from(mono)).toEqual([0, 0.5, 0]);
  });

  it('passes mono input through unchanged', () => {
    const mono = new Float32Array([0.2, 0.4]);
    expect(downmixToMono([mono])).toBe(mono);
  });

  it('returns an empty buffer when no channels exist', () => {
    expect(downmixToMono([]).length).toBe(0);
  });
});

describe('silence detection', () => {
  it('measures peak amplitude', () => {
    expect(peakAmplitude(new Float32Array([0.1, -0.4, 0.2]))).toBeCloseTo(0.4, 5);
  });

  it('flags a quiet room as silent', () => {
    const room = new Float32Array(1600);
    room.fill(0.001);
    expect(isSilent(room)).toBe(true);
  });

  it('does not flag speech as silent', () => {
    const speech = new Float32Array(1600);
    speech.fill(0.2);
    expect(isSilent(speech)).toBe(false);
  });
});

describe('base64 transport', () => {
  it('round-trips bytes without corrupting them', () => {
    const bytes = new Uint8Array([0, 1, 127, 128, 255, 42]);
    const base64 = bufferToBase64(bytes.buffer);

    expect(base64).toBe(btoa(String.fromCharCode(...bytes)));
    expect(atob(base64).length).toBe(bytes.length);
  });

  it('handles payloads larger than the argument limit', () => {
    const bytes = new Uint8Array(100_000);
    bytes.fill(7);
    const base64 = bufferToBase64(bytes.buffer);

    expect(atob(base64).length).toBe(bytes.length);
  });
});

describe('microphone error messages', () => {
  it('explains a denied permission', () => {
    expect(describeMicrophoneError({ name: 'NotAllowedError' })).toContain('denied');
  });

  it('explains a missing device', () => {
    expect(describeMicrophoneError({ name: 'NotFoundError' })).toContain('No microphone');
  });

  it('explains a busy device', () => {
    expect(describeMicrophoneError({ name: 'NotReadableError' })).toContain('in use');
  });

  it('falls back to the thrown message', () => {
    expect(describeMicrophoneError(new Error('boom'))).toBe('Microphone error: boom');
  });

  it('has a generic fallback', () => {
    expect(describeMicrophoneError(null)).toBe('The microphone could not be started.');
  });
});
