
import threading
import customtkinter as ctk
import subprocess
import sys
import os
from osc.client import MocapOSC
from capture.audio import AudioRecorder
from processing.pipeline import MocapPipeline
from utils.config import config
import tkinter.messagebox as msgbox
import socket
import requests
import time
import cv2
from PIL import Image
import concurrent.futures
import qrcode
import shutil
import logging
import urllib3

# Try to import winsound for sync blip (Windows only)
try:
    import winsound
except ImportError:
    winsound = None

logger = logging.getLogger(__name__)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    cv2.setLogLevel(0)
except AttributeError:
    logger.debug("OpenCV log level control is not available in this build.")

CAMERA_BACKEND = getattr(cv2, "CAP_MSMF", 0)


import io

def configure_capture(cap):
    cam_config = config.get("Camera", {})
    width = cam_config.get("width", 1920)
    height = cam_config.get("height", 1080)
    fps = cam_config.get("fps", 30)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    if hasattr(cv2, "CAP_PROP_FOURCC"):
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    if hasattr(cv2, "CAP_PROP_AUTOFOCUS"):
        cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)
    if hasattr(cv2, "CAP_PROP_AUTO_EXPOSURE"):
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)
    return cap

class LivePreviewWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Live Camera Preview")
        self.geometry("800x600")
        self.parent = parent
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        self.scroll = ctk.CTkScrollableFrame(self)
        self.scroll.grid(row=0, column=0, sticky="nsew")
        
        self.previews = {} # id -> label
        self.running = True
        
        # State Management
        self.is_recording = False
        self.is_calibrating = False
        self.writers = {} # did -> cv2.VideoWriter
        self.record_params = {} # scene, take
        self.calib_params = {} # count, delay, last_time, no_ssl
        
        self.calib_saved_count = {} # did -> count
        
        self.caps = {} # id -> cv2.VideoCapture (Persistent)
        self.session = requests.Session() # Reuse connections

        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=8) # Parallel fetch
        
        self.update_thread = threading.Thread(target=self.update_loop, daemon=True)
        self.update_thread.start()

        
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        self.running = False
        try:
            self.session.close()
        except Exception as e:
            logger.warning("Preview HTTP session cleanup failed: %s", e)
        self.executor.shutdown(wait=False)
        # Cleanup any active writers
        for w in self.writers.values():
            w.release()
        # Release caps
        for cap in self.caps.values():
            cap.release()
        self.destroy()

    def start_recording(self, scene, take):
        self.record_params = {'scene': scene, 'take': take}
        self.is_recording = True
        print(f"[Preview] Started recording for {scene}_{take}")

    def stop_recording(self):
        self.is_recording = False
        for did in list(self.writers.keys()):
            self.writers[did].release()
            del self.writers[did]
        print("[Preview] Stopped recording and released writers.")

    def start_calibration(self, indices, num_images=20, delay=3.0, no_ssl=False):
        self.calib_params = {
            'indices': [str(i) for i in indices],
            'num_images': num_images,
            'delay': delay,
            'no_ssl': no_ssl,
            'count': 0,
            'last_time': time.time() + 5.0 # Set last_time to far in future to delay start
        }
        self.calib_saved_count = {} # Reset
        self.is_calibrating = True
        # Ensure subdirs exist
        os.makedirs("calibration_images", exist_ok=True)
        for idx in indices:
            os.makedirs(os.path.join("calibration_images", f"cam{idx}"), exist_ok=True)
        print(f"[Preview] Multi-Cam Calibration Mode Active ({num_images} images, {delay}s delay). Starting in 5 seconds...")

    def stop_calibration(self):
        self.is_calibrating = False
        print("[Preview] Calibration Capture Finished.")

    def fetch_frame(self, dev, protocol):
        did = str(dev['id'])
        dtype = dev['type']
        img = None
        
        try:
            if dtype == 'local':
                if did not in self.caps:
                    self.caps[did] = configure_capture(cv2.VideoCapture(int(did), CAMERA_BACKEND))
                    for _ in range(5):
                        self.caps[did].read()
                
                cap = self.caps[did]
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret:
                        # 1. Handle Recording (Full Res BGR)
                        if self.is_recording:
                            if did not in self.writers:
                                scene = self.record_params['scene']
                                take = self.record_params['take']
                                v_file = f"{scene}_{take}_cam{did}.mp4"
                                h, w = frame.shape[:2]
                                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                                self.writers[did] = cv2.VideoWriter(v_file, fourcc, 30.0, (w, h))
                                print(f"[Preview] Recording Cam {did} to {v_file}")
                            self.writers[did].write(frame)

                        # 2. Handle Calibration (State Driven)
                        if self.is_calibrating and did in self.calib_params['indices']:
                            p = self.calib_params
                            current_count = p['count']
                            # If the master count has advanced, but we haven't saved for THIS camera yet
                            if current_count > 0 and self.calib_saved_count.get(did, -1) < current_count:
                                # Save the frame. Filenames are 0-indexed (img_0000)
                                fname = os.path.join("calibration_images", f"cam{did}", f"img_{current_count-1:04d}.jpg")
                                cv2.imwrite(fname, frame)
                                self.calib_saved_count[did] = current_count
                                # print(f"[Preview] Cam {did} saved img_{current_count-1}")

                        # 3. Create UI Thumbnail (RGB)
                        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        img = Image.fromarray(frame_rgb)
                        img.thumbnail((320, 180))
                    else:
                        cap.release()
                        del self.caps[did]

            elif dtype == 'mobile':
                url = f"{protocol}://127.0.0.1:5000/api/preview/{did}"
                res = self.session.get(url, verify=False, timeout=0.5)
                if res.status_code == 200:
                    img_bytes = io.BytesIO(res.content)
                    img = Image.open(img_bytes)
                    img.thumbnail((320, 180))
        except Exception as e:
            logger.warning("Preview fetch failed for %s: %s", did, e)
            
        return did, img

    def update_loop(self):
        while self.running:
            # READ STATE FROM CACHE (Thread Safe)
            with self.parent.thread_lock:
                devices = list(self.parent.enabled_devices_cache)
                protocol = self.parent.protocol_cache
            
            if not devices:
                time.sleep(0.5)
                continue

            # Update Calibration Timer/Sever Poke
            if self.is_calibrating:
                p = self.calib_params
                # Initial delay handling
                if p['count'] == 0:
                    if time.time() > p['last_time']:
                        p['count'] += 1
                        p['last_time'] = time.time()
                        self.trigger_calib_step(p)
                elif p['count'] < p['num_images'] and time.time() - p['last_time'] > p['delay']:
                        p['count'] += 1
                        p['last_time'] = time.time()
                        self.trigger_calib_step(p)

                if p['count'] >= p['num_images']:
                    selected = p['indices']
                    all_saved = all(self.calib_saved_count.get(did, 0) >= p['num_images'] for did in selected)
                    if all_saved:
                        self.is_calibrating = False

            current_ids = [str(d['id']) for d in devices]
            
            # Remove stale previews
            active_ids = list(self.previews.keys())
            for pid in active_ids:
                if pid not in current_ids:
                    self.after(0, lambda p=pid: self.remove_preview(p))

            # Parallel Fetch
            futures = {self.executor.submit(self.fetch_frame, dev, protocol): dev for dev in devices}
            
            results = []
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())

            # Schedule UI Update on Main Thread
            self.after(0, lambda res=results: self.update_ui(res))

            time.sleep(0.05)

    def trigger_calib_step(self, p):
        print(f"[Preview] Capturing Calibration Set {p['count']}/{p['num_images']}...")
        # Play audible feedback
        if winsound:
            threading.Thread(target=lambda: winsound.Beep(1000, 150)).start()
        
        # Poke Server for Mobile Sync
        try:
            # We need the protocol and url from the parent app
            with self.parent.thread_lock:
                protocol = self.parent.protocol_cache
                
            requests.post(f"{protocol}://127.0.0.1:5000/api/trigger_calibration", json={'count': p['count']-1}, verify=False)
        except requests.RequestException as e:
            logger.warning("Could not trigger mobile calibration capture: %s", e)

    def remove_preview(self, pid):
        if pid in self.previews:
            self.previews[pid].grid_forget()
            self.previews[pid].destroy()
            self.previews.pop(pid, None)
            self.realign_grid()

    def update_ui(self, results):
        if not self.running: return

        for did, img in results:
            if did not in self.previews:
                lbl = ctk.CTkLabel(self.scroll, text=f"Loading {did}...")
                self.previews[did] = lbl
                self.realign_grid()

            if did in self.previews:
                try:
                    if img:
                        # Keep refernece to image to prevent garbage collection
                        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                        self.previews[did].configure(image=ctk_img, text="")
                        self.previews[did]._img_ref = ctk_img 
                    else:
                        self.previews[did].configure(text=f"No Signal ({did})", image=None)
                except Exception as e:
                    logger.warning("Preview UI update failed for %s: %s", did, e)

    def realign_grid(self):
        sorted_ids = sorted(self.previews.keys())
        cols = 2
        for i, did in enumerate(sorted_ids):
            row = i // cols
            col = i % cols
            self.previews[did].grid(row=row, column=col, padx=10, pady=10, sticky="nsew")







class MocapApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Mocap Controller")
        self.geometry("800x850") 
        
        self.server_process = None
        # self.start_server() will be called after UI is ready
        
        # Get Local IP
        self.local_ip = self.get_local_ip()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Initialize OSC
        self.osc_client = MocapOSC()
        
        # Initialize Audio
        self.audio_recorder = None
        
        # Video Subprocesses
        self.video_processes = []

        # Pipeline
        self.pipeline = MocapPipeline()

        # Shared state for background threads
        self.thread_lock = threading.Lock()
        self.enabled_devices_cache = []
        self.protocol_cache = "http"
        
        # Start state sync loop
        self.sync_state()

        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        self.main_frame.grid_columnconfigure(1, weight=1)

        # Scene Name
        self.label_scene = ctk.CTkLabel(self.main_frame, text="Scene Name:")
        self.label_scene.grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.entry_scene = ctk.CTkEntry(self.main_frame)
        self.entry_scene.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        self.entry_scene.insert(0, "Scene_01")

        # Take Number
        self.label_take = ctk.CTkLabel(self.main_frame, text="Take Number:")
        self.label_take.grid(row=1, column=0, padx=10, pady=10, sticky="w")
        self.entry_take = ctk.CTkEntry(self.main_frame)
        self.entry_take.grid(row=1, column=1, padx=10, pady=10, sticky="ew")
        self.entry_take.insert(0, "001")

        # Camera Selection (Scrollable)
        self.label_cams = ctk.CTkLabel(self.main_frame, text="Connected Devices:")
        self.label_cams.grid(row=2, column=0, padx=10, pady=10, sticky="nw")
        
        self.scroll_devices = ctk.CTkScrollableFrame(self.main_frame, height=150)
        self.scroll_devices.grid(row=2, column=1, padx=10, pady=10, sticky="ew")
        
        self.device_checkboxes = {} # id -> checkbox
        self.discovered_devices = [] # list of dicts {id, type, name}
        
        # Refresh Button
        self.btn_refresh = ctk.CTkButton(self.main_frame, text="Refresh Devices", command=self.refresh_devices)
        self.btn_refresh.grid(row=2, column=2, padx=5, pady=10)
 
        
        # Audio Device Selection

        self.label_mic = ctk.CTkLabel(self.main_frame, text="Microphone:")
        self.label_mic.grid(row=3, column=0, padx=10, pady=10, sticky="w")
        self.combo_mic = ctk.CTkComboBox(self.main_frame, values=["Default"])
        self.combo_mic.grid(row=3, column=1, padx=10, pady=10, sticky="ew")
        self.populate_mics()

        # SSL Toggle
        self.check_ssl = ctk.CTkCheckBox(self.main_frame, text="Use SSL (HTTPS)", command=self.restart_server_with_ssl)
        self.check_ssl.grid(row=4, column=1, padx=10, pady=10, sticky="w")
        # Mobile getUserMedia requires HTTPS unless the user enables a browser flag.
        self.check_ssl.select()

        # Server Info
        self.label_ip = ctk.CTkLabel(self.main_frame, text="Connect Mobile to:", font=("Arial", 14))
        self.label_ip.grid(row=5, column=0, columnspan=2, padx=10, pady=(10, 0))
        
        self.entry_url = ctk.CTkEntry(self.main_frame, font=("Arial", 16, "bold"), width=300)
        self.entry_url.grid(row=6, column=0, columnspan=2, padx=10, pady=5)
        self.update_url_display()

        # Troubleshooting Button
        self.btn_trouble = ctk.CTkButton(self.main_frame, text="Fix Camera Permission", command=self.show_troubleshooting, fg_color="orange", text_color="black")
        self.btn_trouble.grid(row=5, column=2, padx=5, pady=5)
        
        # QR Code Label (Initial placeholder)
        self.label_qr = ctk.CTkLabel(self.main_frame, text="QR Loading...")
        self.label_qr.grid(row=6, column=2, padx=10, pady=10)


        # Buttons Frame
        self.btn_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.btn_frame.grid(row=9, column=0, columnspan=2, padx=10, pady=20, sticky="ew")

        self.btn_frame.grid_columnconfigure(0, weight=1)
        self.btn_frame.grid_columnconfigure(1, weight=1)
        self.btn_frame.grid_columnconfigure(2, weight=1)
        self.btn_frame.grid_columnconfigure(3, weight=1)

        # Calibrate Button
        self.btn_calibrate = ctk.CTkButton(self.btn_frame, text="CALIBRATE", command=self.run_calibration_thread, fg_color="blue")
        self.btn_calibrate.grid(row=0, column=0, padx=5, sticky="ew")

        # Sync Blip Button
        self.btn_blip = ctk.CTkButton(self.btn_frame, text="SYNC BLIP", command=self.play_sync_blip, fg_color="purple")
        self.btn_blip.grid(row=0, column=1, padx=5, sticky="ew")

        # Record / Stop Buttons
        self.btn_record = ctk.CTkButton(self.btn_frame, text="RECORD", command=self.start_recording, fg_color="red")
        self.btn_record.grid(row=0, column=2, padx=5, sticky="ew")

        self.btn_stop = ctk.CTkButton(self.btn_frame, text="STOP", command=self.stop_recording, state="disabled")
        self.btn_stop.grid(row=0, column=3, padx=5, sticky="ew")

        self.label_status = ctk.CTkLabel(self.main_frame, text="Ready")
        self.label_status.grid(row=7, column=0, columnspan=2, padx=10, pady=10)

        # Unreal Import Path
        self.label_unreal = ctk.CTkLabel(self.main_frame, text="Unreal Watch Path:")
        self.label_unreal.grid(row=8, column=0, padx=10, pady=5, sticky="w")
        self.entry_unreal = ctk.CTkEntry(self.main_frame, placeholder_text="C:/Project/MocapImports")
        self.entry_unreal.grid(row=8, column=1, padx=10, pady=5, sticky="ew")
        
        # Pre-fill from config
        unreal_cfg = config.get("Unreal", {})
        default_path = unreal_cfg.get("watch_path", "")
        if default_path:
            self.entry_unreal.insert(0, default_path)

        # Exit Button (Bottom Row)
        self.btn_exit = ctk.CTkButton(self.main_frame, text="EXIT APP", command=self.exit_app, fg_color="#444444", hover_color="#222222")
        self.btn_exit.grid(row=11, column=0, columnspan=3, padx=10, pady=20, sticky="ew")

        self.is_recording = False
        
        # Now that UI is ready, start components
        self.start_server()
        self.update_url_display()
        self.preview_window = LivePreviewWindow(self)
        self.refresh_devices()
        self.check_calibration()


        
    def get_local_ip(self):
        try:
            # Connect to an external server to determine the route
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def populate_mics(self):
        try:
            devices = AudioRecorder.list_devices()
            if devices is None:
                 logger.warning("Audio device query returned no devices.")
            # Re-query properly
            import sounddevice as sd
            devs = sd.query_devices()
            mic_names = []
            self.mic_indices = {} # Name -> Index
            
            for i, dev in enumerate(devs):
                if dev['max_input_channels'] > 0:
                    name = f"{i}: {dev['name']}"
                    mic_names.append(name)
                    self.mic_indices[name] = i
            
            if mic_names:
                self.combo_mic.configure(values=mic_names)
                self.combo_mic.set(mic_names[0])
        except Exception as e:
            print(f"Error listing mics: {e}")
    
    def get_enabled_devices(self):
        enabled = []
        for dev in self.discovered_devices:
            did = str(dev['id'])
            # .get() is NOT thread safe, must be called from main thread
            if did in self.device_checkboxes and self.device_checkboxes[did].get() == 1:
                enabled.append(dev)
        return enabled

    def sync_state(self):
        """Periodically sync UI state for background threads."""
        try:
            devices = self.get_enabled_devices()
            protocol = "https" if self.check_ssl.get() else "http"
            with self.thread_lock:
                self.enabled_devices_cache = devices
                self.protocol_cache = protocol
        except Exception as e:
            logger.warning("Could not sync GUI state for background threads: %s", e)
        self.after(500, self.sync_state)

    def refresh_devices(self):
        # Clear existing checkboxes
        for cb in self.device_checkboxes.values():
            cb.destroy()
        self.device_checkboxes = {}
        self.discovered_devices = []
        
        # 1. Discover Local Cams
        # Brute force 0-5
        for i in range(5):
            try:
                cap = configure_capture(cv2.VideoCapture(i, CAMERA_BACKEND))
                if cap.isOpened():
                    self.discovered_devices.append({'id': i, 'type': 'local', 'name': f"Local Cam {i}"})
                    cap.release()
            except Exception as e:
                logger.warning("Camera discovery failed for index %s: %s", i, e)
                
        # 2. Discover Remote Cams
        try:
            protocol = "https" if self.check_ssl.get() else "http"
            url = f"{protocol}://127.0.0.1:5000/api/devices"
            res = requests.get(url, verify=False, timeout=1)
            if res.status_code == 200:
                mobiles = res.json()
                for m in mobiles:
                    dev_id = m.get('id') or m.get('sid')
                    self.discovered_devices.append({'id': dev_id, 'type': 'mobile', 'name': f"Mobile {m['address']}"})
        except Exception as e:
            print(f"Error fetching mobile devices: {e}")
            
        # Repopulate
        for dev in self.discovered_devices:
            did = str(dev['id'])
            name = dev['name']
            cb = ctk.CTkCheckBox(self.scroll_devices, text=name)
            cb.pack(anchor="w", padx=5, pady=2)
            cb.select() # Default enable
            self.device_checkboxes[did] = cb

    def update_url_display(self):
        protocol = "https" if self.check_ssl.get() else "http"
        url = f"{protocol}://{self.local_ip}:5000"
        self.entry_url.delete(0, "end")
        self.entry_url.insert(0, url)
        
        # Update QR if it exists
        if hasattr(self, 'label_qr'):
            try:
                qr = qrcode.QRCode(box_size=10, border=2)
                qr.add_data(url)
                qr.make(fit=True)
                qr_img = qr.make_image(fill_color="black", back_color="white").get_image()
                self.qr_ctk = ctk.CTkImage(light_image=qr_img, dark_image=qr_img, size=(100, 100))
                self.label_qr.configure(image=self.qr_ctk)
            except Exception as e:
                logger.warning("QR code update failed: %s", e)

    def restart_server_with_ssl(self):
        if self.server_process:
            self.server_process.terminate()
            self.server_process.wait()
        self.start_server()
        self.update_url_display()
        self.refresh_devices()

    def open_preview(self):
        self.preview_window = LivePreviewWindow(self)

    def show_troubleshooting(self):
        protocol = "https" if self.check_ssl.get() else "http"
        url = f"{protocol}://{self.local_ip}:5000"
        
        msg = f"If the camera is not showing up or gives a 'Permission Denied' error:\n\n"
        msg += "1. ENSURE you are on the same Wi-Fi.\n"
        
        if self.check_ssl.get():
            msg += "2. Click 'Advanced' -> 'Proceed' on the chrome warning.\n"
            msg += "3. RESET PERMISSIONS: Tap the 'Lock' or 'Warning' icon in the address bar -> 'Permissions' -> 'Reset Permission'.\n"
            msg += "4. If it still fails, uncheck 'Use SSL' and try the Chrome Flag method below.\n"
        else:
            msg += "2. Chrome BLOCKS cameras on non-HTTPS sites by default.\n"
            msg += "3. To FIX this, open Chrome on your phone and go to:\n"
            msg += "   chrome://flags/#unsafely-treat-insecure-origin-as-secure\n"
            msg += f"4. ENTER this URL: {url}\n"
            msg += "5. SET to 'Enabled' and Relaunch Chrome.\n"
            msg += "6. RESET PERMISSIONS: Tap the 'Warning' icon in the address bar -> 'Permissions' -> 'Reset Permission'.\n"
            msg += "7. Now it will treat this site as 'SECURE' and allow the camera."
        
        msg += "\n\nNOTE: The app will now try to request 'Video Only' if the combined request fails."
        
        # show a custom window with a copyable text area
        win = ctk.CTkToplevel(self)
        win.title("Mobile Camera Fix")
        win.geometry("500x400")
        
        txt = ctk.CTkTextbox(win, width=480, height=350)
        txt.pack(padx=10, pady=10)
        txt.insert("0.0", msg)
        txt.configure(state="disabled")

    def start_server(self):
        print("[MocapApp] Launching Flask Server...")
        try:
            cmd = [sys.executable, "src/server/app.py"]
            if not self.check_ssl.get():
                cmd.append("--no-ssl")
            self.server_process = subprocess.Popen(cmd)
        except Exception as e:
            print(f"[MocapApp] Failed to start server: {e}")
            msgbox.showerror("Error", f"Failed to start server subprocess:\n{e}")

        
    def trigger_server_start(self, scene, take, target_sids=None):
        try:
            protocol = "https" if self.check_ssl.get() else "http"
            url = f"{protocol}://127.0.0.1:5000/api/start"
            requests.post(url, json={'scene': scene, 'take': take, 'devices': target_sids}, verify=False)
        except Exception as e:
            print(f"[MocapApp] Error triggering server start: {e}")


    def trigger_server_stop(self):
        try:
            protocol = "https" if self.check_ssl.get() else "http"
            url = f"{protocol}://127.0.0.1:5000/api/stop"
            requests.post(url, json={}, verify=False)
        except Exception as e:
            print(f"[MocapApp] Error triggering server stop: {e}")

    def check_calibration(self):
        # Check for calibration.npz according to config
        calib_path = config.get("Calibration", {}).get("save_path", "calibration.npz")
        self.calibrated_ids = []
        
        if os.path.exists(calib_path):
            try:
                import numpy as np
                data = np.load(calib_path)
                calibrated_ids = []
                for key in data.files:
                    if key.startswith("mtx_"):
                        dev_id = key.replace("mtx_", "")
                        required = [f"dist_{dev_id}", f"rvec_{dev_id}", f"tvec_{dev_id}"]
                        if all(req in data.files for req in required):
                            calibrated_ids.append(dev_id)
                
                calibrated_ids.sort()
                dev_str = ", ".join(calibrated_ids)
                self.calibrated_ids = calibrated_ids

                if len(calibrated_ids) >= 2:
                    self.btn_record.configure(state="normal")
                    self.label_status.configure(text=f"Ready. Calibrated: {dev_str}", text_color="green")
                else:
                    self.btn_record.configure(state="disabled")
                    self.label_status.configure(
                        text="Calibration incomplete: need 2+ cameras with board pose. Re-run CALIBRATE.",
                        text_color="orange",
                    )
            except Exception as e:
                print(f"Error loading calibration: {e}")
                self.btn_record.configure(state="disabled")
                self.label_status.configure(
                    text="Calibration file cannot be read. Re-run CALIBRATE to regenerate it.",
                    text_color="red",
                )
        else:
            self.btn_record.configure(state="disabled")
            self.label_status.configure(text="Calibration Missing! Run Calibration.", text_color="orange")


    def run_calibration_thread(self):
        threading.Thread(target=self.run_calibration).start()

    def run_calibration(self):
        self.btn_calibrate.configure(state="disabled")
        self.btn_record.configure(state="disabled")
        self.label_status.configure(text="Calibrating... Follow instructions.")
        
        try:
            # 0. Ensure Preview is open
            if not self.preview_window or not self.preview_window.winfo_exists():
                self.open_preview()
                time.sleep(1.0) # Give it a second to open caps

            # 1. Start Capture Mode in Preview Window
            self.label_status.configure(text="STEP 1: PLACE BOARD FLAT ON FLOOR for 1st click", text_color="orange")
            
            enabled_devs = self.get_enabled_devices()
            local_indices = [d['id'] for d in enabled_devs if d['type'] == 'local']
            if len(enabled_devs) < 2:
                self.label_status.configure(
                    text="Calibration needs at least two cameras selected.",
                    text_color="orange",
                )
                return

            if os.path.exists("calibration_images"):
                shutil.rmtree("calibration_images")
            
            num_imgs = 20
            delay = 3.0
            self.preview_window.start_calibration(local_indices, num_images=num_imgs, delay=delay, no_ssl=not self.check_ssl.get())
            
            # Wait for capture to finish (blocking the calibrate thread)
            # Initial 5s + (imgs * delay)
            total_wait = 5.0 + (num_imgs * delay) + 2.0
            time.sleep(total_wait)
            
            # 2. Process
            self.label_status.configure(text="Processing Calibration...")
            cmd_process = [sys.executable, "src/calibrate_cli.py", "--process"]
            result = subprocess.run(cmd_process, check=True, capture_output=True, text=True)
            if result.stdout:
                print(result.stdout)
            
            self.label_status.configure(text="Calibration Complete!")
            self.after(0, self.check_calibration)
            
        except subprocess.CalledProcessError as e:
            details = (e.stdout or "") + "\n" + (e.stderr or "")
            print(f"Calibration Error: {details.strip()}")
            self.label_status.configure(
                text="Calibration failed. Make sure the board is visible in every selected camera, especially the first image.",
                text_color="red",
            )
            
        except Exception as e:
            print(f"Error: {e}")
            self.label_status.configure(
                text="Calibration failed because the app could not capture or process the board images.",
                text_color="red",
            )
            
        finally:
             self.btn_calibrate.configure(state="normal")

    def start_recording(self):
        enabled_devs = self.get_enabled_devices()
        expected_calib_ids = []
        for dev in enabled_devs:
            if dev["type"] == "local":
                expected_calib_ids.append(f"cam{dev['id']}")
            elif dev["type"] == "mobile":
                expected_calib_ids.append(f"mobile_{dev['id']}")

        if not (2 <= len(enabled_devs) <= 6):
            self.label_status.configure(text="Select 2-6 cameras before recording.", text_color="orange")
            msgbox.showwarning("Recording Blocked", "Select between 2 and 6 cameras before recording.")
            return

        self.check_calibration()
        available_calibrated = [cam_id for cam_id in expected_calib_ids if cam_id in self.calibrated_ids]
        missing_calib = [cam_id for cam_id in expected_calib_ids if cam_id not in self.calibrated_ids]
        if len(available_calibrated) < 2 or missing_calib:
            missing = ", ".join(missing_calib) if missing_calib else "at least two selected cameras"
            self.label_status.configure(text=f"Recording blocked: calibration missing for {missing}.", text_color="orange")
            msgbox.showwarning(
                "Recording Blocked",
                f"Calibration is missing or incomplete for {missing}. Re-run CALIBRATE before recording.",
            )
            return

        ok, message = self.osc_client.handshake()
        if not ok:
            self.label_status.configure(text="Recording blocked: OSC pre-flight failed.", text_color="red")
            msgbox.showerror("OSC Pre-flight Failed", message)
            return

        self.is_recording = True
        self.btn_record.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.label_status.configure(text="Recording...")
    
        # 1. Warm up Preview (Master Controller)
        if not self.preview_window or not self.preview_window.winfo_exists():
            self.open_preview()
            time.sleep(1.0) 

        scene = self.entry_scene.get()
        take = self.entry_take.get()
        print(f"Starting recording: Scene={scene}, Take={take}")
        
        # 2. Start Audio
        audio_filename = f"{scene}_{take}_audio.wav"
        mic_name = self.combo_mic.get()
        mic_idx = self.mic_indices.get(mic_name, None)
        self.audio_recorder = AudioRecorder(filename=audio_filename, device=mic_idx)
        self.audio_recorder.start()

        # 3. Trigger Mobile Nodes
        mobile_sids = [d['id'] for d in enabled_devs if d['type'] == 'mobile']
        self.trigger_server_start(scene, take, mobile_sids)

        # 4. Start Local Video (via Master Controller)
        self.preview_window.start_recording(scene, take)

        # 5. Trigger OSC (Unreal/Remote)
        self.osc_client.start_recording(scene, take)

    def stop_recording(self):
        self.is_recording = False
        self.btn_record.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        
        # 1. Capture metadata
        scene = self.entry_scene.get()
        take = self.entry_take.get()
        print(f"Stopping recording: {scene}_{take}...")
        self.label_status.configure(text="Processing...")
        
        # 2. Stop Master Controller (Local Video)
        if self.preview_window:
            self.preview_window.stop_recording()
            
        # 3. Stop Audio
        if self.audio_recorder:
            self.audio_recorder.stop()
            spike_time = AudioRecorder.find_sync_spike(self.audio_recorder.filename)
            print(f"Detected Sync Spike: {spike_time}")
            
        # 4. Stop Remote Triggers (OSC/Mobile)
        self.osc_client.stop_recording()
        self.trigger_server_stop()

        # 5. Build cam index list for pipeline
        enabled_devs = self.get_enabled_devices()
        cam_indices = [d['id'] for d in enabled_devs if d['type'] == 'local']

        # 6. Auto-increment take number
        try:
            current_take = int(take)
            self.entry_take.delete(0, "end")
            self.entry_take.insert(0, f"{current_take + 1:03d}")
        except ValueError as e:
            logger.warning("Take number is not numeric; auto-increment skipped: %s", e)

        # 7. Start Processing Pipeline (Async)
        threading.Thread(target=self.run_processing, args=(scene, take, cam_indices)).start()

    def play_sync_blip(self):
        """Play a high-frequency blip for audio synchronization."""
        if winsound:
            # 1000Hz for 200ms
            threading.Thread(target=lambda: winsound.Beep(1000, 200)).start()
            print("Sync Blip Played (1000Hz)")
        else:
            print("winsound not available. Use a manual clap.")

    def run_processing(self, scene, take, cam_indices):
        self.label_status.configure(text=f"Processing {scene}_{take}...")
        
        try:
            success = self.pipeline.process_session(scene, take, cam_indices)
            if success:
                self.label_status.configure(text=f"Completed {scene}_{take}")
                print(f"Successfully processed {scene}_{take}")
                
                # OPTIONAL: Copy to Unreal
                unreal_path = self.entry_unreal.get().strip()
                if unreal_path:
                    try:
                        os.makedirs(unreal_path, exist_ok=True)
                        csv_src = os.path.join("MocapExports", f"{scene}_{take}.csv")
                        csv_dest = os.path.join(unreal_path, f"{scene}_{take}.csv")
                        if os.path.exists(csv_src):
                            shutil.copy2(csv_src, csv_dest)
                            print(f"Auto-imported to Unreal: {csv_dest}")
                    except Exception as e:
                        print(f"Failed to copy to Unreal: {e}")
            else:
                self.label_status.configure(
                    text="Processing failed. Raw files were kept; check calibration, OpenPose, and sync clap.",
                    text_color="red",
                )
                print("Processing Failed")
        except Exception as e:
            print(f"Critical Pipeline Error: {e}")
            self.label_status.configure(
                text="Processing failed unexpectedly. Raw files were kept for inspection.",
                text_color="red",
            )

        # Auto-increment take number (moved from stop_recording to be safe, 
        # or keep it there for UI responsiveness. Keeping it there is fine.)






    def exit_app(self):
        """Safely stop everything and close the app."""
        if self.is_recording:
            self.stop_recording()
        self.on_closing()

    def on_closing(self):
        print("[MocapApp] Shutting down...")
        
        # 1. Stop Server
        if self.server_process:
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=2)
            except Exception as e:
                logger.warning("Server shutdown did not finish cleanly: %s", e)
        
        # 2. Stop Preview Window
        if hasattr(self, 'preview_window') and self.preview_window:
            self.preview_window.running = False
            try:
                self.preview_window.session.close()
                self.preview_window.executor.shutdown(wait=False, cancel_futures=True)
                if self.preview_window.update_thread.is_alive():
                    self.preview_window.update_thread.join(timeout=1.0)
                self.preview_window.destroy()
            except Exception as e:
                logger.warning("Preview window cleanup failed: %s", e)
        
        # 3. Force stop any remaining local video processes
        for proc, _ in self.video_processes:
            try:
                proc.terminate()
            except Exception as e:
                logger.warning("Video process cleanup failed: %s", e)

        # 4. Final Cleanup
        print("[MocapApp] Application Closed.")
        self.destroy()
        sys.exit(0)


if __name__ == "__main__":
    app = MocapApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()

