#!/usr/bin/env python3
"""Listen to the phone with the laptop's microphone.

    mic-level.py SECONDS [WAV] [HZ]

Records SECONDS from the default PipeWire source (48 kHz mono S16) with pw-record,
or reads WAV if given, and prints one line per 250 ms window: the level in dBFS,
the strongest frequency, and the level in a 20 Hz band around HZ (440 by
default, speaker-test -t sine). The laptop mic is noisy (about -18 dBFS of
broadband floor), so a tone shows in the band column long before the total.

Check the instrument first, or a silent result says nothing about the phone: a
tone from the laptop's own speaker (pw-play) reads about -19 dB in its band
against a floor near -50 dB. The vibrator is too weak a buzz to show at all.
"""

import subprocess
import sys
import wave

import numpy as np

RATE = 48000
WIN = RATE // 4


def record(seconds, path):
    # pw-record has no duration option; it is stopped with SIGINT by timeout
    subprocess.run(['timeout', '-s', 'INT', str(seconds), 'pw-record', '--rate',
                    str(RATE), '--channels', '1', '--format', 's16', path])


def main():
    seconds = int(sys.argv[1])
    path = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != '-' else '/tmp/mic-level.wav'
    hz = float(sys.argv[3]) if len(sys.argv) > 3 else 440.0
    if path == '/tmp/mic-level.wav':
        record(seconds, path)
    with wave.open(path) as w:
        assert w.getframerate() == RATE and w.getsampwidth() == 2
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        x = x.reshape(-1, w.getnchannels())[:, 0].astype(np.float64) / 32768
    for i in range(len(x) // WIN):
        seg = x[i * WIN:(i + 1) * WIN]
        rms = np.sqrt(np.mean(seg ** 2)) + 1e-12
        spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        spec[:int(50 * len(seg) / RATE)] = 0     # drop DC and mains hum
        freqs = np.fft.rfftfreq(len(seg), 1 / RATE)
        peak = freqs[np.argmax(spec)]
        band = np.sqrt(np.sum(spec[np.abs(freqs - hz) <= 10] ** 2)) * 2 / len(seg)
        print('%5.2f s  %6.1f dBFS  peak %5.0f Hz  %4.0f Hz band %6.1f dB' % (
            i * WIN / RATE, 20 * np.log10(rms), peak, hz, 20 * np.log10(band + 1e-12)))


if __name__ == '__main__':
    main()
