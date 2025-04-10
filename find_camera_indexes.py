import cv2

def find_camera_indexes(max_devices=10):
    camera_indexes = []
    for index in range(max_devices):
        cap = cv2.VideoCapture(index)
        if cap.isOpened():
            camera_indexes.append(index)
            print(f"Camera found at index: {index}")
        cap.release()
    if not camera_indexes:
        print("No cameras detected.")
    return camera_indexes

# Scan for cameras
camera_indexes = find_camera_indexes()
print(f"Available camera indexes: {camera_indexes}")