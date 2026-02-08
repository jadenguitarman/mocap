
import numpy as np
import cv2

def DLT(P_list, points_list):
    """
    Direct Linear Transform for N views.
    
    Args:
        P_list: List of 3x4 Projection Matrices for each camera.
        points_list: List of (u, v) tuples for the point in each camera.
                     Must match the order of P_list.
                     If a point is missing (e.g. occlusion), pass None and the corresponding P will be skipped.
    
    Returns:
        np.array([x, y, z]): The triangulated 3D point.
    """
    A = []

    for P, point in zip(P_list, points_list):
        if point is None:
            continue
            
        u, v = point
        
        # P is 3x4
        # equation: u = (P0*X) / (P2*X)  =>  u*(P2*X) - P0*X = 0
        
        row1 = u * P[2] - P[0]
        row2 = v * P[2] - P[1]
        
        A.append(row1)
        A.append(row2)

    A = np.array(A)
    
    if len(A) < 4:
        # Not enough data (need at least 2 cameras -> 4 equations)
        return None

    # Solve A*X = 0 using SVD
    # X is the last column of V^T (or last row of V in numpy's svd if computing full matrices)
    u, s, vh = np.linalg.svd(A)
    
    X = vh[-1]
    
    # Normalize homogeneous coordinates
    if X[3] != 0:
        X = X[:3] / X[3]
    else:
        return None # Point at infinity

    return X

def triangulate_frame(projection_matrices, keypoints_per_camera):
    """
    Triangulates all keypoints for a single frame.
    
    Args:
        projection_matrices: List of P matrices.
        keypoints_per_camera: List of keypoint lists. 
                              shape: (num_cameras, num_keypoints, 2) or dicts.
                              
    Returns:
        List of 3D points.
    """
    num_keypoints = len(keypoints_per_camera[0])
    points_3d = []
    
    for i in range(num_keypoints):
        points_2d = []
        for cam_idx in range(len(projection_matrices)):
            # Assuming keypoints_per_camera is a list of lists of (u,v)
            kp = keypoints_per_camera[cam_idx][i]
            # Check confidence if available? OpenPose usually gives (x, y, confidence)
            if len(kp) >= 3 and kp[2] < 0.1: # Low confidence
                points_2d.append(None)
            else:
                points_2d.append(kp[:2])
            
        pt_3d = DLT(projection_matrices, points_2d)
        points_3d.append(pt_3d)
        
    return points_3d
