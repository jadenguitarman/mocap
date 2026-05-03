
import os
import cv2
import time
import argparse
import requests
import sys
from processing.calibrate import CameraCalibrator
from utils.config import config


def ensure_dir(d):
    if not os.path.exists(d):
        os.makedirs(d)

def calibration_complete_ids(calib_data):
    complete = []
    for key in calib_data:
        if not key.startswith("mtx_"):
            continue
        cam_id = key.replace("mtx_", "")
        required = [f"dist_{cam_id}", f"rvec_{cam_id}", f"tvec_{cam_id}"]
        if all(req in calib_data for req in required):
            complete.append(cam_id)
    return sorted(complete)

def capture_calibration_images(cam_indices, output_dir="calibration_images", num_images=20, delay=2.0, no_ssl=False):
    print(f"Starting Multi-Cam Calibration Capture for cameras: {cam_indices}")
    print(f"Will capture {num_images} images with {delay}s delay.")
    print("Press 'q' to quit early.")
    
    ensure_dir(output_dir)
    
    caps = {}
    for idx in cam_indices:
        cap = cv2.VideoCapture(idx)
        # Set res from config
        width = config.get("Camera", {}).get("width", 1280)
        height = config.get("Camera", {}).get("height", 720)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        
        if cap.isOpened():
            caps[idx] = cap
        else:
            print(f"Error: Camera {idx} failed to open. Ensure no other app (including the Preview window) is using it.")
            # Release any opened ones
            for c in caps.values():
                c.release()
            return False

    # Create subdirs
    for idx in cam_indices:
        ensure_dir(os.path.join(output_dir, f"cam{idx}"))

    count = 0
    last_cap_time = time.time()
    
    try:
        while count < num_images:
            frames = {}
            # Read all frames
            for idx, cap in caps.items():
                ret, frame = cap.read()
                if ret:
                    frames[idx] = frame
            
            # Show preview of first cam
            if cam_indices and cam_indices[0] in frames:
                cv2.imshow("Calibration Capture (Press Q to Quit)", frames[cam_indices[0]])
                
            # Check timer
            if time.time() - last_cap_time > delay:
                print(f"Capturing set {count+1}/{num_images}...")
                for idx, frame in frames.items():
                    fname = os.path.join(output_dir, f"cam{idx}", f"img_{count:04d}.jpg")
                    cv2.imwrite(fname, frame)
                
                # Trigger Mobile Capture via Server
                try:
                    protocol = "http" if no_ssl else "https"
                    # Assuming server is running local
                    requests.post(f"{protocol}://127.0.0.1:5000/api/trigger_calibration", json={'count': count}, verify=False)
                except Exception as e:
                    print(f"Failed to trigger mobile sync: {e}")

                count += 1
                last_cap_time = time.time()

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
    finally:
        for cap in caps.values():
            cap.release()
        cv2.destroyAllWindows()
        
    print("Capture finished.")
    return True

def run_calibration(cam_indices, image_dir="calibration_images", output_file="calibration.npz"):
    
    calib_config = config.get("Calibration", {})
    rows = calib_config.get("rows", 7)
    cols = calib_config.get("columns", 5)
    sq_len = calib_config.get("square_length", 0.04)
    mk_len = calib_config.get("marker_length", 0.02)
    
    calibrator = CameraCalibrator(rows, cols, sq_len, mk_len)
    
    results = {}
    
    if not os.path.exists(image_dir):
        print(f"Error: Calibration images directory {image_dir} not found.")
        return False

    subdirs = [f.path for f in os.scandir(image_dir) if f.is_dir()]
    
    if not subdirs:
        print("Error: No camera subdirectories found in calibration_images.")
        return False

    # 1. Intrinsic Calibration
    for cam_dir in subdirs:
        dirname = os.path.basename(cam_dir)
        cam_id = dirname 
        
        images = [os.path.join(cam_dir, f) for f in os.listdir(cam_dir) if f.startswith("img_") and f.endswith(".jpg")]
        if not images:
            continue
            
        print(f"Calibrating Intrinsics for {cam_id} ({len(images)} images)...")
        res = calibrator.calibrate_intrinsics(images)
        if res:
            mtx, dist, ret = res
            results[f"mtx_{cam_id}"] = mtx
            results[f"dist_{cam_id}"] = dist
            results[f"ret_{cam_id}"] = ret
        else:
            print(f"  > Failed to calibrate {cam_id}")

    # 2. Extrinsic Calibration
    print("Calibrating Extrinsics (using img_0000.jpg)...")
    for cam_dir in subdirs:
        cam_id = os.path.basename(cam_dir)
        img_path = os.path.join(cam_dir, "img_0000.jpg")
        
        if os.path.exists(img_path) and f"mtx_{cam_id}" in results:
            rvec, tvec = calibrator.estimate_pose(img_path, results[f"mtx_{cam_id}"], results[f"dist_{cam_id}"])
            if rvec is not None:
                results[f"rvec_{cam_id}"] = rvec
                results[f"tvec_{cam_id}"] = tvec
                print(f"  > {cam_id} Pose Found.")
            else:
                print(f"  > {cam_id} Pose Failed for {cam_id}. Ensure board is visible in img_0000.jpg")
    
    complete_ids = calibration_complete_ids(results)
    if len(complete_ids) < 2:
        print("Calibration failed: fewer than two cameras produced complete intrinsics and extrinsics.")
        print("Make sure the ChArUco board is visible in img_0000.jpg for each camera and in enough calibration images.")
        if os.path.exists(output_file):
            print(f"Keeping previous calibration file unchanged: {output_file}")
        return False

    # Save atomically only after the result is known to be usable.
    import numpy as np
    tmp_output = output_file + ".tmp.npz"
    np.savez(tmp_output, **results)
    os.replace(tmp_output, output_file)
    print(f"Calibration saved to {output_file} for: {', '.join(complete_ids)}")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true", help="Run capture sequence first")
    parser.add_argument("--process", action="store_true", help="Run calibration processing")
    parser.add_argument("--no-ssl", action="store_true", help="Don't use SSL for server triggers")
    parser.add_argument("--indices", type=str, help="Comma separated camera indices (e.g. 0,1)")
    args = parser.parse_args()
    
    # Defaults
    if args.indices:
        cams = [int(i.strip()) for i in args.indices.split(",")]
    else:
        cams = config.get("Camera", {}).get("indices", [0])
    
    save_path = config.get("Calibration", {}).get("save_path", "calibration.npz")
    
    success = True
    if args.capture:
        if not capture_calibration_images(cams, no_ssl=args.no_ssl):
            success = False
            
    if success and args.process:
        if not run_calibration(cams, output_file=save_path):
            success = False
            
    if not args.capture and not args.process:
        print("Please specify --capture or --process (or both).")
        sys.exit(1)

    if not success:
        sys.exit(1)
