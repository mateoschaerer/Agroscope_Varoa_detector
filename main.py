import sys
import os
import threading
import time

# Ensure root of the project is in Python path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from classes.detector import get_detector
from classes.settings import Settings
from utils.tools import get_frames
from classes.MiteManager import MiteManager
from classes.PlotterModular import Plotter  # Use backwards compatible import



class AnalysisState:
    """Shared state for analysis pause/resume control"""
    def __init__(self):
        self.paused = False
        self.continue_analysis = False
        self.pause_event = threading.Event()
        self.continue_event = threading.Event()
        self.mite_manager = None
        self.recording_number = 0
        self.user_confirmed_continue = False
    
    def pause_after_recording1(self, mite_manager, recording_number=1):
        """Pause the analysis after recording 1"""
        self.paused = True
        self.continue_analysis = False
        self.user_confirmed_continue = False
        self.mite_manager = mite_manager
        self.recording_number = recording_number
        self.pause_event.set()  # Signal that pause occurred
        self.continue_event.clear()  # Clear continue event
        print(f"[INFO] Analysis paused after recording {recording_number}")
    
    def resume_analysis(self):
        """Resume analysis after user confirmation"""
        if self.paused:
            self.continue_analysis = True
            self.user_confirmed_continue = True
            self.paused = False
            self.continue_event.set()  # Signal to continue
            print("[INFO] Analysis resuming...")
    
    def wait_for_continue(self, timeout=None):
        """Wait for user to continue analysis"""
        if self.paused:
            print("[INFO] Waiting for user to continue analysis...")
            self.continue_event.wait(timeout)
            return self.user_confirmed_continue
        return True


# Global analysis state instance
analysis_state = AnalysisState()


def continue_analysis_from_gui():
    """Function called by GUI to continue analysis after pause"""
    print("[INFO] GUI requested analysis continuation")
    analysis_state.resume_analysis()
    return True


def get_analysis_state():
    """Get the current analysis state for GUI"""
    return analysis_state



"""def _create_reanalysis_directory(results_base):
    Create a new reanalysis directory with incremental naming.
    i = 1
    while True:
        reanalyze_path = os.path.join(results_base, f"reanalysis{i}")
        if not os.path.exists(reanalyze_path):
            os.makedirs(reanalyze_path)
            print(f"reanalysis{i} created...")
            return reanalyze_path
        i += 1"""


def _process_single_recording(detector, frames, num_per_plate, name, ground_truth, 
                            results_folder, discobox_run, recording_number, dead_streak=1, num_recordings=1, settings=None):
    """Process a single recording and generate its plots and data."""
    # Guard clause: Check if frames exist (frames should be a single numpy stack here)
    if frames is None or len(frames) == 0:
        raise ValueError("No frames provided for processing")
    
    os.makedirs(results_folder, exist_ok=True)
    
    # Run detection
    detector.run_detection(frames[0])
    
    # Create stage manager
    stage = MiteManager(
        coordinate_file=f"Zoning/coordinates{num_per_plate}.txt",
        mites_detection=detector.result,
        frames=frames,
        name=name,
        settings=settings
    )
    
    stage.update_mite_status(ground_truth)
    stage.save_data(recording_count=recording_number, dead_streak=dead_streak, num_recordings=num_recordings)

    #plotter.create_recording_pdf(recording_count=recording_number)
    
    stage.save()
    return stage


def _process_recording0(detector, frames, num_per_plate, name, discobox_run, results_folder=None,settings = None):
    """Lightweight preliminary pass (recording 0).
    Purpose: run detection, read text zones, persist a MiteManager stage to disk
    so the GUI can load and allow user edits before recording 1 runs.

    This function intentionally does NOT create plots or call save_data.
    """
    if frames is None or len(frames) == 0:
        raise ValueError("No frames provided for recording0")

    os.makedirs(results_folder or os.path.join("outputs", "recording0"), exist_ok=True)

    # Run detection on the first frame
    detector.run_detection(frames[0])

    # Create stage manager from the detection result; MiteManager will read text zones
    stage = MiteManager(
        coordinate_file=f"Zoning/coordinates{num_per_plate}.txt",
        mites_detection=detector.result,
        frames=frames,
        name=name,
        settings=settings
    )

    # Persist the stage to disk so GUI can load it for verification
    try:
        stage.save()
    except Exception:
        # MiteManager.getMites may already call save(); ignore save failures here
        pass

    return stage


