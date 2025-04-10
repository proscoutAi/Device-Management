import cv2
import numpy as np
from pypylon import pylon

# Initialize the camera
camera = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateFirstDevice())
camera.Open()

# Set the camera resolution to its full sensor size
camera.Width = 1936
camera.Height = 1216

# Start grabbing
camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

converter = pylon.ImageFormatConverter()
converter.OutputPixelFormat = pylon.PixelType_RGB8packed
converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned

try:
        grab_result = camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
        if grab_result.GrabSucceeded():
            # Convert to OpenCV image
            image = converter.Convert(grab_result)
            img = image.GetArray()

            # Resize the image to fit within 640x640 while preserving aspect ratio
            target_size = 640
            h, w, _ = img.shape
            scaling_factor = min(target_size / w, target_size / h)
            new_width = int(w * scaling_factor)
            new_height = int(h * scaling_factor)

            resized_img = cv2.resize(img, (new_width, new_height))

            # Add padding to make it 640x640
            top_pad = (target_size - new_height) // 2
            bottom_pad = target_size - new_height - top_pad
            left_pad = (target_size - new_width) // 2
            right_pad = target_size - new_width - left_pad

            padded_img = cv2.copyMakeBorder(
                resized_img, top_pad, bottom_pad, left_pad, right_pad,
                cv2.BORDER_CONSTANT, value=(0, 0, 0)  # Black padding
            )

            # Display the image
            cv2.imshow("Padded Image", padded_img)
            cv2.imwrite("test.jpg",padded_img)
            cv2.imwrite("orig.jpg",img)

            # Break loop if 'q' is pressed
            

        grab_result.Release()
finally:
    camera.StopGrabbing()
    camera.Close()
    cv2.destroyAllWindows()
