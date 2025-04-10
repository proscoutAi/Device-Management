import uuid
device_uuid = str(uuid.uuid4())  # Generate a unique identifier
with open("/Users/ronenrayten/Spray Detection MVP/SprayDetectionUnet/ProScout-master/camera/device_id.txt", "w") as f:
    f.write(device_uuid)