def _generate_summary_reports(plotter, stage):
    """Generate summary reports and plots."""
    plotter.make_survival_time_graph()
    plotter.plot_variability_by_mite()
    plotter.excel_summary_mites()
    plotter.excel_summary_recordings()
    stage.reset()


def reanalyze_recording(results_base, num_per_plate, detector, frames_by_recording, 
                       discobox_run, name, ground_truth, pause_callback=None, pause_after_recording1=False, dead_streak=1, settings=None):
    """Reanalyze recordings and generate comprehensive reports."""
    # Guard clauses - frames_by_recording is a list of numpy stacks
    if not frames_by_recording or len(frames_by_recording) == 0:
        raise ValueError("No recordings provided for reanalysis")
    
    if not detector:
        raise ValueError("Detector not provided")
    
    # Reset analysis state at the beginning
    analysis_state.paused = False
    analysis_state.continue_analysis = False
    analysis_state.user_confirmed_continue = False
    analysis_state.pause_event.clear()
    analysis_state.continue_event.clear()

    reanalyze_path = results_base

    plotter = None
    stage = None
    
    # First run a lightweight recording0: detect + read text + save stage only
    try:
        print("[INFO] Running preliminary recording0 (detect + read text) to produce editable stage")
        frames0 = frames_by_recording[0]
        stage0 = _process_recording0(detector, frames0, num_per_plate, name, discobox_run,
                                     results_folder=os.path.join(reanalyze_path, "recording0"), settings=settings)

        # Pause and hand the stage to the GUI for verification before recording1
        analysis_state.pause_after_recording1(stage0, recording_number=0)
        if pause_callback:
            print("[INFO] Calling GUI pause callback for recording0 stage...")
            pause_callback(stage0)

        print("[INFO] Analysis paused after recording0. Waiting for user confirmation to continue...")
        analysis_state.wait_for_continue()

        if not analysis_state.user_confirmed_continue:
            print("[ERROR] User did not confirm continuation after recording0 - stopping analysis")
            return

        print("[OK] User confirmed continuation after recording0 - proceeding with recording 1...")

    except Exception as e:
        print(f"Warning: recording0 pass failed: {e}")

    # Process each recording starting at recording 1
    for i in range(0, len(frames_by_recording)):
        recording_number = i + 1
        frames = frames_by_recording[i]
        results_folder = os.path.join(reanalyze_path, f"recording{recording_number}")
        
        stage = _process_single_recording(
            detector, frames, num_per_plate, name, ground_truth,
            results_folder, discobox_run, recording_number, dead_streak=dead_streak, num_recordings=len(frames_by_recording), settings=settings
        )
    
    # Generate per recording summaries
    for i in range(0, len(frames_by_recording)):
        recording_number = i + 1
        print(f"PLOTTING recording {i + 1}")
        results_folder = os.path.join(reanalyze_path, f"recording{i+1}")
        plotter = Plotter(
            stage=stage,
            output_folder=results_folder,
            discobox_run=discobox_run
        )

        plotter.make_survival_graph(recording_number=recording_number)

    # frame_path is derived from the shared general_summary_path (not the
    # per-recording folder), so every iteration above would overwrite the same
    # file - write it once, after the loop, instead of once per recording.
    if plotter:
        plotter.save_frame0_detection(frames[0], thickness=2)

    # general summaries
    if plotter and stage:
        _generate_summary_reports(plotter, stage)


def continue_reanalyze_from_recording2(results_base, num_per_plate, detector, frames_by_recording, 
                                     discobox_run, name, ground_truth, dead_streak=1, settings=None):
    """Continue reanalysis from recording 2 after pause."""
    # Guard clauses
    if not frames_by_recording or len(frames_by_recording) < 2:
        raise ValueError("Need at least 2 recordings to continue from recording 2")
    
    if not detector:
        raise ValueError("Detector not provided")
    
    # Find the existing reanalysis directory
    reanalyze_path = None
    i = 1
    while True:
        potential_path = os.path.join(results_base, f"reanalysis{i}")
        if os.path.exists(potential_path):
            # Check if recording1 exists but recording2 doesn't
            recording1_path = os.path.join(potential_path, "recording1")
            recording2_path = os.path.join(potential_path, "recording2")
            if os.path.exists(recording1_path) and not os.path.exists(recording2_path):
                reanalyze_path = potential_path
                break
            i += 1
        else:
            break
    
    if not reanalyze_path:
        raise ValueError("No paused analysis found to continue")
    
    print(f"[INFO] Continuing analysis from: {reanalyze_path}")
    
    plotter = None
    stage = None
    
    # Process remaining recordings (starting from recording 2)
    for i in range(1, len(frames_by_recording)):  # Start from index 1 (recording 2)
        recording_number = i + 1
        frames = frames_by_recording[i]
        results_folder = os.path.join(reanalyze_path, f"recording{recording_number}")
        
        print(f"[INFO] Processing recording {recording_number}...")
        plotter, stage = _process_single_recording(
            detector, frames, num_per_plate, name, ground_truth,
            results_folder, discobox_run, recording_number, dead_streak=dead_streak, num_recordings=len(frames_by_recording), settings=settings
        )
    
    # Generate summary reports
    if plotter and stage:
        _generate_summary_reports(plotter, stage)
    
    # Remove pause file if it exists
    pause_file = os.path.join(reanalyze_path, "pause_analysis.flag")
    if os.path.exists(pause_file):
        os.remove(pause_file)
        print("[INFO] Removed pause flag file")


