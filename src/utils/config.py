
import toml
import os

CONFIG_PATH = "config.toml"

def load_config(path=CONFIG_PATH):
    if not os.path.exists(path):
        print(f"Warning: {path} not found. Using defaults.")
        return {}
    
    try:
        data = toml.load(path)
        return data
    except Exception as e:
        print(f"Error loading config: {e}")
        return {}

# Global instance for easy access
config = load_config()
