const SILENCE_SAMPLE = 128;
const LEVEL_GAIN = 4;
const ANALYSER_FFT_SIZE = 1024;

export function levelOf(samples: Uint8Array): number {
  let sumOfSquares = 0;
  for (const sample of samples) {
    const centered = (sample - SILENCE_SAMPLE) / SILENCE_SAMPLE;
    sumOfSquares += centered * centered;
  }
  const rootMeanSquare = Math.sqrt(sumOfSquares / samples.length);
  return Math.min(1, rootMeanSquare * LEVEL_GAIN);
}

export function createLevelAnalyser(context: AudioContext): AnalyserNode {
  const analyser = context.createAnalyser();
  analyser.fftSize = ANALYSER_FFT_SIZE;
  return analyser;
}

export function createLevelReader(analyser: AnalyserNode): () => number {
  const samples = new Uint8Array(analyser.fftSize);
  return () => {
    analyser.getByteTimeDomainData(samples);
    return levelOf(samples);
  };
}