def analyze_recording(results_base, num_per_plate, detector, frames, discobox_run, 
                     name, num_recordings, ground_truth, count, dead_streak=1, settings=None):
    """Analyze a single recording session."""
    # Guard clauses - frames is a single numpy stack
    if frames is None or len(frames) == 0:
        raise ValueError("No frames provided for analysis")
    
    if not detector:
        raise ValueError("Detector not provided")
    
    if count <= 0:
        raise ValueError("Count must be greater than 0")

    results_folder = os.path.join(results_base, "results", f"recording{count}")
    
    plotter, stage = _process_single_recording(
        detector, frames, num_per_plate, name, ground_truth,
        results_folder, discobox_run, count, dead_streak=dead_streak, settings=settings
    )

    # Generate summary reports if this is the final recording
    if count >= num_recordings:
        _generate_summary_reports(plotter, stage)


def _determine_results_base(folder_path, discobox_run, output_folder=None):
    """Determine the base path for results."""
    if output_folder:
        return output_folder
    return folder_path if discobox_run else "outputs"


def _validate_predict_inputs(folder_path, name, num_per_plate):
    """Validate inputs for predict function."""
    if not folder_path:
        raise ValueError("Folder path must be provided")
    
    if not name:
        raise ValueError("Name must be provided")

def predict(folder_path, name, num_per_plate, reanalyze=False, discobox_run=False,
           num_recordings=2, count=2, output_folder=None,
           pause_callback=None, dead_streak=1, enable_text_recognition=True):
    """Main prediction function that orchestrates the analysis process."""
    # Guard clauses
    _validate_predict_inputs(folder_path, name, num_per_plate)

    try:
        detector = get_detector()
        frames = get_frames(folder_path, discobox_run, reanalyze)
        settings = Settings(folder_path)
        # GUI-provided runtime toggle, not something read from .settings.txt:
        # lets users skip the heavy OCR model on underpowered machines and
        # label zones manually instead.
        settings.enable_text_recognition = enable_text_recognition
    except Exception as e:
        raise RuntimeError(f"Failed to initialize detector or load frames: {e}")
    
    # Guard clause for frames - can be either a single stack or list of stacks
    if frames is None:
        raise ValueError("No frames were loaded from the specified folder")
    
    # For reanalyze: frames is a list of stacks, for analyze: frames is a single stack
    if reanalyze and (not isinstance(frames, list) or len(frames) == 0):
        raise ValueError("No frame stacks were loaded for reanalysis")
    elif not reanalyze and len(frames) == 0:
        raise ValueError("No frames were loaded for analysis")
    
    ground_truth = ""  # alive or dead
    results_base = _determine_results_base(folder_path, discobox_run, output_folder)
    
    if reanalyze:
        # For GUI: always pause after recording 1 if we have a callback and more than 1 recording
        should_pause = pause_callback is not None and len(frames) > 1

        reanalyze_recording(results_base, num_per_plate, detector, frames,
                          discobox_run, name, ground_truth, pause_callback, should_pause, dead_streak, settings)
    else:
        analyze_recording(results_base, num_per_plate, detector, frames, discobox_run,
                        name, num_recordings, ground_truth, count, dead_streak, settings)


if __name__ == "__main__":
    # Example usage - this will only run when script is executed directly
    # Uncomment the line below to run a test analysis
    # predict("Datasets/long_run_test_final/", "test", num_per_plate=1, reanalyze=True)
    print("Varroa Detector - Use the GUI application (launch_gui.py) for interactive analysis")