import cv2
from classes.mite import Mite
from classes.Rect import TextZone, MiteZone
from classes.TextReader import get_text_reader
from PIL import Image
import pandas as pd
import pickle
import os
import numpy as np

class MiteManager:
    """Manages mites detection, zone assignment, and data processing."""

    def __init__(self, mites_detection, frames, coordinate_file, name, settings):
        # Guard clauses
        if not mites_detection:
            raise ValueError("Mites detection results must be provided")
        if frames is None or len(frames) == 0:
            raise ValueError("Frames must be provided and not empty")
        if not coordinate_file:
            raise ValueError("Coordinate file must be provided")
        if not name:
            raise ValueError("Name must be provided")
        
        print("Initializing stage...")
        
        self._initialize_paths()
        
        if os.path.exists(self.save_path):
            self.load_miteManager(frames)
        else:
            self._initialize_new_manager(mites_detection, frames, coordinate_file, name, settings)

    def _initialize_paths(self):
        """Initialize file paths."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.save_path = os.path.join(base_dir, "mite_manager.plk")

    def _initialize_new_manager(self, mites_detection, frames, coordinate_file, name, settings):
        """Initialize a new MiteManager instance."""
        self.zones = []
        self.name = name
        self.frames = frames
        self.zone_map = {
            0: "text_zone",
            1: "mite_zone"
        }
        # Set before get_zones/getMites: _read_zone_labels (called from getMites)
        # needs settings.enable_text_recognition to decide whether to run OCR.
        self.settings = settings

        self.get_zones(coordinate_file)
        self.getMites(mites_detection)
        self.img_size = (15, 10)
        self.frame0 = None
        self.data = pd.DataFrame()
        self.mite_data = pd.DataFrame()
        self.reloaded = False

    def save(self):
        with open(self.save_path, 'wb') as f:
            pickle.dump(self, f)

    def __getstate__(self):
        # The raw frame stack (self.frames) is only read while the manager is
        # first built (getMites/_read_zone_labels, recording0). Every reload
        # re-attaches fresh frames via update_mites(), so excluding it here
        # keeps save() from serializing the full per-recording image stack to
        # disk on every recording.
        state = self.__dict__.copy()
        state['frames'] = None
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)

    def load_miteManager(self,frames):
        with open(self.save_path, 'rb') as f:
            loaded = pickle.load(f)
            self.__dict__.update(loaded.__dict__)
            self.reloaded = True
            # Handle legacy saved objects that don't have settings attribute
            if not hasattr(self, 'settings'):
                self.settings = None
            self.update_mites(frames)


    def load_coordinate_file(self, coordinate_file):
        """Load and validate coordinate file path."""
        if not coordinate_file:
            raise ValueError("Coordinate file path cannot be empty")
        
        if not os.path.isabs(coordinate_file):
            coordinate_file = os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__),
                    "..",
                    coordinate_file
                )
            )
        
        if not os.path.exists(coordinate_file):
            raise FileNotFoundError(f"Coordinate file not found: {coordinate_file}")
        
        self.coordinate_file = coordinate_file

    def get_zones(self, coordinate_file):
        """Parse zones from coordinate file."""
        self.load_coordinate_file(coordinate_file)
        
        with open(self.coordinate_file, 'r') as f:
            for line_num, line in enumerate(f, 1):
                try:
                    self._process_zone_line(line, line_num)
                except ValueError as e:
                    print(f"Warning: Line {line_num} - {e}")
                    continue

    def _process_zone_line(self, line, line_num):
        """Process a single line from the coordinate file."""
        parts = line.strip().split()
        
        if len(parts) != 5:
            raise ValueError(f"Invalid line format (expected 5 parts, got {len(parts)}): {line.strip()}")

        try:
            class_id = int(parts[0])
            x1, y1, x2, y2 = map(float, parts[1:])
        except ValueError as e:
            raise ValueError(f"Invalid number format: {e}")

        if class_id not in self.zone_map:
            raise ValueError(f"Unknown class ID {class_id}")

        zone_id = self.zone_map[class_id]

        if zone_id == "mite_zone":
            self.zones.append(MiteZone(int(x1), int(y1), int(x2), int(y2)))
        elif zone_id == "text_zone":
            text_zone = TextZone(int(x1), int(y1), int(x2), int(y2))
            self._assign_text_zone_to_mite_zone(text_zone)

    def _assign_text_zone_to_mite_zone(self, text_zone):
        """Find and assign text zone to its parent mite zone."""
        for mite_zone in self.zones:
            if text_zone in mite_zone:
                text_zone.parent_rect = mite_zone
                mite_zone.add_text_zone(text_zone)
                return
        
        print(f"Warning: Text zone {text_zone} could not be assigned to any mite zone")


    def getMites(self, result):
        """Extract mites from detection results and assign them to zones."""
        # Guard clauses
        if not result or not hasattr(result, 'boxes'):
            print("Warning: No detection results or boxes found")
            return
        
        if not result.boxes.xyxy.numel():
            print("Warning: No bounding boxes in detection results")
            return

        boxes = result.boxes.xyxy.cpu().numpy().astype(int)
        assigned_count = 0
        
        print(f"Processing {len(boxes)} detected mites...")
        
        for i, box in enumerate(boxes):
            try:
                mite = Mite(box, self.frames)
                if self._assign_mite_to_zone(mite):
                    assigned_count += 1
            except Exception as e:
                print(f"Warning: Failed to process mite {i}: {e}")
                continue
        
        print(f"Got mites: {len(boxes)}")
        print(f"Assigned mites: {assigned_count}")
        
        self._read_zone_labels()
        # Save stage after mites and text zones are assigned
        self.save()

    def _assign_mite_to_zone(self, mite):
        """Assign a mite to an appropriate zone."""
        for zone in self.zones:
            if self._is_mite_in_valid_zone(mite, zone):
                return zone.assign_mites(mite)
        return False

    def _is_mite_in_valid_zone(self, mite, zone):
        """Check if mite is in zone but not overlapping text zones."""
        if mite.bbox not in zone:
            return False
        
        # Check that mite doesn't overlap with text zones
        for text_zone in zone.text_zones:
            if mite.bbox in text_zone:
                return False
        
        return True

    def _read_zone_labels(self):
        """Read labels from text zones using OCR, unless disabled in settings."""
        if not getattr(self.settings, 'enable_text_recognition', True):
            print("Text recognition disabled - leaving zone labels for manual entry.")
            return

        text_reader = get_text_reader()
        print("Text reader loaded...")

        for zone in self.zones:
            if not zone.mites:  # Skip zones without mites
                continue
                
            for text_zone in zone.text_zones:
                try:
                    self._process_text_zone(text_zone, text_reader)
                except Exception as e:
                    print(f"Warning: Failed to read text from zone {text_zone}: {e}")

    def _process_text_zone(self, text_zone, text_reader):
        """Process a single text zone to extract label."""
        img = text_zone.get_ROI(self.frames)[0]
        img_PIL = Image.fromarray(img).convert("RGB")
        text_zone.text = text_reader.read(img_PIL)
        print(f"Read text: '{text_zone.text}' from zone {text_zone}")
        
        # Update the zone id for the parent zone
        if hasattr(text_zone, 'parent_rect') and text_zone.parent_rect:
            text_zone.parent_rect.zone_id = text_zone.text

    def reset(self):
        """Delete save file and reset object to default state."""
        if os.path.exists(self.save_path):
            os.remove(self.save_path)
            print(f"Deleted save file: {self.save_path}")

    def update_mites(self, frames):
        """Update mites with new frame data."""
        if frames is None or len(frames) == 0:
            raise ValueError("Frames must be provided and not empty")

        self.frames = frames
        for zone in self.zones:
            for mite in zone.mites:
                mite.update_ROI(frames)

    def update_mite_status(self, ground_truth):
        """Update the status of all mites."""
        save = ground_truth in ['alive', 'dead']

        for zone in self.zones:
            print(f"Zone {zone.zone_id} has {len(zone.mites)} mites.")
            
            for mite in zone.mites:
                mite.update_status()
           
        
                if save:
                    mite.save_with_ground_truth(ground_truth)


    def post_process_mite_data(self,mites_data, streak, num_recordings, recording_count):
        # map status to numbers
        mites_data.loc[:, "status_num"] = mites_data["status"].map({"alive": 0, "dead": 1})

        # helper to get streak start for one group
        def get_streak_start(series):
            rolling_sum = series.rolling(window=streak).sum()
            mask = rolling_sum == streak
            if mask.any():
                idx = mask.idxmax()  # first index where streak occurs
                rec_num = mites_data.loc[idx, "recording"]
                return rec_num - streak + 1
            else:
                return np.nan



        # group by mite_ID and compute streak_start per mite
        streak_starts = mites_data.groupby("mite ID")["status_num"].apply(get_streak_start)

        # map the streak_start back to the original DataFrame
        mites_data["streak_start"] = mites_data["mite ID"].map(streak_starts)

        # Calculate streak_end for each mite
        mites_data["streak_end"] = mites_data["streak_start"] + streak - 1

        if recording_count >= num_recordings:
            mites_data["status"] = np.select(
                [
                    mites_data["streak_start"].notna() & (mites_data["recording"] >= mites_data["streak_start"]),
                    mites_data["streak_start"].notna() & (mites_data["recording"] < mites_data["streak_start"]),
                    mites_data["streak_start"].isna()
                ],
                ["dead", # dead if streak_start is not set and recording is greater than streak_start
                 "alive", # alive if streak_start is not set and recording is less than streak_start
                 "alive"], #alive if no streak
                default=mites_data["status"]
            )

        
        return mites_data


    def save_data(self, recording_count, dead_streak, num_recordings):
        # Step 1: Prepare the data
        mite_data = []

        for zone in self.zones:
            if zone.zone_id == "EMPTY":
                continue
       

            # collect individual mite data
            for mite in zone.mites:
                mite_data.append(mite.to_dict(recording_count))

        if mite_data:
            df_mites = pd.DataFrame(mite_data)

        
            self.mite_data = pd.concat([df_mites, self.mite_data], ignore_index=True)
            self.mite_data = self.mite_data.sort_values(by=['mite ID', 'recording'])

            #apply streak dead rule
            # self.mite_data = self.post_process_mite_data(self.mite_data, dead_streak, num_recordings, recording_count)

            # Calculate summary statistics by recording and zone_id

            summary = self.mite_data.groupby(["recording", "zone ID"]).agg(
                total_mites=("mite ID", "nunique"),
                dead=("status", lambda x: (x == "dead").sum()),
                alive=("status", lambda x: (x == "alive").sum())
            ).reset_index()

            summary["Survival %"] = summary.apply(
                lambda row: (row["alive"] / row["total_mites"] * 100) if row["total_mites"] > 0 else 0.0,
                axis=1
            )

            self.data = summary


            summary.to_csv("mite_summary.csv", index=False)
            self.mite_data.to_csv("mite_data.csv", index=False)

        return self.data, self.mite_data



       


       