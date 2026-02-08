
import cv2
import cv2.aruco as aruco
import numpy as np
import os
import glob
import json

class CameraCalibrator:
    def __init__(self, rows=7, columns=5, square_length=0.04, marker_length=0.02):
        # Default Board Settings (adjust as needed)
        self.CHARUCOBOARD_ROWCOUNT = rows
        self.CHARUCOBOARD_COLCOUNT = columns
        self.ARUCO_DICT = aruco.getPredefinedDictionary(aruco.DICT_6X6_250)
        self.board = aruco.CharucoBoard((self.CHARUCOBOARD_COLCOUNT, self.CHARUCOBOARD_ROWCOUNT),
                                        square_length, marker_length, self.ARUCO_DICT)
        self.board.setLegacyPattern(True) # Depending on OpenCV version/board used

    def calibrate_intrinsics(self, image_files, save_path="intrinsics.npz"):
        """
        Calibrates a single camera using a set of images.
        """
        all_corners = []
        all_ids = []
        imsize = None

        print(f"Detecting ChArUco corners in {len(image_files)} images...")
        for fname in image_files:
            img = cv2.imread(fname)
            if img is None: continue
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            imsize = gray.shape[::-1]

            corners, ids, rejected = aruco.detectMarkers(gray, self.ARUCO_DICT)

            if len(corners) > 0:
                ret, c_corners, c_ids = aruco.interpolateCornersCharuco(
                    corners, ids, gray, self.board)
                if ret > 0 and c_ids is not None and len(c_ids) > 6:
                    all_corners.append(c_corners)
                    all_ids.append(c_ids)
        
        if len(all_corners) == 0:
            print("No corners detected.")
            return None

        print("Calibrating camera...")
        ret, camera_matrix, dist_coeffs, rvecs, tvecs = aruco.calibrateCameraCharuco(
            all_corners, all_ids, self.board, imsize, None, None)

        print(f"Calibration Reprojection Error: {ret}")
        np.savez(save_path, mtx=camera_matrix, dist=dist_coeffs, ret=ret)
        return camera_matrix, dist_coeffs

    def estimate_pose(self, image_path, camera_matrix, dist_coeffs):
        """
        Estimates the camera pose relative to the board (World Origin).
        """
        img = cv2.imread(image_path)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        corners, ids, rejected = aruco.detectMarkers(gray, self.ARUCO_DICT)
        
        if len(corners) > 0:
            ret, c_corners, c_ids = aruco.interpolateCornersCharuco(
                corners, ids, gray, self.board)
            if ret > 0:
                valid, rvec, tvec = aruco.estimatePoseCharucoBoard(
                    c_corners, c_ids, self.board, camera_matrix, dist_coeffs, None, None)
                if valid:
                    return rvec, tvec
        return None, None

def calibrate_all_cameras(data_dir="calibration_data", output_file="calibration.npz"):
    # Expected structure: data_dir/cam0/*.jpg, data_dir/cam1/*.jpg, etc.
    calib_data = {}
    
    # Needs to be adapted to finding folders
    # For this simplified implementation, let's assume we capture a set of synced images 
    # for EXTRINSICS, but use a video sweep for INTRINSICS.
    # OR, we just grab one frame from each camera where the board is visible to define 0,0,0
    
    pass

if __name__ == "__main__":
    # Example usage CLI could go here
    pass
