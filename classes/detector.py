from ultralytics import YOLO
import os
import torch

class Detector:
    """YOLO-based detector for Varroa mites."""
    
    def __init__(self):
        self.model_path = self._get_model_path()
        self.model = self._initialize_model()
        self.result = None

    def _get_model_path(self):
        """Get the path to the trained model."""
        return os.path.join(
            os.path.dirname(__file__),
            "..",
            "model_weights",
            "runs",
            "detect",
            "fine_tuned_varro_model6",
            "weights",
            "best.pt"
        )

    def _initialize_model(self):
        """Initialize the YOLO model."""
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Model file not found: {self.model_path}")
        
        return YOLO(self.model_path, verbose=False)

    def run_detection(self, image):
        """Run detection on a single image."""
        # Guard clauses
        if image is None:
            raise ValueError("Image cannot be None")
        
        if not hasattr(self.model, 'predict') and not callable(getattr(self.model, '__call__', None)):
            raise RuntimeError("Model is not properly initialized")

        try:
            result = self.model(
                image,
                imgsz=1024,  # fine tuned uses 1024 / not fine tuned 6016
                max_det=2000,
                conf=0.2,
                iou=0.5,
                save=False,
                show_labels=False,
                line_width=2,
                save_txt=False,
                save_conf=False,
                verbose=False,
                batch=1,
                exist_ok=True,
                # device="cuda"   # uncomment if you have gpu
            )
            
            if not result or len(result) == 0:
                raise RuntimeError("Detection failed or returned no results")
            
            self.result = result[0]  # only for one image
            
        except Exception as e:
            raise RuntimeError(f"Detection failed: {str(e)}")

    def has_detections(self):
        """Check if the last detection found any objects."""
        if self.result is None:
            return False

        return hasattr(self.result, 'boxes') and len(self.result.boxes) > 0


_detector_instance = None


def get_detector():
    """Return a process-wide cached Detector.

    Reusing one instance across analyses run in the same app session avoids
    reloading the YOLO weights from disk every time the user starts a new
    analysis; run_detection() overwrites self.result each call so reuse is safe.
    """
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = Detector()
    return _detector_instance





# Train 

if __name__ == '__main__':
    if False:
        import torch
        # Check if GPU is available
        print("CUDA available:", torch.cuda.is_available())
        print("GPU Name:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "N/A")


        # Load a pretrained model (or your existing one)
        model = YOLO("../model_weights/best.pt") 
        

        #freeze first 100 layers of the model
        layers = list(model.model.children())

        for i, layer in enumerate(layers[:100]):
            for param in layer.parameters():
                param.requires_grad = False


        model.train(
            data="yolo_data/data.yaml",  # path to your dataset YAML
            epochs=70,
            imgsz=1024,
            batch=1,
            name="fine_tuned_varro_model",
            resume=False  # True if you're continuing from a checkpoint
        )


