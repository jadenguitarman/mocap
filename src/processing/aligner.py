
import librosa
import numpy as np
import os
import json

class AudioAligner:
    def __init__(self):
        pass

    def find_onset(self, audio_path):
        """
        Finds the first significant onset (clap) in the audio file.
        Returns the time in seconds.
        """
        if not os.path.exists(audio_path):
            print(f"[Aligner] Error: File nt found {audio_path}")
            return None

        # Load audio (mono)
        y, sr = librosa.load(audio_path, sr=None, mono=True)
        
        # Detect onsets
        onset_frames = librosa.onset.onset_detect(y=y, sr=sr, backtrack=True)
        onset_times = librosa.frames_to_time(onset_frames, sr=sr)
        
        if len(onset_times) > 0:
            # Assume the first distinct onset is the clap
            # Could add logic to find the *loudest* onset if needed
            return onset_times[0]
            
        return None

    def calculate_offsets(self, reference_path, mobile_paths):
        """
        Calculates time offsets for a list of mobile audio files relative to a reference (PC) audio.
        Returns a dict {filename: offset_seconds, drift_factor: 1.0}
        """
        ref_onset = self.find_onset(reference_path)
        if ref_onset is None:
            print("[Aligner] No onset found in reference audio.")
            return {}

        offsets = {}
        for path in mobile_paths:
            mob_onset = self.find_onset(path)
            if mob_onset:
                # If mobile onset is at 5s and ref is at 2s, mobile started 3s EARLY? 
                # Wait. 
                # Event happened at RealTime T.
                # Ref recording started at T_ref_start. Onset is at T - T_ref_start.
                # Mob recording started at T_mob_start. Onset is at T - T_mob_start.
                # Offset = (T - T_mob_start) - (T - T_ref_start) = T_ref_start - T_mob_start
                # Actually we just want to know: To sync Mobile to Ref, shift Mobile by X.
                # Shift = Ref_Onset_Time - Mob_Onset_Time
                
                offset = ref_onset - mob_onset
                offsets[os.path.basename(path)] = {
                    "time_offset": offset,
                    "drift_factor": 1.0 # Placeholder for linear drift calculation
                }
                print(f"[Aligner] {os.path.basename(path)} offset: {offset:.4f}s")
            else:
                print(f"[Aligner] No onset for {os.path.basename(path)}")
        
        return offsets

    def get_drift(self, ref_duration, mob_duration):
        # Naive drift: ratio of durations? 
        # Only works if we know they recorded the EXACT same real-time span.
        # But they started/stopped at different times.
        # Drift correction requires TWO sync points (Clap Start + Clap End).
        # For now, we assume 1.0 (modern clocks are decent enough for short takes).
        return 1.0
