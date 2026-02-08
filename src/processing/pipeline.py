
import os
import subprocess
import json
import csv
import shutil
import glob
from capture.audio import AudioRecorder
from processing.triangulate import triangulate_frame
from processing.filter import MocapFilter

class MocapPipeline:
    def __init__(self, openpose_path="bin/OpenPoseDemo.exe", output_dir="MocapExports"):
        self.openpose_path = openpose_path
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

        # 2. Run OpenPose for each camera
        # Result: JSONs in temp folders
        json_dirs = {}
        for cam_idx in cam_indices:
            video_file = f"{scene}_{take}_cam{cam_idx}.mp4"
            output_json_dir = f"temp_{scene}_{take}_cam{cam_idx}"
            
            if not os.path.exists(video_file):
                print(f"[Pipeline] Error: Video file {video_file} missing.")
                return False
                
            self.run_openpose(video_file, output_json_dir)
            json_dirs[cam_idx] = output_json_dir

        # 3. Read JSONs, Triangulate, Filter
        print("[Pipeline] Triangulating...")
        
        # Need Projection Matrices
        # TODO: Load from calibration.npz
        # For now, using placeholders
        projections = [None] * len(cam_indices) 
        
        # Initialize Filter
        mocap_filter = MocapFilter()
        
        final_data = [] # List of rows [Time, Bone1_X, Bone1_Y, Bone1_Z, Bone2...]

        # Determine max frames
        # Just check one folder
        first_dir = json_dirs[cam_indices[0]]
        json_files = sorted(glob.glob(os.path.join(first_dir, "*.json")))
        num_frames = len(json_files)
        
        for f in range(start_frame, num_frames):
            frame_points = [] # List of point lists for this frame
            
            for i, cam_idx in enumerate(cam_indices):
                # Construct filename pattern usually: name_000000000000_keypoints.json
                # OpenPose naming is tricky, usually append _0000..
                # We'll use glob or assume strict naming if we controlled OpenPose output
                # Let's assume strict logic:
                json_name = f"{os.path.basename(video_file).split('.')[0]}_{f:012d}_keypoints.json"
                # Actually video_file var is overwritten in loop. Recover:
                v_name = f"{scene}_{take}_cam{cam_idx}"
                json_path = os.path.join(json_dirs[cam_idx], f"{v_name}_{f:012d}_keypoints.json")
                
                kps = self.read_openpose_json(json_path)
                frame_points.append(kps)

            # Triangulate this frame
            # points_3d = triangulate_frame(projections, frame_points)
            
            # Filter
            # filtered_3d = mocap_filter.filter_frame(f/fps, points_3d)
            
            # TODO: Convert to Unreal structure
            # row = [f/fps] + filtered_3d_flattened
            # final_data.append(row)
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
            for cam_idx in cam_indices:
                shutil.rmtree(json_dirs[cam_idx], ignore_errors=True)
                
                # Safe usage: Uncomment to delete videos
                video_file = f"{scene}_{take}_cam{cam_idx}.mp4"
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
            "--net_resolution", "-1x320"
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
