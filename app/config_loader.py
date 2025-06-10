import os
import yaml

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.yml')
    config_path = os.path.abspath(config_path)
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)
