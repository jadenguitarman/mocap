import re


DEVICE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def sanitize_token(value, default="unknown"):
    value = str(value or default).strip()
    value = DEVICE_ID_RE.sub("-", value)
    return value[:80] or default


def register_device(connected_devices, sid_to_device, latest_previews, socket_sid, device_id, address):
    device_id = sanitize_token(device_id, socket_sid)
    old_device_id = sid_to_device.get(socket_sid)
    if old_device_id and old_device_id != device_id:
        connected_devices.pop(old_device_id, None)
        latest_previews.pop(old_device_id, None)

    sid_to_device[socket_sid] = device_id
    connected_devices[device_id] = {
        'sid': socket_sid,
        'id': device_id,
        'type': 'mobile',
        'address': address,
    }
    return connected_devices[device_id]
