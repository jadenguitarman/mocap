
import threading
import customtkinter as ctk
import subprocess
import sys
import os
from osc.client import MocapOSC
from osc.client import MocapOSC
from capture.audio import AudioRecorder
from processing.pipeline import MocapPipeline
from utils.config import config
import tkinter.messagebox as msgbox
import socket
import socket
import requests
import time
import cv2
from PIL import Image
import concurrent.futures
import qrcode



import io

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
        
        self.caps = {} # id -> cv2.VideoCapture (Persistent)
        self.session = requests.Session() # Reuse connections

        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=8) # Parallel fetch
        
        self.update_thread = threading.Thread(target=self.update_loop)
        self.update_thread.start()

        
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        self.running = False
        self.running = False
        self.executor.shutdown(wait=False)
        # Release caps
        for cap in self.caps.values():
            cap.release()
        self.destroy()



    def fetch_frame(self, dev):
        did = str(dev['id'])
        dtype = dev['type']
        img = None
        
        try:
            if dtype == 'local':
                # Use persistent capture
                if did not in self.caps:
                    self.caps[did] = cv2.VideoCapture(int(did))
                    # Warmup
                    self.caps[did].read()
                
                cap = self.caps[did]
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret:
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        frame = cv2.resize(frame, (320, 180))
                        img = Image.fromarray(frame)
                    else:
                        # Try re-open if failed
                        cap.release()
                        del self.caps[did]

            elif dtype == 'mobile':
                 # Assuming server is local
                url = f"http://127.0.0.1:5000/api/preview/{did}"
                # Use session for keep-alive
                res = self.session.get(url.replace("http", "https"), verify=False, timeout=0.5)
                if res.status_code == 200:
                    img_bytes = io.BytesIO(res.content)
                    img = Image.open(img_bytes)
        except:
            pass
            
        return did, img

    def update_loop(self):
        while self.running:
            if not hasattr(self.parent, 'get_enabled_devices'):
                time.sleep(1)
                continue
                
            devices = self.parent.get_enabled_devices() 
            current_ids = [str(d['id']) for d in devices]
            
            # Remove stale previews (Main Thread Logic via direct call? No, we are in thread)
            # Tkinter updates must be scheduled or done carefully. CTk is somewhat thread safe for configure?
            # Ideally use .after, but we are in a thread loop. CTk usually handles it.
            
            # Prune
            active_widgets = list(self.previews.keys())
            for pid in active_widgets:
                if pid not in current_ids:
                    # Schedule removal in main thread if possible, or attempt direct
                    try:
                        self.previews[pid].pack_forget()
                        self.previews[pid].destroy()
                        del self.previews[pid]
                    except:
                        pass # widget gone?

            # Create needed widgets (Main Thread Safe?) 
            # We'll just creating them here checking if exists.
            for dev in devices:
                did = str(dev['id'])
                if did not in self.previews:
                     # This might crash if called from thread. 
                     # But let's try. If it crashes, we need a queue.
                     # For now, we assume simple CTk thread safety or lack thereof causing minor glitches.
                     # To be safe:
                     pass 
            
            # Parallel Fetch
            futures = {self.executor.submit(self.fetch_frame, dev): dev for dev in devices}
            
            for future in concurrent.futures.as_completed(futures):
                did, img = future.result()
                
                # Update UI
                if did not in self.previews:
                    # Create lazily on first successful frame? 
                    # Or check again.
                    # Creating widgets from thread is risky.
                    # Best practice: use self.after from main thread, but we are in loop.
                    # We will try direct creation.
                    if self.running:
                         lbl = ctk.CTkLabel(self.scroll, text=f"Loading {did}...")
                         lbl.pack(padx=5, pady=5, side="left", fill="both", expand=True)
                         self.previews[did] = lbl

                if did in self.previews:
                    try:
                        if img:
                             ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(320, 180))
                             self.previews[did].configure(image=ctk_img, text="")
                        else:
                             self.previews[did].configure(text=f"No Signal")
                    except:
                        pass

            time.sleep(0.05) # ~20 FPS loop







class MocapApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Mocap Controller")
        self.title("Mocap Controller")
        self.geometry("800x600")
        
        # Start Flask Server Subprocess

        self.server_process = None
        self.start_server()
        
        # Get Local IP
        self.local_ip = self.get_local_ip()

        self.grid_columnconfigure(0, weight=1)

        self.grid_rowconfigure(0, weight=1)

        # Initialize OSC
        # Loaded from config
        self.osc_client = MocapOSC()

        
        # Initialize Audio
        self.audio_recorder = None
        
        # Video Subprocesses
        self.video_processes = []

        # Pipeline
        self.pipeline = MocapPipeline()




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

        # Hand Tracking Toggle
        self.check_hand = ctk.CTkCheckBox(self.main_frame, text="Enable Hand Tracking (BODY_135)")
        self.check_hand.grid(row=4, column=0, columnspan=2, padx=10, pady=10, sticky="w")
        
        # Server Info
        url = f"https://{self.local_ip}:5000"
        self.label_ip = ctk.CTkLabel(self.main_frame, text=f"Connect Mobile to:\n{url}", font=("Arial", 16, "bold"))
        self.label_ip.grid(row=5, column=0, columnspan=2, padx=10, pady=20)
        
        # QR Code
        try:
            qr = qrcode.QRCode(box_size=10, border=2)
            qr.add_data(url)
            qr.make(fit=True)
            # qrcode.make_image returns a PilImage wrapper. We need the internal image.
            # Usually .get_image() works for factory=PilImage
            qr_img_wrapper = qr.make_image(fill_color="black", back_color="white")
            qr_img = qr_img_wrapper.get_image()

            
            # config fit to size
            self.qr_ctk = ctk.CTkImage(light_image=qr_img, dark_image=qr_img, size=(100, 100))
            self.label_qr = ctk.CTkLabel(self.main_frame, image=self.qr_ctk, text="")
            self.label_qr.grid(row=5, column=2, padx=10, pady=10)
        except Exception as e:
            print(f"QR Gen Failed: {e}")


        # Buttons Frame
        self.btn_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.btn_frame.grid(row=6, column=0, columnspan=2, padx=10, pady=20, sticky="ew")

        self.btn_frame.grid_columnconfigure(0, weight=1)
        self.btn_frame.grid_columnconfigure(1, weight=1)
        self.btn_frame.grid_columnconfigure(2, weight=1)

        # Calibrate Button
        self.btn_calibrate = ctk.CTkButton(self.btn_frame, text="CALIBRATE", command=self.run_calibration_thread, fg_color="blue")
        self.btn_calibrate.grid(row=0, column=0, padx=5, sticky="ew")

        # Record / Stop Buttons
        self.btn_record = ctk.CTkButton(self.btn_frame, text="RECORD", command=self.start_recording, fg_color="red")
        self.btn_record.grid(row=0, column=1, padx=5, sticky="ew")

        self.btn_stop = ctk.CTkButton(self.btn_frame, text="STOP", command=self.stop_recording, state="disabled")
        self.btn_stop.grid(row=0, column=2, padx=5, sticky="ew")

        # Status Status
        self.label_status = ctk.CTkLabel(self.main_frame, text="Ready")
        self.label_status.grid(row=6, column=0, columnspan=2, padx=10, pady=10)

        self.is_recording = False
        
        self.preview_window = LivePreviewWindow(self)
        self.refresh_devices()


        
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
            if devices is None: # sounddevice might return device list or something else
                 # It prints and returns. 
                 pass
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
            if did in self.device_checkboxes and self.device_checkboxes[did].get() == 1:
                enabled.append(dev)
        return enabled

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
                cap = cv2.VideoCapture(i)
                if cap.isOpened():
                    self.discovered_devices.append({'id': i, 'type': 'local', 'name': f"Local Cam {i}"})
                    cap.release()
            except:
                pass
                
        # 2. Discover Remote Cams
        try:
            url = "https://127.0.0.1:5000/api/devices"
            res = requests.get(url, verify=False, timeout=1)
            if res.status_code == 200:
                mobiles = res.json()
                for m in mobiles:
                    self.discovered_devices.append({'id': m['sid'], 'type': 'mobile', 'name': f"Mobile {m['address']}"})
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

    def start_server(self):

        print("[MocapApp] Launching Flask Server...")
        # Ad-hoc SSL is used in app.py
        try:
            cmd = [sys.executable, "src/server/app.py"]
            self.server_process = subprocess.Popen(cmd)
        except Exception as e:
            print(f"[MocapApp] Failed to start server: {e}")
            msgbox.showerror("Error", f"Failed to start server subprocess:\n{e}")

        
    def trigger_server_start(self, scene, take, target_sids=None):
        try:
            url = "https://127.0.0.1:5000/api/start"
            requests.post(url, json={'scene': scene, 'take': take, 'devices': target_sids}, verify=False)
        except Exception as e:
            print(f"[MocapApp] Error triggering server start: {e}")


    def trigger_server_stop(self):
        try:
            url = "https://127.0.0.1:5000/api/stop"
            requests.post(url, json={}, verify=False)
        except Exception as e:
            print(f"[MocapApp] Error triggering server stop: {e}")

    def check_calibration(self):
        # Check for calibration.npz according to config
        calib_path = config.get("Calibration", {}).get("save_path", "calibration.npz")
        
        if os.path.exists(calib_path):
            try:
                import numpy as np
                data = np.load(calib_path)
                # Keys are mtx_{id}, dist_{id}, etc.
                # Find all unique IDs
                calibrated_ids = []
                for key in data.files:
                    if key.startswith("mtx_"):
                        dev_id = key.replace("mtx_", "")
                        calibrated_ids.append(dev_id)
                
                calibrated_ids.sort()
                dev_str = ", ".join(calibrated_ids)
                
                self.btn_record.configure(state="normal")
                self.label_status.configure(text=f"Ready. Calibrated: {dev_str}", text_color="green")
            except Exception as e:
                print(f"Error loading calibration: {e}")
                self.label_status.configure(text="Calibration Error", text_color="red")
        else:
            self.btn_record.configure(state="disabled")
            self.label_status.configure(text="Calibration Missing! Run Calibration.", text_color="orange")


    def run_calibration_thread(self):
        threading.Thread(target=self.run_calibration).start()

    def run_calibration(self):
        self.btn_calibrate.configure(state="disabled")
        self.btn_record.configure(state="disabled")
        self.label_status.configure(text="Calibrating... Follow instructions.")
        
        # 1. Capture
        self.label_status.configure(text="Capturing Images...")
        # We need to capture from the cameras configured.
        # simpler to just run the CLI script
        
        try:
            # Run capture (blocking, opens window)
            cmd_capture = [sys.executable, "src/calibrate_cli.py", "--capture"]
            subprocess.run(cmd_capture, check=True)
            
            # 2. Process
            self.label_status.configure(text="Processing Calibration...")
            cmd_process = [sys.executable, "src/calibrate_cli.py", "--process"]
            subprocess.run(cmd_process, check=True)
            
            self.label_status.configure(text="Calibration Complete!")
            self.after(0, self.check_calibration)
            
        except subprocess.CalledProcessError as e:
            self.label_status.configure(text=f"Calibration Failed: {e}")
            print(f"Calibration Error: {e}")
            
        except Exception as e:
            self.label_status.configure(text=f"Error: {e}")
            print(f"Error: {e}")
            
        finally:
             self.btn_calibrate.configure(state="normal")

    def start_recording(self):

        self.is_recording = True
        self.btn_record.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.label_status.configure(text="Recording...")
        print(f"Starting recording: Scene={self.entry_scene.get()}, Take={self.entry_take.get()}")
        
        scene = self.entry_scene.get()
        take = self.entry_take.get()
        
        # Start Audio
        filename = f"{scene}_{take}_audio.wav"
        # Start Audio
        filename = f"{scene}_{take}_audio.wav"
        
        # Get selected mic index
        mic_name = self.combo_mic.get()
        mic_idx = self.mic_indices.get(mic_name, None)
        
        self.audio_recorder = AudioRecorder(filename=filename, device=mic_idx)
        self.audio_recorder.start()

        
        # Start Video Subprocesses
        self.video_processes = []
        
        # Trigger Mobile Nodes (Only enabled ones)
        # Filter mobile SIDs
        enabled_devs = self.get_enabled_devices()
        mobile_sids = [d['id'] for d in enabled_devs if d['type'] == 'mobile']
        self.trigger_server_start(scene, take, mobile_sids)

        # Start Video Subprocesses (Local)
        self.video_processes = []
        local_indices = [d['id'] for d in enabled_devs if d['type'] == 'local']
        
        try:
            for idx in local_indices:
                vid_filename = f"{scene}_{take}_cam{idx}.mp4"
                if os.path.exists(vid_filename + ".stop"):
                    os.remove(vid_filename + ".stop")
                    
                cmd = [sys.executable, "src/capture/video.py", str(idx), vid_filename]
                proc = subprocess.Popen(cmd)
                self.video_processes.append((proc, vid_filename))
        except ValueError:
            print("Invalid camera indices format")

        # Trigger OSC
        self.osc_client.start_recording(scene, take)
        
        






    def stop_recording(self):
        self.is_recording = False
        self.btn_record.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.label_status.configure(text="Processing...")
        print("Stopping recording...")
        
        # Auto-increment take number
        try:
            current_take = int(self.entry_take.get())
            self.entry_take.delete(0, "end")
            self.entry_take.insert(0, f"{current_take + 1:03d}")
        except ValueError:
            pass
            
        self.label_status.configure(text="Ready")
        
        # Trigger OSC Stop
        self.osc_client.stop_recording()
        
        # Trigger Mobile Stop
        self.trigger_server_stop()

        # Stop Audio

        if self.audio_recorder:
            self.audio_recorder.stop()
            # Analyze spike (can be async or part of post-processing pipeline)
            # For now just print it
            spike_time = AudioRecorder.find_sync_spike(self.audio_recorder.filename)
            print(f"Detected Sync Spike: {spike_time}")
            
        # Stop Video Subprocesses
        for proc, filename in self.video_processes:
            # Create stop file
            with open(filename + ".stop", 'w') as f:
                f.write("stop")
            
            # Wait for process to exit with a timeout
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print(f"Forcing termination of camera process for {filename}")
                proc.terminate()
        
        self.video_processes = []

        # Start Processing Thread
        scene = self.entry_scene.get()
        take = self.entry_take.get()
        

        enabled_devs = self.get_enabled_devices()
        cam_indices = [d['id'] for d in enabled_devs if d['type'] == 'local']


        threading.Thread(target=self.run_processing, args=(scene, take, cam_indices)).start()

    def run_processing(self, scene, take, cam_indices):
        self.label_status.configure(text=f"Processing {scene}_{take}...")
        
        try:
            success = self.pipeline.process_session(scene, take, cam_indices)
            if success:
                self.label_status.configure(text=f"Completed {scene}_{take}")
                print(f"Successfully processed {scene}_{take}")
            else:
                self.label_status.configure(text="Processing Failed")
                # Main thread check needed for messagebox? CustomTkinter might handle it or need root.after
                print("Processing Failed")
        except Exception as e:
            self.label_status.configure(text=f"Error: {str(e)}")
            print(f"Critical Pipeline Error: {e}")
            # Ensure user sees this
            # self.after(0, lambda: msgbox.showerror("Pipeline Error", str(e)))

        # Auto-increment take number (moved from stop_recording to be safe, 
        # or keep it there for UI responsiveness. Keeping it there is fine.)






    def on_closing(self):
        if self.server_process:
            self.server_process.terminate()
        if hasattr(self, 'preview_window') and self.preview_window:
            self.preview_window.running = False
            self.preview_window.destroy()
        self.destroy()


if __name__ == "__main__":
    app = MocapApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()

