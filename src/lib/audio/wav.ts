/**
 * PCM capture and WAV encoding.
 *
 * Speech providers expect 16 kHz mono PCM. The microphone gives us float
 * samples at the device rate, so we downmix, resample with a windowed average
 * and encode a canonical 16-bit WAV before anything leaves the app.
 */

export const TARGET_SAMPLE_RATE = 16_000;

/** Mixes an arbitrary channel count down to mono. */
export function downmixToMono(channels: Float32Array[]): Float32Array {
  if (channels.length === 0) return new Float32Array(0);
  if (channels.length === 1) return channels[0];

  const length = channels[0].length;
  const mono = new Float32Array(length);

  for (let index = 0; index < length; index += 1) {
    let sum = 0;
    for (const channel of channels) {
      sum += channel[index] ?? 0;
    }
    mono[index] = sum / channels.length;
  }

  return mono;
}

/**
 * Resamples mono audio by averaging the source samples that fall inside each
 * destination window. Averaging acts as a cheap anti-alias filter, which keeps
 * speech intelligible when downsampling from 48 kHz.
 */
export function resampleMono(
  samples: Float32Array,
  fromRate: number,
  toRate = TARGET_SAMPLE_RATE
): Float32Array {
  if (fromRate <= 0 || toRate <= 0) {
    throw new Error('Sample rates must be positive.');
  }
  if (fromRate === toRate || samples.length === 0) {
    return samples;
  }

  const ratio = fromRate / toRate;
  const length = Math.max(1, Math.floor(samples.length / ratio));
  const output = new Float32Array(length);

  for (let index = 0; index < length; index += 1) {
    const start = Math.floor(index * ratio);
    const end = Math.min(samples.length, Math.floor((index + 1) * ratio));

    if (end <= start) {
      output[index] = samples[start] ?? 0;
      continue;
    }

    let sum = 0;
    for (let cursor = start; cursor < end; cursor += 1) {
      sum += samples[cursor];
    }
    output[index] = sum / (end - start);
  }

  return output;
}

/** Peak amplitude in the 0..1 range, used to detect silence. */
export function peakAmplitude(samples: Float32Array): number {
  let peak = 0;
  for (let index = 0; index < samples.length; index += 1) {
    const value = Math.abs(samples[index]);
    if (value > peak) peak = value;
  }
  return peak;
}

export function isSilent(samples: Float32Array, threshold = 0.008): boolean {
  return peakAmplitude(samples) < threshold;
}

function writeAscii(view: DataView, offset: number, text: string): void {
  for (let index = 0; index < text.length; index += 1) {
    view.setUint8(offset + index, text.charCodeAt(index));
  }
}

/**
 * Encodes mono float samples as a 16-bit PCM WAV container.
 * Returns a plain ArrayBuffer so it can be sent to Rust as a byte array.
 */
export function encodeWav(samples: Float32Array, sampleRate = TARGET_SAMPLE_RATE): ArrayBuffer {
  const dataSize = samples.length * 2;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  writeAscii(view, 0, 'RIFF');
  view.setUint32(4, 36 + dataSize, true);
  writeAscii(view, 8, 'WAVE');
  writeAscii(view, 12, 'fmt ');
  view.setUint32(16, 16, true); // PCM chunk size
  view.setUint16(20, 1, true); // format: PCM
  view.setUint16(22, 1, true); // channels: mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  writeAscii(view, 36, 'data');
  view.setUint32(40, dataSize, true);

  let offset = 44;
  for (let index = 0; index < samples.length; index += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[index]));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
    offset += 2;
  }

  return buffer;
}

/** Converts an ArrayBuffer to base64 without exceeding argument limits. */
export function bufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  const chunkSize = 0x8000;
  let binary = '';

  for (let index = 0; index < bytes.length; index += chunkSize) {
    const slice = bytes.subarray(index, index + chunkSize);
    binary += String.fromCharCode(...slice);
  }

  return btoa(binary);
}
