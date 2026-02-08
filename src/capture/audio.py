
import pyaudio
import wave
import threading
import numpy as np
import scipy.io.wavfile as wavfile
import os

class AudioRecorder:
    def __init__(self, filename="recording.wav", chunk=1024, format=pyaudio.paInt16, channels=1, rate=44100):
        self.filename = filename
        self.chunk = chunk
        self.format = format
        self.channels = channels
        self.rate = rate
        self.frames = []
        self.recording = False
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.thread = None

    def start(self):
        self.frames = []
        self.recording = True
        self.stream = self.p.open(format=self.format,
                                  channels=self.channels,
                                  rate=self.rate,
                                  input=True,
                                  frames_per_buffer=self.chunk)
        self.thread = threading.Thread(target=self._record)
        self.thread.start()
        print(f"[Audio] Recording started: {self.filename}")

    def _record(self):
        while self.recording:
            try:
                data = self.stream.read(self.chunk)
                self.frames.append(data)
            except Exception as e:
                print(f"[Audio] Error recording: {e}")
                break

    def stop(self):
        self.recording = False
        if self.thread:
            self.thread.join()
        
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        
        # Don't terminate PyAudio here if we want to reuse the instance, 
        # but for a simple app often it's fine. 
        # self.p.terminate() 
        
        self.save()
        print(f"[Audio] Recording stopped. Saved to {self.filename}")

    def save(self):
        wf = wave.open(self.filename, 'wb')
        wf.setnchannels(self.channels)
        wf.setsampwidth(self.p.get_sample_size(self.format))
        wf.setframerate(self.rate)
        wf.writeframes(b''.join(self.frames))
        wf.close()

    @staticmethod
    def find_sync_spike(wav_path, threshold_ratio=0.8):
        """
        Analyzes the .wav file for the highest decibel spike.
        Returns the time in seconds of the spike.
        """
        if not os.path.exists(wav_path):
            print(f"[Audio] File not found: {wav_path}")
            return None

        rate, data = wavfile.read(wav_path)
        
        # If stereo, convert to mono
        if len(data.shape) > 1:
            data = data.mean(axis=1)
            
        # Normalize
        data = data / np.max(np.abs(data))
        
        # Find peak
        peak_index = np.argmax(np.abs(data))
        peak_time = peak_index / rate
        
        print(f"[Audio] Sync spike found at {peak_time:.4f}s")
        return peak_time
