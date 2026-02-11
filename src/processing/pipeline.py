
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
        
        self.output_dir = output_dir

        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def process_session(self, scene, take, cam_indices, fps=30):
        print(f"[Pipeline] Starting processing for {scene}_{take}")
        
        # 1. Audio Sync
        audio_file = f"{scene}_{take}_audio.wav"
        sync_time = AudioRecorder.find_sync_spike(audio_file)
        if sync_time is None:
            print("[Pipeline] Error: No sync spike found. Defaulting to 0.")
            sync_time = 0
            
        start_frame = int(sync_time * fps)
        print(f"[Pipeline] Sync Frame: {start_frame}")

        # 1.5 Align Mobile Uploads
        # Logic: Check uploads folder for matching scene/take audio
        aligner = AudioAligner()
        upload_pattern = os.path.join("uploads", f"{scene}_{take}_*.webm")
        mobile_files = glob.glob(upload_pattern)
        
        mobile_offsets = {}
        if mobile_files:
            print(f"[Pipeline] Found {len(mobile_files)} mobile uploads. Aligning...")
            # We need the master audio path for the aligner
            # Note: Aligner uses librosa, which is fine.
            # Calculate offsets relative to Master Audio
            # Offset = Mobile_Start - Master_Start?
            # No, we want the DELAY.
            # If Master Clap is at 2.0s. Mobile Clap is at 5.0s.
            # Mobile is AHEAD by 3.0s (recorded 3s of junk before clap, vs 2s of junk).
            # To sync, we assume Clap is Frame 0.
            # So Mobile Frame 0 is at 5.0s. Master Frame 0 is at 2.0s.
            # We want everything relative to Master.
            
            mobile_offsets = aligner.calculate_offsets(audio_file, mobile_files)
        else:

            print("[Pipeline] No mobile uploads found.")
            
        # --- PREPARE INPUTS ---
        # Combine local cameras and mobile uploads into a unified list of "views"
        # View Structure: { 'type': 'local'/'mobile', 'id': cam_idx/filename, 'video_path': path, 'offset': time_offset }
        
        views = []
        for cam_idx in cam_indices:
            views.append({
                'type': 'local',
                'id': cam_idx,
                'video_path': f"{scene}_{take}_cam{cam_idx}.mp4",
                'offset': 0.0
            })
            
        for mob_file in mobile_files:
            fname = os.path.basename(mob_file)
            offset_info = mobile_offsets.get(fname, {'time_offset': 0.0})
            views.append({
                'type': 'mobile',
                'id': fname,
                'video_path': mob_file,
                'offset': offset_info['time_offset']
            })
            
        print(f"[Pipeline] Processing {len(views)} views (Local + Mobile)...")

        # 2. Run OpenPose for each view
        # Result: JSONs in temp folders
        
        json_dirs = {}
        for view in views:
            video_file = view['video_path']
            # Create a unique temp dir
            # sanitize filename for dir
            safe_id = str(view['id']).replace('.','_')
            output_json_dir = f"temp_{scene}_{take}_{safe_id}"
            
            if not os.path.exists(video_file):
                print(f"[Pipeline] Error: Video file {video_file} missing.")
                continue
                
            self.run_openpose(video_file, output_json_dir)
            json_dirs[view['id']] = output_json_dir
            
        # 3. Load Calibration & Compute Projections
        # We need calibration data for TRIANGULATION.
        # If a view (e.g. mobile) is not in calibration.npz, we cannot triangulate it suitable for 3D.
        # But we can still export its 2D data if we wanted.
        # For now, we only triangulate views that have calibration data.
        
        calib_data = self.load_calibration()
        projections = []
        active_json_dirs = [] # parallel list to projections
        
        if calib_data:
            print("[Pipeline] Computing Projection Matrices...")
        else:
            print("[Pipeline] WARNING: No calibration data found! Triangulation will be skipped/invalid.")

        for view in views:
            # Check if we have calibration for this view
            if view['type'] == 'local' and calib_data:
                idx = str(view['id'])
                calib_id = idx
            elif view['type'] == 'mobile' and calib_data:
                # Mobile filename format: {scene}_{take}_{device_id}_{timestamp}.webm
                # We need to extract device_id.
                # But wait, view['id'] IS the filename "scene_take_device_time.webm"
                parts = view['id'].split('_')
                # scene_take_device_time.webm
                # We can't be 100% sure of the split if scene/take have underscores.
                # But we know the format from server/app.py: f"{scene}_{take}_{device_id}_{timestamp}.webm"
                # Let's rely on the fact that device_id is likely the 3rd to last part if we split by '_'???
                # Or better, regex.
                # Actually, the file naming is a bit loose.
                # Let's assume standard format.
                if len(parts) >= 4:
                    # device_id is parts[-2] if timestamp is last?
                    # filename: scene_take_sid_timestamp.webm
                    # sid is parts[-2]
                    sid = parts[-2]
                    calib_id = f"mobile_{sid}"
                else:
                    calib_id = "unknown"
            else:
                 calib_id = None

            if calib_id and f"mtx_{calib_id}" in calib_data:
                K = calib_data[f"mtx_{calib_id}"]
                rvec = calib_data[f"rvec_{calib_id}"]
                tvec = calib_data[f"tvec_{calib_id}"]
                
                # Compute P = K [R | t]
                R, _ = cv2.Rodrigues(rvec)
                Rt = np.hstack((R, tvec))
                P = K @ Rt
                
                projections.append(P)
                active_json_dirs.append(json_dirs[view['id']]) 
                print(f"[Pipeline] Added 3D View: {calib_id}")
            else:
                print(f"[Pipeline] Skipping View {view['id']} for 3D (No calibration data for {calib_id})")


        # 4. Read JSONs, Triangulate, Filter
        print(f"[Pipeline] Triangulating with {len(projections)} views...")
        
        # Initialize Filter
        mocap_filter = MocapFilter()
        
        final_data = [] # List of rows [Time, Bone0_X...]

        if len(projections) < 2:
            print("[Pipeline] Not enough calibrated views for triangulation (Need 2+).")
            # We will still proceed but final_data will be empty or handle gracefully
        
        # Determine max frames from the first active view
        if active_json_dirs:
            first_dir = active_json_dirs[0]
            # Files match pattern *_keypoints.json
            json_files = sorted(glob.glob(os.path.join(first_dir, "*_keypoints.json")))
            num_frames = len(json_files)
            
            # Frame Count Strategy: USE MINIMUM
            # Reasoning: Triangulation requires valid data from ALL calibrated cameras simultaneously.
            # If one camera stops early, we cannot resolve the 3D position reliably (or at all for 2-cam setups)
            # without complex missing-marker handling.
            # Therefore, the valid interaction period is the intersection of all camera timelines.
            num_frames = min([len(glob.glob(os.path.join(d, "*_keypoints.json"))) for d in active_json_dirs])
            print(f"[Pipeline] Processing {num_frames} frames (limited by shortest video).")

            
            for f in range(start_frame, num_frames):
                frame_points = [] # List of point lists for this frame
                
                valid_frame = True
                for j_dir in active_json_dirs:
                    # Construct filename. 
                    # OpenPose output format: {video_name_no_ext}_{frame_12d}_keypoints.json
                    # We need to find the file that *ends with* _{f:012d}_keypoints.json in this dir
                    # Easier to glob it or assume strict naming if we knew the video name exactly.
                    # Construction matching run_openpose:
                    # video_path -> basename -> splitext
                    # But we are iterating dirs directly...
                    
                    # Let's try to find the specific frame file
                    frame_suffix = f"_{f:012d}_keypoints.json"
                    candidates = glob.glob(os.path.join(j_dir, f"*{frame_suffix}"))
                    
                    if candidates:
                        json_path = candidates[0]
                        kps = self.read_openpose_json(json_path)
                        frame_points.append(kps)
                    else:
                        # Missing frame
                        frame_points.append([]) 
                        # Or mark frame invalid?
                
                # Triangulate this frame
                if len(frame_points) == len(projections):
                    points_3d = triangulate_frame(projections, frame_points)
                    
                    # Filter
                    timestamp = (f - start_frame) / fps
                    filtered_3d = mocap_filter.filter_frame(timestamp, points_3d)
                    
                    # Flatten into row
                    # points_3d is list of [x,y,z]
                    # We need [x1,y1,z1, x2,y2,z2...]
                    row = [timestamp]
                    for pt in filtered_3d:
                        if pt is not None:
                            row.extend(pt) # x, y, z
                        else:
                            row.extend([0,0,0]) # Missing point
                            
                    final_data.append(row)



            pass


        # 4. Export CSV
        csv_filename = os.path.join(self.output_dir, f"{scene}_{take}.csv")
        try:
            self.write_csv(final_data, csv_filename)
        except Exception as e:
            print(f"[Pipeline] Error writing CSV: {e}")
            return False
        
        # 5. Cleanup
        # Verify CSV exists and is not empty
        if os.path.exists(csv_filename) and os.path.getsize(csv_filename) > 0:
            print("[Pipeline] CSV verified. performing cleanup...")
            print("[Pipeline] CSV verified. performing cleanup...")
            for view in views:
                # Cleanup temp dirs
                if view['id'] in json_dirs:
                    shutil.rmtree(json_dirs[view['id']], ignore_errors=True)
                
                # Cleanup videos (Safe usage: Uncomment to delete)
                # if os.path.exists(view['video_path']):
                #    os.remove(view['video_path'])

                if os.path.exists(video_file):
                    os.remove(video_file)
                    print(f"[Pipeline] Deleted raw video: {video_file}")
        else:
            print("[Pipeline] WARNING: CSV verification failed. Keeping raw files.")

        return True


    def run_openpose(self, video_path, output_dir):
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        print(f"[Pipeline] Running OpenPose on {video_path}...")
        
        # Command: OpenPoseDemo.exe --video video.mp4 --write_json output_dir --display 0 --render_pose 0 --net_resolution -1x320
        cmd = [
            self.openpose_path,
            "--video", video_path,
            "--write_json", output_dir,
            "--display", "0",
            "--render_pose", "0",
            "--net_resolution", self.net_resolution
        ]

        
        # Mocking execution if binary missing
        try:
            subprocess.check_call(cmd)
        except FileNotFoundError:
            print("[Pipeline] OpenPose binary not found. Mocking JSON output...")
            # Create dummy JSONs for testing
            # self.create_dummy_jsons(output_dir, 100)

    def read_openpose_json(self, json_path):
        if not os.path.exists(json_path):
            return [] # Can happen if OpenPose failed for a frame
            
        with open(json_path, 'r') as f:
            data = json.load(f)
            
        # Extract BODY_25
        if not data['people']:
            return []
            
        # Get first person
        person = data['people'][0]
        # pose_keypoints_2d list
        kp = person['pose_keypoints_2d']
        
        # Convert to list of (x, y, c)
        points = []
        for i in range(0, len(kp), 3):
            points.append( kp[i:i+3] )
            
        return points

    def write_csv(self, data, filename):
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            # Header?
            header = ["Time"] + [f"Bone_{i}_{axis}" for i in range(25) for axis in ["X","Y","Z"]]
            writer.writerow(header)
            writer.writerows(data)
        print(f"[Pipeline] Exported {filename}")
        print(f"[Pipeline] Exported {filename}")

    def load_calibration(self):
        calib_path = config.get("Calibration", {}).get("save_path", "calibration.npz")
        if not os.path.exists(calib_path):
            return None
        try:
            return np.load(calib_path)
        except Exception as e:
            print(f"[Pipeline] Error loading calibration: {e}")
            return None
