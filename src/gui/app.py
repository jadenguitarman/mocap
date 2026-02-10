
import threading
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
import requests
import time





class MocapApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Mocap Controller")
        self.geometry("600x450")
        
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

        # Camera Indices
        self.label_cams = ctk.CTkLabel(self.main_frame, text="Camera Indices (comma-separated):")
        self.label_cams.grid(row=2, column=0, padx=10, pady=10, sticky="w")
        self.entry_cams = ctk.CTkEntry(self.main_frame)
        self.entry_cams.grid(row=2, column=1, padx=10, pady=10, sticky="ew")
        
        # Load default cams from config
        default_cams = config.get("Camera", {}).get("indices", [0, 1])
        default_cams_str = ", ".join(map(str, default_cams))
        self.entry_cams.insert(0, default_cams_str) 


        # Hand Tracking Toggle
        self.check_hand = ctk.CTkCheckBox(self.main_frame, text="Enable Hand Tracking (BODY_135)")
        self.check_hand.grid(row=3, column=0, columnspan=2, padx=10, pady=10, sticky="w")
        
        # Server Info
        self.label_ip = ctk.CTkLabel(self.main_frame, text=f"Connect Mobile to: https://{self.local_ip}:5000", font=("Arial", 16, "bold"))
        self.label_ip.grid(row=4, column=0, columnspan=2, padx=10, pady=20)

        # Record / Stop Buttons
        self.btn_record = ctk.CTkButton(self.main_frame, text="RECORD", command=self.start_recording, fg_color="red")
        self.btn_record.grid(row=5, column=0, padx=10, pady=20, sticky="ew")

        self.btn_stop = ctk.CTkButton(self.main_frame, text="STOP", command=self.stop_recording, state="disabled")
        self.btn_stop.grid(row=5, column=1, padx=10, pady=20, sticky="ew")

        # Status Status
        self.label_status = ctk.CTkLabel(self.main_frame, text="Ready")
        self.label_status.grid(row=6, column=0, columnspan=2, padx=10, pady=10)

        self.is_recording = False
        
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

    def start_server(self):
        print("[MocapApp] Launching Flask Server...")
        # Ad-hoc SSL is used in app.py
        cmd = [sys.executable, "src/server/app.py"]
        self.server_process = subprocess.Popen(cmd)
        
    def trigger_server_start(self, scene, take):
        try:
            url = "http://127.0.0.1:5000/api/start" # Server runs on HTTP internally locally? 
            # Wait, app.py runs with ssl_context='adhoc', so it is HTTPS even locally?
            # Flask-SocketIO with adhoc ssl means it is HTTPS.
            # We need to verify verify=False for self-signed
            url = "https://127.0.0.1:5000/api/start"
            requests.post(url, json={'scene': scene, 'take': take}, verify=False)
        except Exception as e:
            print(f"[MocapApp] Error triggering server start: {e}")

    def trigger_server_stop(self):
        try:
            url = "https://127.0.0.1:5000/api/stop"
            requests.post(url, json={}, verify=False)
        except Exception as e:
            print(f"[MocapApp] Error triggering server stop: {e}")


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
        self.audio_recorder = AudioRecorder(filename=filename)
        self.audio_recorder.start()
        
        # Start Video Subprocesses
        self.video_processes = []
        try:
            cam_indices = [int(x.strip()) for x in self.entry_cams.get().split(',')]
            for idx in cam_indices:
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
        
        # Trigger Mobile Nodes
        self.trigger_server_start(scene, take)





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
        
        try:
            cam_indices = [int(x.strip()) for x in self.entry_cams.get().split(',')]
        except ValueError:
            cam_indices = []

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
        self.destroy()

if __name__ == "__main__":
    app = MocapApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()

