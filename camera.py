import cv2 as cv2
from numpy import ndarray


class Camera:
    """A simple class to interact with a camera"""

    def __init__(self, camera_index: int = 0):
        """
        @param camera_index: The index of the camera device to use
        """
        try:
            self.capture = cv2.VideoCapture(camera_index)
            # Set the desired resolution
            self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)  # Set width to 1280 pixels
            self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)  # Set height to 720 pixels

            if not self.capture.isOpened():
                raise Exception(f'Camera with index {camera_index} could not be opened')
            else:
                ret, frame = self.capture.read()
            if not ret:
                print("Failed to grab frame")
                
                cv2.imshow("Frame", frame)
        except Exception as e:
                print(f"Error during camera open: {e}")
                raise e
          

    def snap(self) -> ndarray:
        """
        Capture an image from the camera

        @return: The image as a numpy array
        """

        ret, frame = self.capture.read()
        if not ret:
            raise Exception('Failed to capture image')

        return frame


    def release(self):
        """Release the camera device"""

        self.capture.release()