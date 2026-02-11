
import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wavfile
import threading
import time
import os
from scipy.signal import find_peaks

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
        # Flatten to mono if needed
        if self.channels > 1:
            audio_data = np.mean(audio_data, axis=1)
        else:
            audio_data = audio_data.flatten()
            
        # Normalize
        audio_data = audio_data / np.max(np.abs(audio_data))
        
        # Find peaks
        # Threshold: 0.5 (adjustable)
        peaks, _ = find_peaks(audio_data, height=0.5, distance=self.samplerate*0.5) # Min 0.5s between claps
        
        if len(peaks) > 0:
            first_clap_index = peaks[0]
            first_clap_time = first_clap_index / self.samplerate
            print(f"[Audio] CLAP DETECTED at {first_clap_time:.4f}s")
            return first_clap_time
        else:
            print("[Audio] No clear clap detected.")
            return None

    @staticmethod
    def find_sync_spike(filename):
        if not os.path.exists(filename):
            print(f"[Audio] File not found: {filename}")
            return None
            
        try:
            samplerate, data = wavfile.read(filename)
            # Use the same logic
            # Flatten
            if len(data.shape) > 1:
                data = np.mean(data, axis=1)
                
            data = data / np.max(np.abs(data))
            peaks, _ = find_peaks(data, height=0.5, distance=samplerate*0.5)
            
            if len(peaks) > 0:
                return peaks[0] / samplerate
            return None
        except Exception as e:
            print(f"[Audio] Error finding sync spike: {e}")
            return None


if __name__ == "__main__":
    # Test Device Discovery
    AudioRecorder.list_devices()
