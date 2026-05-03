
import librosa
import os

class AudioAligner:
    def __init__(self, min_sync_gap=1.0):
        self.min_sync_gap = min_sync_gap

    def find_onsets(self, audio_path):
        """
        Finds significant sync onsets in the audio file.
        Returns onset times in seconds.
        """
        if not os.path.exists(audio_path):
            print(f"[Aligner] Error: File not found {audio_path}")
            return []

        try:
            y, sr = librosa.load(audio_path, sr=None, mono=True)
            onset_frames = librosa.onset.onset_detect(y=y, sr=sr, backtrack=True)
            onset_times = librosa.frames_to_time(onset_frames, sr=sr)
            filtered = []
            for onset in onset_times:
                if not filtered or onset - filtered[-1] >= self.min_sync_gap:
                    filtered.append(float(onset))
            return filtered
        except Exception as e:
            print(f"[Aligner] WARNING: Could not load {audio_path}. Error: {e}")
            print(f"[Aligner] HINT: Ensure FFmpeg is installed and added to PATH for WebM support.")

        return []

    def find_onset(self, audio_path):
        onsets = self.find_onsets(audio_path)
        if onsets:
            return onsets[0]
        return None

    def get_duration(self, audio_path):
        if not os.path.exists(audio_path):
            return None
        try:
            return librosa.get_duration(path=audio_path)
        except Exception as e:
            print(f"[Aligner] WARNING: Could not read duration for {audio_path}. Error: {e}")
            return None

    def calculate_offsets(self, reference_path, mobile_paths):
        """
        Calculates time offsets for a list of mobile audio files relative to a reference (PC) audio.
        Returns a dict {filename: offset_seconds, drift_factor}.
        Requires two sync onsets in every stream so clock drift can be solved.
        """
        ref_onsets = self.find_onsets(reference_path)
        if len(ref_onsets) < 2:
            print("[Aligner] Need two sync onsets in reference audio: one start clap/blip and one end clap/blip.")
            return {}
        ref_onset = ref_onsets[0]

        offsets = {}
        for path in mobile_paths:
            mob_onsets = self.find_onsets(path)
            if len(mob_onsets) >= 2:
                mob_onset = mob_onsets[0]
                offset = ref_onset - mob_onset
                drift_factor = self.get_drift(ref_onsets, mob_onsets)
                offsets[os.path.basename(path)] = {
                    "time_offset": offset,
                    "drift_factor": drift_factor
                }
                print(f"[Aligner] {os.path.basename(path)} offset: {offset:.4f}s, drift: {drift_factor:.6f}")
            else:
                print(f"[Aligner] Need two sync onsets for {os.path.basename(path)}.")
        
        return offsets

    def get_drift(self, ref_onsets, mob_onsets):
        if len(ref_onsets) < 2 or len(mob_onsets) < 2:
            return 1.0
        ref_span = ref_onsets[-1] - ref_onsets[0]
        mob_span = mob_onsets[-1] - mob_onsets[0]
        if ref_span <= 0 or mob_span <= 0:
            return 1.0
        return self._bounded_drift(ref_span / mob_span, "two sync onsets")

    def _bounded_drift(self, drift, source):
        if 0.95 <= drift <= 1.05:
            return drift
        print(f"[Aligner] WARNING: Ignoring implausible drift factor {drift:.6f} from {source}.")
        return 1.0
