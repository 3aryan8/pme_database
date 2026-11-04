"""
Module for image processing with YOLO model.
"""

from typing import List, Tuple
import config
from modules.storage_manager import StorageManager

class YOLOProcessor:
    """Class to handle YOLO model inference and image processing."""
    
    def __init__(self, model_path: str = None):
        """
        Initialize the YOLO processor.
        
        Args:
            model_path: Path to the YOLO model file
        """
        self.model_path = model_path or config.MODEL_PATH
        self.model = None
        self.storage_manager = StorageManager()
        self.box_annotator = None
        self.label_annotator = None

    def load_model(self):
        """Load the YOLO model if not already loaded."""
        if self.model is None:
            from ultralytics import YOLO
            import supervision as sv

            self.model = YOLO(self.model_path)
            self.box_annotator = sv.BoxAnnotator()
            self.label_annotator = sv.LabelAnnotator()
        return self.model
    
    def _separate_signature(self, image, index: int) -> Tuple[str, str, str]:
        """Create separate stamp and signature views from a detected stamp crop."""
        import cv2
        import numpy as np

        height = image.shape[0]
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        blue_ink = cv2.inRange(hsv, (90, 35, 25), (175, 255, 255))
        blue_ink = cv2.morphologyEx(
            blue_ink,
            cv2.MORPH_OPEN,
            np.ones((2, 2), dtype=np.uint8),
        )

        # Keep fine pen strokes while removing the thicker printed stamp lettering.
        stamp_core = cv2.morphologyEx(
            blue_ink,
            cv2.MORPH_OPEN,
            np.ones((7, 7), dtype=np.uint8),
        )
        thin_strokes = cv2.subtract(blue_ink, stamp_core)
        upper_region = np.zeros_like(thin_strokes)
        upper_region[: max(int(height * 0.55), 1), :] = 255
        signature_mask = cv2.bitwise_and(thin_strokes, upper_region)
        signature_mask = cv2.morphologyEx(
            signature_mask,
            cv2.MORPH_CLOSE,
            np.ones((3, 3), dtype=np.uint8),
        )

        signature = np.full_like(image, 255)
        signature[signature_mask > 0] = image[signature_mask > 0]
        stamp = image.copy()
        stamp[signature_mask > 0] = 255

        extracted_path = self.storage_manager.save_extracted_object(image, index)
        stamp_path = self.storage_manager.save_separated_object(
            stamp,
            "stamp",
            index,
        )
        signature_path = self.storage_manager.save_separated_object(
            signature,
            "signature",
            index,
        )
        return extracted_path, stamp_path, signature_path

    def process_image(
        self,
        image_path: str,
    ) -> Tuple[str, List[str], List[str], List[str]]:
        """
        Run YOLO inference on an image and return the annotated image and cropped objects.
        
        Args:
            image_path: Path to the input image
            
        Returns:
            Tuple containing:
                - Path to the annotated output image
                - List of all detected object image paths
                - List of separated stamp image paths
                - List of separated signature image paths
        """
        import cv2
        import supervision as sv

        # Load the model if not already loaded
        self.load_model()
        
        # Load the image and run inference
        image = cv2.imread(image_path)
        results = self.model(image, verbose=False)[0]
        detections = sv.Detections.from_ultralytics(results)
        
        # Annotate the image
        annotated_image = image.copy()
        annotated_image = self.box_annotator.annotate(scene=annotated_image, detections=detections)
        annotated_image = self.label_annotator.annotate(scene=annotated_image, detections=detections)
        
        # Save the annotated image
        output_path = self.storage_manager.save_output_image(annotated_image)
        
        # Save and return cropped objects
        cropped_images = []
        stamp_images = []
        signature_images = []
        for i, (x_min, y_min, x_max, y_max) in enumerate(detections.xyxy):
            cropped_image = image[int(y_min):int(y_max), int(x_min):int(x_max)]
            cropped_path, stamp_path, signature_path = self._separate_signature(
                cropped_image,
                i,
            )
            cropped_images.append(cropped_path)
            stamp_images.append(stamp_path)
            signature_images.append(signature_path)
        
        return output_path, cropped_images, stamp_images, signature_images
