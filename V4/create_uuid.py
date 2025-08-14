import uuid
device_uuid = str(uuid.uuid4())  # Generate a unique identifier
with open("/home/proscout/ProScout-master/device-manager/device_id.txt", "w") as f:
    f.write(device_uuid)