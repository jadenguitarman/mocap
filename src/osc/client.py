
from pythonosc.udp_client import SimpleUDPClient
import socket
import time
import subprocess
import platform

class MocapOSC:
    def __init__(self, iphone_ip="192.168.1.100", iphone_port=5000, unreal_ip="127.0.0.1", unreal_port=8000):
        self.iphone_ip = iphone_ip
        self.iphone_port = iphone_port
        self.unreal_ip = unreal_ip
        self.unreal_port = unreal_port

        self.client_iphone = SimpleUDPClient(self.iphone_ip, self.iphone_port)
        self.client_unreal = SimpleUDPClient(self.unreal_ip, self.unreal_port)

    def start_recording(self, scene_name, take_number):
        # iPhone Trigger
        # Typical Live Link Face OSC for record is /RecordStart but doc says /recStart
        # We will wrap it with Scene/Take metadata if possible, but SimpleUDPClient sends address + args.
        self.client_iphone.send_message("/recStart", [scene_name, take_number])
        
        # Unreal Trigger
        # /remote/object/call is typically for RC API, but assuming OSC mapping exists in UE5
        self.client_unreal.send_message("/remote/object/call", ["TakeRecorder", "Start"])
        
        print(f"[OSC] Sent Start Command to iPhone({self.iphone_ip}) and Unreal({self.unreal_ip})")

    def stop_recording(self):
        self.client_iphone.send_message("/recStop", [])
        self.client_unreal.send_message("/remote/object/call", ["TakeRecorder", "Stop"])
        print(f"[OSC] Sent Stop Command")

    def handshake(self):
        """
        Checks if the iPhone IP is reachable via Ping.
        UDP ports cannot be easily checked for 'openness' without a listener/response protocol.
        """
        success = True
        
        # Ping iPhone
        try:
            param = '-n' if platform.system().lower() == 'windows' else '-c'
            command = ['ping', param, '1', self.iphone_ip]
            subprocess.check_call(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"[Handshake] iPhone at {self.iphone_ip} is reachable.")
        except subprocess.CalledProcessError:
            print(f"[Handshake] FAILURE: iPhone at {self.iphone_ip} is unreachable.")
            success = False

        # For Unreal (Localhost), we assume it's there if running, but we can't easily check UDP port 8000 
        # unless Unreal sends a heartbeat back. For now, we assume localhost is always "reachable".
        
        return success
