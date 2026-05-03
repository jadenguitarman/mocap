
import cv2
import cv2.aruco as aruco
import numpy as np
import os


class CameraCalibrator:
    def __init__(self, rows=7, columns=5, square_length=0.04, marker_length=0.02):
        self.CHARUCOBOARD_ROWCOUNT = rows
        self.CHARUCOBOARD_COLCOUNT = columns
        self.square_length = square_length
        self.marker_length = marker_length
        self.dictionary_candidates = [
            ("DICT_6X6_250", aruco.DICT_6X6_250),
            ("DICT_4X4_50", aruco.DICT_4X4_50),
            ("DICT_4X4_100", aruco.DICT_4X4_100),
            ("DICT_5X5_100", aruco.DICT_5X5_100),
            ("DICT_5X5_250", aruco.DICT_5X5_250),
            ("DICT_6X6_100", aruco.DICT_6X6_100),
            ("DICT_6X6_1000", aruco.DICT_6X6_1000),
        ]
        self.dictionary_name = "DICT_6X6_250"
        self.ARUCO_DICT = aruco.getPredefinedDictionary(aruco.DICT_6X6_250)
        self.board = self._make_board(self.ARUCO_DICT, legacy=False)
        self.blur_threshold = 80.0

    def sharpness_score(self, gray):
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    def _make_board(self, dictionary, legacy=False):
        board = aruco.CharucoBoard(
            (self.CHARUCOBOARD_COLCOUNT, self.CHARUCOBOARD_ROWCOUNT),
            self.square_length,
            self.marker_length,
            dictionary,
        )
        if hasattr(board, "setLegacyPattern"):
            board.setLegacyPattern(bool(legacy))
        return board

    def _detect_markers(self, gray, dictionary):
        parameters = aruco.DetectorParameters()
        if hasattr(aruco, "ArucoDetector"):
            detector = aruco.ArucoDetector(dictionary, parameters)
            return detector.detectMarkers(gray)
        return aruco.detectMarkers(gray, dictionary, parameters=parameters)

    def _interpolate_charuco(self, gray, corners, ids, board):
        if ids is None or len(corners) == 0:
            return None, None
        try:
            ret, c_corners, c_ids = aruco.interpolateCornersCharuco(corners, ids, gray, board)
            if ret and c_ids is not None and len(c_ids) > 0:
                return c_corners, c_ids
        except Exception:
            return None, None
        return None, None

    def _detect_charuco_with_board(self, gray, dictionary, board):
        corners, ids, _ = self._detect_markers(gray, dictionary)
        c_corners, c_ids = self._interpolate_charuco(gray, corners, ids, board)
        return corners, ids, c_corners, c_ids

    def _select_board(self, image_files):
        best = None
        sample_files = image_files[: min(len(image_files), 8)]
        print("Auto-detecting ChArUco dictionary/layout...")

        for dict_name, dict_id in self.dictionary_candidates:
            dictionary = aruco.getPredefinedDictionary(dict_id)
            for legacy in (False, True):
                board = self._make_board(dictionary, legacy=legacy)
                marker_hits = 0
                charuco_hits = 0
                max_corners = 0

                for fname in sample_files:
                    img = cv2.imread(fname)
                    if img is None:
                        continue
                    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                    corners, ids, c_corners, c_ids = self._detect_charuco_with_board(gray, dictionary, board)
                    marker_count = 0 if ids is None else len(ids)
                    corner_count = 0 if c_ids is None else len(c_ids)
                    marker_hits += marker_count
                    charuco_hits += corner_count
                    max_corners = max(max_corners, corner_count)

                print(f"  {dict_name}, legacy={legacy}: markers={marker_hits}, charuco_corners={charuco_hits}")
                score = (charuco_hits, marker_hits, max_corners)
                if best is None or score > best["score"]:
                    best = {
                        "score": score,
                        "dict_name": dict_name,
                        "dictionary": dictionary,
                        "legacy": legacy,
                        "board": board,
                    }

        if best and best["score"][0] > 0:
            self.dictionary_name = best["dict_name"]
            self.ARUCO_DICT = best["dictionary"]
            self.board = best["board"]
            print(f"Selected {best['dict_name']} with legacy={best['legacy']}.")
            return True

        print("No ChArUco corners found with the common dictionaries/layouts.")
        return False

    def calibrate_intrinsics(self, image_files, save_path="intrinsics.npz"):
        """
        Calibrates a single camera using a set of images.
        """
        all_corners = []
        all_ids = []
        imsize = None

        print(f"Detecting ChArUco corners in {len(image_files)} images...")
        if not self._select_board(image_files):
            return None

        per_image_counts = []
        sharpness_scores = []
        for fname in image_files:
            img = cv2.imread(fname)
            if img is None: continue
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            imsize = gray.shape[::-1]
            sharpness = self.sharpness_score(gray)
            sharpness_scores.append(sharpness)
            corners, ids, c_corners, c_ids = self._detect_charuco_with_board(gray, self.ARUCO_DICT, self.board)
            marker_count = 0 if ids is None else len(ids)
            corner_count = 0 if c_ids is None else len(c_ids)
            per_image_counts.append((os.path.basename(fname), marker_count, corner_count))
            if c_ids is not None and len(c_ids) > 6:
                all_corners.append(c_corners)
                all_ids.append(c_ids)
        
        if len(all_corners) == 0:
            print("No corners detected.")
            if sharpness_scores:
                avg_sharpness = sum(sharpness_scores) / len(sharpness_scores)
                print(f"Average image sharpness: {avg_sharpness:.1f} (target: {self.blur_threshold:.1f}+).")
                if avg_sharpness < self.blur_threshold:
                    print("Calibration images appear blurry. Improve focus/lighting or move the board farther away before retrying.")
            print("Per-image marker/corner counts:")
            for fname, marker_count, corner_count in per_image_counts:
                print(f"  {fname}: markers={marker_count}, charuco_corners={corner_count}")
            return None

        print("Calibrating camera...")
        # Note: calibrateCameraCharuco still exists in both versions but behavior slightly varies
        try:
            ret, camera_matrix, dist_coeffs, rvecs, tvecs = aruco.calibrateCameraCharuco(
                all_corners, all_ids, self.board, imsize, None, None)
        except Exception as e:
            print(f"Calibration failed: {e}")
            return None

        print(f"Calibration Reprojection Error: {ret}")
        # np.savez(save_path, mtx=camera_matrix, dist=dist_coeffs, ret=ret) # Handled by caller now
        return camera_matrix, dist_coeffs, ret


    def estimate_pose(self, image_path, camera_matrix, dist_coeffs):
        """
        Estimates the camera pose relative to the board (World Origin).
        """
        img = cv2.imread(image_path)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        corners, ids, c_corners, c_ids = self._detect_charuco_with_board(gray, self.ARUCO_DICT, self.board)
        if c_ids is not None and len(c_ids) > 6:
            valid, rvec, tvec = aruco.estimatePoseCharucoBoard(
                c_corners, c_ids, self.board, camera_matrix, dist_coeffs, None, None)
            if valid:
                return rvec, tvec
        return None, None


