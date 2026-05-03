
import os
import subprocess
import json
import csv
import shutil
import glob
import cv2
import numpy as np

from capture.audio import AudioRecorder
from processing.triangulate import triangulate_frame
from processing.filter import MocapFilter
from processing.aligner import AudioAligner
from utils.config import config


class MocapPipeline:
    def __init__(self, openpose_path=None, output_dir="MocapExports"):
        op_config = config.get("OpenPose", {})
        self.openpose_path = openpose_path or op_config.get("binary_path", "bin/OpenPoseDemo.exe")
        self.net_resolution = op_config.get("net_resolution", "-1x320")
        
        self.output_dir = os.path.abspath(output_dir)

        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        # 1. Dependency Check: FFmpeg
        self.has_ffmpeg = self._check_ffmpeg()
        if not self.has_ffmpeg:
            print("\n" + "!"*60)
            print("WARNING: FFmpeg not found on your system!")
            print("Mobile uploads (WebM) cannot be processed without FFmpeg.")
            print("PLEASE RESTART YOUR TERMINAL (or VS Code) to refresh your PATH.")
            print("If you just installed it, a restart is required for Python to see it.")
            print("!"*60 + "\n")

    def _check_ffmpeg(self):
        try:
            # Check standard path
            subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except OSError:
            return False

    def process_session(self, scene, take, cam_indices, fps=30):
        print(f"[Pipeline] Starting processing for {scene}_{take}")
        
        # 1. Audio Sync
        audio_file = os.path.abspath(f"{scene}_{take}_audio.wav")
        sync_time = AudioRecorder.find_sync_spike(audio_file)
        if sync_time is None:
            print("[Pipeline] Error: No sync spike found. Keep the raw files and record a loud clap or sync blip.")
            return False
            
        start_frame = int(sync_time * fps)
        print(f"[Pipeline] Sync Frame: {start_frame}")

        # 1.5 Align Mobile Uploads
        aligner = AudioAligner()
        upload_pattern = os.path.join("uploads", f"{scene}_{take}_*.webm")
        mobile_files = [os.path.abspath(f) for f in glob.glob(upload_pattern)]
        
        mobile_offsets = {}
        if mobile_files:
            print(f"[Pipeline] Found {len(mobile_files)} mobile uploads. Aligning...")
            mobile_offsets = aligner.calculate_offsets(audio_file, mobile_files)
        else:
            print("[Pipeline] No mobile uploads found.")
            
        # --- PREPARE INPUTS ---
        views = []
        for cam_idx in cam_indices:
            v_path = os.path.abspath(f"{scene}_{take}_cam{cam_idx}.mp4")
            views.append({
                'type': 'local',
                'id': cam_idx,
                'video_path': v_path,
                'offset': 0.0
            })
            
        for mob_file in mobile_files:
            fname = os.path.basename(mob_file)
            if fname not in mobile_offsets:
                print(f"[Pipeline] Error: Mobile file {fname} does not have two-point audio alignment.")
                return False
            offset_info = mobile_offsets[fname]
            device_id = self.extract_mobile_device_id(fname, scene, take)
            views.append({
                'type': 'mobile',
                'id': fname,
                'calib_id': f"mobile_{device_id}",
                'video_path': mob_file,
                'offset': offset_info['time_offset'],
                'drift_factor': offset_info.get('drift_factor', 1.0),
            })
            
        print(f"[Pipeline] Processing {len(views)} views (Local + Mobile)...")
        if len(views) < 2:
            print("[Pipeline] Error: At least two camera views are required for 3D triangulation.")
            return False

        # 2. Run OpenPose for each view
        json_dirs = {}
        for view in views:
            video_file = view['video_path']
            safe_id = str(view['id']).replace('.','_')
            output_json_dir = os.path.abspath(f"temp_{scene}_{take}_{safe_id}")
            
            if not os.path.exists(video_file):
                print(f"[Pipeline] Error: Video file {video_file} missing.")
                return False
                
            if not self.run_openpose(video_file, output_json_dir):
                print(f"[Pipeline] Error: OpenPose failed for {video_file}. Keeping raw files for retry.")
                return False
            json_dirs[view['id']] = output_json_dir
            
        # 3. Load Calibration & Compute Projections
        calib_data = self.load_calibration()
        projections = []
        active_views = []
        
        if calib_data is not None:
            print("[Pipeline] Computing Projection Matrices...")
        else:
            print("[Pipeline] Error: No valid calibration data found.")
            return False

        for view in views:
            calib_id = None
            if view['type'] == 'local' and calib_data is not None:
                # Local IDs must match filename prefix in calibration (e.g. mtx_cam0)
                calib_id = f"cam{view['id']}"
            elif view['type'] == 'mobile' and calib_data is not None:
                calib_id = view.get("calib_id", "unknown")

            if calib_id and f"mtx_{calib_id}" in calib_data:
                K = calib_data[f"mtx_{calib_id}"]
                rvec = calib_data[f"rvec_{calib_id}"]
                tvec = calib_data[f"tvec_{calib_id}"]
                
                R, _ = cv2.Rodrigues(rvec)
                Rt = np.hstack((R, tvec))
                P = K @ Rt
                
                projections.append(P)
                active_views.append({
                    "id": view["id"],
                    "json_dir": json_dirs[view["id"]],
                    "frame_offset": int(round(view.get("offset", 0.0) * fps)),
                    "drift_factor": view.get("drift_factor", 1.0),
                })
                print(f"[Pipeline] Added 3D View: {calib_id}")
            else:
                print(f"[Pipeline] Skipping View {view['id']} for 3D (No calibration data for {calib_id})")

        # 4. Read JSONs, Triangulate, Filter
        print(f"[Pipeline] Triangulating with {len(projections)} views...")
        mocap_filter = MocapFilter()
        final_data = []

        if len(projections) < 2:
            print("[Pipeline] Not enough calibrated views for triangulation (Need 2+).")
            print("[Pipeline] NOTE: You MUST run the CALIBRATE step for each camera before processing.")
            return False
        
        if active_views:
            view_counts = [
                len(glob.glob(os.path.join(v["json_dir"], "*_keypoints.json")))
                for v in active_views
            ]
            if not view_counts:
                print("[Pipeline] Error: No valid JSON frames found in any calibrated view.")
                return False
            else:
                available_after_sync = [
                    int((count - max(0, start_frame - v["frame_offset"])) * v["drift_factor"])
                    for count, v in zip(view_counts, active_views)
                ]
                num_output_frames = min(available_after_sync)
                if num_output_frames <= 0:
                    print("[Pipeline] Error: No frames remain after sync alignment.")
                    return False
                print(f"[Pipeline] Processing {num_output_frames} synced frames.")

            for out_frame in range(num_output_frames):
                frame_points = []
                for view in active_views:
                    source_start = start_frame - view["frame_offset"]
                    source_frame = source_start + int(round(out_frame / view["drift_factor"]))
                    if source_frame < 0:
                        frame_points.append([])
                        continue
                    frame_suffix = f"_{source_frame:012d}_keypoints.json"
                    candidates = glob.glob(os.path.join(view["json_dir"], f"*{frame_suffix}"))
                    
                    if candidates:
                        json_path = candidates[0]
                        kps = self.read_openpose_json(json_path)
                        frame_points.append(kps)
                    else:
                        frame_points.append([]) 
                
                if len(frame_points) == len(projections):
                    points_3d = triangulate_frame(projections, frame_points)
                    timestamp = out_frame / fps
                    filtered_3d = mocap_filter.filter_frame(timestamp, points_3d)
                    
                    row = [timestamp]
                    for pt in filtered_3d:
                        if pt is not None:
                            row.extend(pt)
                        else:
                            row.extend([0,0,0])
                    final_data.append(row)
        else:
            print("[Pipeline] Error: No active calibrated views available.")
            return False

        if not final_data:
            print("[Pipeline] Error: Triangulation produced no animation rows. Keeping raw files.")
            return False

        # 4. Export CSV
        csv_filename = os.path.join(self.output_dir, f"{scene}_{take}.csv")
        try:
            self.write_csv(final_data, csv_filename)
        except Exception as e:
            print(f"[Pipeline] Error writing CSV: {e}")
            return False
        
        # 5. Cleanup
        if self.verify_csv(csv_filename):
            print("[Pipeline] CSV verified. performing cleanup...")
            for view in views:
                if view['id'] in json_dirs:
                    shutil.rmtree(json_dirs[view['id']], ignore_errors=True)
                
                if os.path.exists(view['video_path']):
                    os.remove(view['video_path'])
                    print(f"[Pipeline] Deleted raw video: {view['video_path']}")
        else:
            print("[Pipeline] WARNING: CSV verification failed. Keeping raw files.")

        return True

    @staticmethod
    def extract_mobile_device_id(filename, scene, take):
        upload_prefix = f"{scene}_{take}_"
        upload_stem = os.path.splitext(os.path.basename(filename))[0]
        if upload_stem.startswith(upload_prefix):
            rest = upload_stem[len(upload_prefix):]
            return rest.rsplit("_", 1)[0]
        return upload_stem.rsplit("_", 1)[0]

    def run_openpose(self, video_path, output_dir):
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        print(f"[Pipeline] Running OpenPose on {video_path}...")
        
        # OpenPose MUST be run from its root directory to find models.
        # We also need to use absolute paths since we're changing CWD.
        op_binary = os.path.abspath(self.openpose_path)
        op_root = os.path.dirname(os.path.dirname(op_binary))
        
        # Convert project-relative paths to absolute
        abs_video = os.path.abspath(video_path)
        abs_output = os.path.abspath(output_dir)

        # Get the relative path of binary from root (usually bin/OpenPoseDemo.exe)
        # We use the literal name since on Windows we want to trigger the .exe
        bin_filename = os.path.basename(op_binary)
        bin_rel = os.path.join("bin", bin_filename)

        cmd = [
            bin_rel,
            "--video", abs_video,
            "--write_json", abs_output,
            "--display", "0",
            "--render_pose", "0",
            "--net_resolution", self.net_resolution
        ]
        
        if not os.path.exists(op_binary):
            print(f"[Pipeline] OpenPose binary not found: {op_binary}")
            return False

        try:
            # Run from OpenPose root
            subprocess.check_call(cmd, cwd=op_root)
            json_count = len(glob.glob(os.path.join(output_dir, "*_keypoints.json")))
            if json_count == 0:
                print("[Pipeline] OpenPose completed but produced no keypoint JSON files.")
                return False
            return True
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            print(f"[Pipeline] OpenPose failed (Root: {op_root}). Error: {e}")
            return False

    def read_openpose_json(self, json_path):
        if not os.path.exists(json_path):
            return []
            
        with open(json_path, 'r') as f:
            data = json.load(f)
            
        if not data['people']:
            return []
            
        person = data['people'][0]
        kp = person['pose_keypoints_2d']
        points = []
        for i in range(0, len(kp), 3):
            points.append( kp[i:i+3] )
        return points

    def write_csv(self, data, filename):
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            header = ["Time"] + [f"Bone_{i}_{axis}" for i in range(25) for axis in ["X","Y","Z"]]
            writer.writerow(header)
            writer.writerows(data)
        print(f"[Pipeline] Exported {filename}")

    def verify_csv(self, filename):
        if not os.path.exists(filename) or os.path.getsize(filename) <= 0:
            return False
        try:
            with open(filename, newline='') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                first_row = next(reader, None)
            expected_cols = 1 + 25 * 3
            return bool(header and first_row and len(header) == expected_cols and len(first_row) == expected_cols)
        except Exception as e:
            print(f"[Pipeline] CSV verification error: {e}")
            return False

    def load_calibration(self):
        calib_path = config.get("Calibration", {}).get("save_path", "calibration.npz")
        if not os.path.exists(calib_path):
            return None
        try:
            data = np.load(calib_path)
            complete = []
            for key in data.files:
                if not key.startswith("mtx_"):
                    continue
                cam_id = key.replace("mtx_", "")
                required = [f"dist_{cam_id}", f"rvec_{cam_id}", f"tvec_{cam_id}"]
                if all(req in data.files for req in required):
                    complete.append(cam_id)
            if len(complete) < 2:
                print(f"[Pipeline] Calibration file is incomplete. Complete cameras: {complete or 'none'}")
                return None
            return data
        except Exception as e:
            print(f"[Pipeline] Error loading calibration: {e}")
            return None
