import os
import cv2
import numpy as np
from concurrent.futures import ThreadPoolExecutor


COUNTER_FILE = ".count"


def get_frames(folder_path, discobox_run=True, reanalyze=True):
    """Load frames from folder(s) with improved error handling."""
    # Guard clauses
    if not folder_path:
        raise ValueError("Folder path must be provided")

    # Resolve full folder path
    resolved_path = _resolve_folder_path(folder_path, discobox_run)

    if not os.path.exists(resolved_path):
        raise FileNotFoundError(f"Folder does not exist: {resolved_path}")

    # Get subfolders to process
    subfolders = _get_subfolders_to_process(resolved_path)

    # When not reanalyzing, only the last recording's stack is ever kept
    # (see _return_frames_based_on_mode) - skip decoding the rest entirely.
    if not reanalyze:
        subfolders = [sorted(subfolders)[-1]]

    # Load frames from each subfolder
    frames_by_folder = {}
    for subfolder in subfolders:
        frames = _load_frames_from_folder(subfolder)
        if frames:
            frames_by_folder[subfolder] = np.stack(frames)




    if not frames_by_folder:
        raise ValueError("No images found in folder or none could be loaded.")

    return  _return_frames_based_on_mode(frames_by_folder, reanalyze)


def get_settings(folder_path):
    """Load settings from a text file."""
    settings_file = os.path.join(folder_path, "settings.txt")
    if not os.path.exists(settings_file):
        raise FileNotFoundError(f"Settings file not found: {settings_file}")

    with open(settings_file, "r") as f:
        settings = f.read()

    return settings


def _resolve_folder_path(folder_path, discobox_run):
    """Resolve the absolute path for the folder."""
    if discobox_run:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.abspath(os.path.join(base_dir, "..", "..", folder_path))
    else:
        return os.path.abspath(folder_path)


def _get_subfolders_to_process(folder_path):
    """Get list of subfolders to process."""
    subfolders = sorted([
        os.path.join(folder_path, d)
        for d in os.listdir(folder_path)
        if os.path.isdir(os.path.join(folder_path, d))
    ])
    
    # If no subfolders found, use the main folder
    return subfolders if subfolders else [folder_path]


def _load_frames_from_folder(subfolder):
    """Load all BMP frames from a specific folder.

    Images are decoded in parallel (cv2.imread releases the GIL, so this is a
    real speedup on disk-I/O-bound loads) while preserving on-disk sort order,
    which the motion-based alive/dead analysis depends on.
    """
    img_paths = []
    for root, dirs, files in os.walk(subfolder, followlinks=True):
        for fname in files:
            if fname.lower().endswith(".bmp"):
                img_paths.append(os.path.join(root, fname))

    img_paths.sort()

    if not img_paths:
        return []

    with ThreadPoolExecutor(max_workers=min(8, len(img_paths))) as executor:
        loaded = list(executor.map(_load_single_image, img_paths))

    return [frame for frame in loaded if frame is not None]


def _load_single_image(img_path):
    """Load and convert a single image."""
    try:
        img = cv2.imread(img_path)
        if img is None:
            print(f"Skipped (not image or unreadable): {img_path}")
            return None
        
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
    except Exception as e:
        print(f"Error loading image {img_path}: {e}")
        return None


def _return_frames_based_on_mode(frames_by_folder, reanalyze):
    """Return frames based on analysis mode."""
    if not reanalyze:
        # Only return the last folder's stack
        last_folder = sorted(frames_by_folder.keys())[-1]
        return frames_by_folder[last_folder]
    
    # Return all as list for reanalysis
    return list(frames_by_folder.values())




def draw_rects_from_polygon_labels(image_path, label_path, output_path):
    """Draw rectangles from polygon labels on an image."""
    # Guard clauses
    if not image_path or not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")
    
    if not label_path or not os.path.exists(label_path):
        raise FileNotFoundError(f"Label file not found: {label_path}")
    
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Could not load image: {image_path}")
    
    h, w = image.shape[:2]
    
    try:
        with open(label_path, 'r') as f:
            lines = f.readlines()
        
        for line_num, line in enumerate(lines, 1):
            try:
                _draw_rect_from_line(image, line, w, h)
            except Exception as e:
                print(f"Warning: Error processing line {line_num}: {e}")
                continue
        
        cv2.imwrite(output_path, image)
        
    except Exception as e:
        raise RuntimeError(f"Failed to process labels: {e}")


def _draw_rect_from_line(image, line, image_width, image_height):
    """Draw a rectangle from a single label line."""
    class_id, (x1, y1, x2, y2) = _extract_rect_from_polygon_line(line, image_width, image_height)
    
    color = (0, 255, 0) if class_id == 0 else (0, 0, 255)
    cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
    cv2.putText(image, f"Class {class_id}", (x1, max(y1 - 10, 0)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)


def _extract_rect_from_polygon_line(line, image_width, image_height):
    """Extract rectangle coordinates from a polygon line."""
    parts = list(map(float, line.strip().split()))
    
    if len(parts) < 9:  # class_id + 8 coordinates
        raise ValueError(f"Expected at least 9 parts, got {len(parts)}")
    
    class_id = int(parts[0])
    coords = parts[1:9]  # Take first 8 coordinates
    
    if len(coords) != 8:
        raise ValueError(f"Expected 8 coordinates, got {len(coords)}")
    
    x_coords = [coords[i] * image_width for i in range(0, 8, 2)]
    y_coords = [coords[i] * image_height for i in range(1, 8, 2)]
    
    x_min, x_max = int(min(x_coords)), int(max(x_coords))
    y_min, y_max = int(min(y_coords)), int(max(y_coords))
    
    return class_id, (x_min, y_min, x_max, y_max)


def convert_yolo_to_coords(input_file, output_file, image_path):
    """Convert YOLO polygon format bounding boxes to pixel coordinates (x1, y1, x2, y2).
    
    Args:
        input_file (str): Path to the input file with YOLO format bounding boxes.
        output_file (str): Path to save the output file with pixel coordinates.
        image_path (str): Path to the image to get dimensions for conversion.
    
    Output format:
        class_id x1 y1 x2 y2  (pixel coordinates)
    """
    # Load image using cv2
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Image not found or unable to open: {image_path}")
    
    img_height, img_width = img.shape[:2]
    print(f"Image size: {img_width}x{img_height}")

    with open(input_file, 'r') as f_in, open(output_file, 'w') as f_out:
        for line in f_in:
            parts = line.strip().split()
            if len(parts) != 9:
                print(f"Skipping invalid line (expected 9 elements): {line.strip()}")
                continue

            class_id = parts[0]
            coords = list(map(float, parts[1:]))

            xs = coords[0::2]
            ys = coords[1::2]

            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)

            # Convert normalized coordinates to pixel coordinates
            x1_px = min_x * img_width
            y1_px = min_y * img_height
            x2_px = max_x * img_width
            y2_px = max_y * img_height

            f_out.write(f"{class_id} {x1_px:.2f} {y1_px:.2f} {x2_px:.2f} {y2_px:.2f}\n")

    print(f"Conversion complete! Output saved to {output_file}")


def read_counter():
    if os.path.exists(COUNTER_FILE):
        with open(COUNTER_FILE, "r") as f:
            try:
                return int(f.read().strip())
            except ValueError:
                return 0
    return 0

def write_counter(count):
    with open(COUNTER_FILE, "w") as f:
        f.write(str(count))

def reset_counter():
    if os.path.exists(COUNTER_FILE):
        os.remove(COUNTER_FILE)

