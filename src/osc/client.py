
from pythonosc.udp_client import SimpleUDPClient
import subprocess
import platform
from utils.config import config


class MocapOSC:
    def __init__(self, iphone_ip=None, iphone_port=None, unreal_ip=None, unreal_port=None):
        net_config = config.get("Network", {})
        
        self.iphone_ip = iphone_ip or net_config.get("iphone_ip", "192.168.1.100")
        self.iphone_port = iphone_port or net_config.get("iphone_port", 5000)
        self.unreal_ip = unreal_ip or net_config.get("unreal_ip", "127.0.0.1")
        self.unreal_port = unreal_port or net_config.get("unreal_port", 8000)

        self.client_iphone = SimpleUDPClient(self.iphone_ip, self.iphone_port)
        self.client_unreal = SimpleUDPClient(self.unreal_ip, self.unreal_port)


    def start_recording(self, scene_name, take_number):
        # iPhone Trigger
        self.client_iphone.send_message("/recStart", [scene_name, take_number])
        
        # Unreal Trigger (Simplified to match standard guide)
        self.client_unreal.send_message("/recStart", [scene_name, take_number])
        
        print(f"[OSC] Sent Start Command to iPhone({self.iphone_ip}) and Unreal({self.unreal_ip})")

    def stop_recording(self):
        # iPhone Trigger
        self.client_iphone.send_message("/recStop", [])
        
        # Unreal Trigger
        self.client_unreal.send_message("/recStop", [])
        print(f"[OSC] Sent Stop Command")

    def handshake(self):
        """
        Checks whether configured OSC endpoints are reachable enough to start a take.
        UDP ports cannot prove readiness without a responder, so this validates host reachability.
        """
        messages = []
        
        try:
            param = '-n' if platform.system().lower() == 'windows' else '-c' 
            command = ['ping', param, '1', self.iphone_ip]
            subprocess.check_call(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"[Handshake] iPhone at {self.iphone_ip} is reachable.")
        except subprocess.CalledProcessError:
            messages.append(f"Live Link Face host {self.iphone_ip} did not answer ping. Check Wi-Fi, the configured iPhone IP, and firewall settings.")

        if self.unreal_ip not in ("127.0.0.1", "localhost", "0.0.0.0"):
            try:
                param = '-n' if platform.system().lower() == 'windows' else '-c'
                command = ['ping', param, '1', self.unreal_ip]
                subprocess.check_call(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print(f"[Handshake] Unreal host at {self.unreal_ip} is reachable.")
            except subprocess.CalledProcessError:
                messages.append(f"Unreal host {self.unreal_ip} did not answer ping. Start Unreal or fix the configured OSC host.")

        if messages:
            for msg in messages:
                print(f"[Handshake] FAILURE: {msg}")
            return False, " ".join(messages)

        return True, "OSC hosts are reachable."
