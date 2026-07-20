/**
 * Pure client-side technical indicator math, computed from candle closes.
 * These are standard, well-known formulas — no backend round-trip needed.
 *
 * Every function returns an array the same length as the input `values`
 * array, with `null` in slots where there isn't yet enough history to
 * compute a value (so callers can zip with candle times and filter nulls).
 */

export type Series = (number | null)[];

/** Exponential moving average, seeded with a simple average of the first
 * `period` values (standard convention), alpha = 2 / (period + 1). */
export function ema(values: number[], period: number): Series {
  const result: Series = new Array(values.length).fill(null);
  if (values.length < period) return result;

  const k = 2 / (period + 1);
  let seed = 0;
  for (let i = 0; i < period; i++) seed += values[i];
  seed /= period;

  let prev = seed;
  result[period - 1] = seed;
  for (let i = period; i < values.length; i++) {
    prev = values[i] * k + prev * (1 - k);
    result[i] = prev;
  }
  return result;
}

/** Simple moving average over a trailing window of `period` values. */
export function sma(values: number[], period: number): Series {
  const result: Series = new Array(values.length).fill(null);
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= period) sum -= values[i - period];
    if (i >= period - 1) result[i] = sum / period;
  }
  return result;
}

/** Bollinger Bands: SMA middle band, +/- `mult` * population stddev. */
export function bollingerBands(
  values: number[],
  period = 20,
  mult = 2
): { middle: Series; upper: Series; lower: Series } {
  const middle = sma(values, period);
  const upper: Series = new Array(values.length).fill(null);
  const lower: Series = new Array(values.length).fill(null);

  for (let i = period - 1; i < values.length; i++) {
    const mean = middle[i];
    if (mean == null) continue;
    let variance = 0;
    for (let j = i - period + 1; j <= i; j++) {
      variance += (values[j] - mean) ** 2;
    }
    variance /= period;
    const sd = Math.sqrt(variance);
    upper[i] = mean + mult * sd;
    lower[i] = mean - mult * sd;
  }
  return { middle, upper, lower };
}

/** Wilder's RSI (the standard RSI smoothing method). */
export function rsi(values: number[], period = 14): Series {
  const result: Series = new Array(values.length).fill(null);
  if (values.length <= period) return result;

  let gainSum = 0;
  let lossSum = 0;
  for (let i = 1; i <= period; i++) {
    const diff = values[i] - values[i - 1];
    if (diff >= 0) gainSum += diff;
    else lossSum -= diff;
  }
  let avgGain = gainSum / period;
  let avgLoss = lossSum / period;
  result[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);

  for (let i = period + 1; i < values.length; i++) {
    const diff = values[i] - values[i - 1];
    const gain = diff > 0 ? diff : 0;
    const loss = diff < 0 ? -diff : 0;
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
    result[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  }
  return result;
}

/** MACD: fast EMA - slow EMA, signal = EMA(signalPeriod) of the MACD line,
 * histogram = macd - signal. The signal EMA is seeded from the first index
 * where the MACD line itself becomes defined (i.e. once slow EMA warms up). */
export function macd(
  values: number[],
  fastPeriod = 12,
  slowPeriod = 26,
  signalPeriod = 9
): { macdLine: Series; signalLine: Series; histogram: Series } {
  const fast = ema(values, fastPeriod);
  const slow = ema(values, slowPeriod);
  const macdLine: Series = values.map((_, i) => {
    const f = fast[i];
    const s = slow[i];
    return f != null && s != null ? f - s : null;
  });

  const firstValid = macdLine.findIndex((v) => v != null);
  const signalLine: Series = new Array(values.length).fill(null);
  if (firstValid !== -1) {
    const subset = macdLine.slice(firstValid) as number[];
    const subsetSignal = ema(subset, signalPeriod);
    subsetSignal.forEach((v, idx) => {
      signalLine[firstValid + idx] = v;
    });
  }

  const histogram: Series = values.map((_, i) => {
    const m = macdLine[i];
    const s = signalLine[i];
    return m != null && s != null ? m - s : null;
  });

  return { macdLine, signalLine, histogram };
}
