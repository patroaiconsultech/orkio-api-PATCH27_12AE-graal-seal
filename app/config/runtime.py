import os

RUNTIME_FLAGS = {
    "capability_enabled": os.getenv("ORKIO_CAPABILITY_ENABLED", "true").lower() == "true",
    "bridge_enabled": os.getenv("ORKIO_BRIDGE_ENABLED", "true").lower() == "true",
    "allow_write_actions": os.getenv("ORKIO_WRITE_ENABLED", "true").lower() == "true",
}
