
import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wavfile
import threading
import time
import os
from scipy.signal import find_peaks

# Minimum time between sync claps (seconds)
MIN_CLAP_DISTANCE_SEC = 2.0


class AudioRecorder:
    def __init__(self, filename="recording.wav", device=None, samplerate=44100, channels=1):
        self.filename = filename
        self.device = device
        self.samplerate = samplerate
        self.channels = channels
        self.recording = []
        self.is_recording = False
        self.stream = None
        self.start_time = 0

    @staticmethod
    def list_devices():
        print(sd.query_devices())
        return sd.query_devices()

    def callback(self, indata, frames, time, status):
        if status:
            print(status)
        self.recording.append(indata.copy())

    def start(self):
        if self.is_recording:
            return
        
        self.recording = []
        self.is_recording = True
        self.start_time = time.time()
        
        try:
            self.stream = sd.InputStream(
                samplerate=self.samplerate,
                device=self.device,
                channels=self.channels,
                callback=self.callback
            )
            self.stream.start()
            print(f"[Audio] Started recording on device {self.device}...")
        except Exception as e:
            print(f"[Audio] Error starting stream: {e}")
            self.is_recording = False

    def stop(self):
        if not self.is_recording:
            return

        self.is_recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
        
        # Concatenate and Save
        if self.recording:
            audio_data = np.concatenate(self.recording, axis=0)
            wavfile.write(self.filename, self.samplerate, (audio_data * 32767).astype(np.int16))
            print(f"[Audio] Saved to {self.filename}")
            return self.analyze_clap(audio_data)
        return None

    def analyze_clap(self, audio_data):
        """Analyze audio and return the first clap time (for backward compatibility)."""
        clap_times = self.find_all_sync_spikes(self.filename)
        if clap_times and len(clap_times) > 0:
            print(f"[Audio] CLAP DETECTED at {clap_times[0]:.4f}s")
            return clap_times[0]
        else:
            print("[Audio] No clear clap detected.")
            return None

    @staticmethod
    def find_all_sync_spikes(filename):
        """
        Find ALL sync spikes (claps) in an audio file.
        Returns a list of times (in seconds) where significant peaks occur.
        This enables two-point synchronization for drift calculation.
        """
        if not os.path.exists(filename):
            print(f"[Audio] File not found: {filename}")
            return []
            
        try:
            samplerate, data = wavfile.read(filename)
            # Flatten to mono if needed
            if len(data.shape) > 1:
                data = np.mean(data, axis=1)
                
            peak = np.max(np.abs(data))
            if peak == 0:
                print("[Audio] Recording is silent; no sync spike can be detected.")
                return []
            data = data / peak
            
            # Find peaks with minimum distance between claps
            min_distance_samples = int(MIN_CLAP_DISTANCE_SEC * samplerate)
            peaks, properties = find_peaks(data, height=0.3, distance=min_distance_samples)
            
            if len(peaks) == 0:
                return []
            
            # Sort by prominence (sharpness) and return times
            # Use the highest peaks first (most likely to be intentional claps)
            peak_heights = properties['heights']
            sorted_indices = np.argsort(peak_heights)[::-1]  # Descending order
            
            # Convert to times and sort by time
            clap_times = sorted([peaks[i] / samplerate for i in sorted_indices])
            
            if len(clap_times) >= 2:
                print(f"[Audio] Found {len(clap_times)} sync spikes: start={clap_times[0]:.4f}s, end={clap_times[-1]:.4f}s")
            elif len(clap_times) == 1:
                print(f"[Audio] Found 1 sync spike at {clap_times[0]:.4f}s (single-point sync only)")
            
            return clap_times
        except Exception as e:
            print(f"[Audio] Error finding sync spikes: {e}")
            return []

    @staticmethod
    def find_sync_spike(filename):
        """Find the first sync spike (for backward compatibility)."""
        if not os.path.exists(filename):
            print(f"[Audio] File not found: {filename}")
            return None
            
        clap_times = AudioRecorder.find_all_sync_spikes(filename)
        if clap_times and len(clap_times) > 0:
            return clap_times[0]
        return None


if __name__ == "__main__":
    # Test Device Discovery
    AudioRecorder.list_devices()
