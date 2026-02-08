
import math

class LowPassFilter(object):
    def __init__(self, alpha):
        self.__setAlpha(alpha)
        self.y = None
        self.s = None

    def __setAlpha(self, alpha):
        alpha = float(alpha)
        if alpha <= 0 or alpha > 1.0:
            raise ValueError("alpha (%s) should be in (0.0, 1.0]" % alpha)
        self.alpha = alpha

    def __call__(self, value, timestamp=None, alpha=None):
        if alpha is not None:
            self.__setAlpha(alpha)
        if self.y is None:
            s = value
        else:
            s = self.alpha * value + (1.0 - self.alpha) * self.s
        self.y = value
        self.s = s
        return s
    
    def lastValue(self):
        return self.y

class OneEuroFilter(object):
    def __init__(self, t0, x0, min_cutoff=1.0, beta=0.0, d_cutoff=1.0):
        """
        min_cutoff: Decrease to reduce jitter
        beta: Increase to reduce lag
        """
        self.t_prev = t0
        self.x_prev = x0
        self.dx_prev = 0.0
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.d_cutoff = float(d_cutoff)
        
        self.x_filt = x0
        
        alpha = self.alpha(self.min_cutoff) 
        self.x_filt = LowPassFilter(alpha)
        self.dx_filt = LowPassFilter(self.alpha(self.d_cutoff))

    def alpha(self, cutoff):
        te = 1.0 / 30.0 # Default fallback if dt is 0
        r = 2 * math.pi * cutoff * te
        return r / (r + 1)

    def __call__(self, t, x):
        if self.t_prev is None:
            dt = 1.0/30.0 # Default
        else:
            dt = t - self.t_prev
            
        self.t_prev = t

        dx = 0.0
        if self.x_prev is not None and dt > 0:
            dx = (x - self.x_prev) / dt
            
        edx = self.dx_filt(dx, alpha=self.smoothing_factor(dt, self.d_cutoff))
        cutoff = self.min_cutoff + self.beta * abs(edx)
        
        x_filtered = self.x_filt(x, alpha=self.smoothing_factor(dt, cutoff))
        
        self.x_prev = x_filtered
        return x_filtered

    def smoothing_factor(self, dt, cutoff):
        r = 2 * math.pi * cutoff * dt
        return r / (r + 1)

class MocapFilter:
    def __init__(self, num_points=25, min_cutoff=1.0, beta=0.0):
        self.filters = []
        for _ in range(num_points * 3): # x, y, z for each point
            self.filters.append(OneEuroFilter(0, 0, min_cutoff, beta))
            
    def filter_frame(self, t, points_3d):
        """
        points_3d: List of [x, y, z] or flatted list
        """
        filtered = []
        # Flatten input if needed or iterate
        # Assumes points_3d is list of [x, y, z]
        
        flat_points = [c for p in points_3d for c in p]
        
        if len(flat_points) != len(self.filters):
            # Re-init if size changes (e.g. variable number of people?)
            # For standard body tracking, point count is fixed (BODY_25)
            pass 
            
        filtered_flat = []
        for i, val in enumerate(flat_points):
            f_val = self.filters[i](t, val)
            filtered_flat.append(f_val)
            
        # Re-structure
        filtered_points = []
        for i in range(0, len(filtered_flat), 3):
            filtered_points.append(filtered_flat[i:i+3])
            
        return filtered_points
