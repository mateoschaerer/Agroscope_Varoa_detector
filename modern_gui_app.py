"""
Modern GUI Application for Varroa Detector with enhanced UI design
Features: Modern styling, drag-and-drop, ZIP downloads
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk, font
import threading
import os
import sys
import subprocess
from pathlib import Path
import time
import zipfile
import shutil
from datetime import datetime
import tempfile
import cv2
import numpy as np
import pickle
from PIL import Image, ImageTk, ImageDraw, ImageFont


# Replace interactive messagebox dialogs with a silent shim that prints to console
# and avoids blocking GUI flow. This removes modal prompts while preserving
# console visibility for debugging.
class _SilentMessageBox:
    def showinfo(self, title, message, **kwargs):
        try:
            print(f"INFO: {title} - {message}")
            # Update status label if available on the main app
            # (we check dynamically where used)
        except Exception:
            pass

    def showwarning(self, title, message, **kwargs):
        try:
            print(f"WARNING: {title} - {message}")
        except Exception:
            pass

    def showerror(self, title, message, **kwargs):
        try:
            print(f"ERROR: {title} - {message}")
        except Exception:
            pass

    def askyesno(self, title, message, **kwargs):
        # Default to True when code expects confirmation; the GUI now auto-loads stages.
        print(f"ASK (auto-yes): {title} - {message}")
        return True


# Shadow the imported messagebox with the silent shim to disable modal prompts
messagebox = _SilentMessageBox()

class SplashScreen:
    """Startup splash screen.

    The logo is drawn with plain Canvas shapes (a small bee bitmap) instead of
    emoji glyphs, so it renders identically everywhere - including minimal
    Linux installs without a color-emoji font, where emoji characters show up
    as empty boxes.
    """

    def __init__(self, duration=1400):
        self.duration = duration
        self._closed = False
        self.splash = tk.Toplevel()
        self.splash.title("")
        self.splash.geometry("520x360")
        self.splash.configure(bg='#2d7d32')
        self.splash.overrideredirect(True)

        # Create splash content first
        self.create_splash_content()

        # Center splash screen after content is created
        self.center_splash()

        # Auto close after duration
        self.splash.after(self.duration, self.close_splash)

        # Make sure splash is on top
        self.splash.lift()
        self.splash.focus_force()

    def center_splash(self):
        # Force window to update and calculate actual size
        self.splash.update_idletasks()
        
        # Get screen dimensions
        screen_width = self.splash.winfo_screenwidth()
        screen_height = self.splash.winfo_screenheight()
        
        # Get window dimensions (use requested size if actual size not ready)
        window_width = self.splash.winfo_reqwidth() if self.splash.winfo_width() <= 1 else self.splash.winfo_width()
        window_height = self.splash.winfo_reqheight() if self.splash.winfo_height() <= 1 else self.splash.winfo_height()
        
        # If still no size, use default
        if window_width <= 1:
            window_width = 520
        if window_height <= 1:
            window_height = 360
        
        # Calculate center position
        x = (screen_width // 2) - (window_width // 2)
        y = (screen_height // 2) - (window_height // 2)
        
        # Ensure window doesn't go off screen
        x = max(0, x)
        y = max(0, y)
        
        self.splash.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        # Force another update to ensure centering takes effect
        self.splash.update_idletasks()
        
    def create_splash_content(self):
        # Main container
        main_frame = tk.Frame(self.splash, bg='#2d7d32')
        main_frame.pack(expand=True, fill='both')

        # Logo: small canvas-drawn bee bitmap (no emoji font required)
        self.logo_canvas = tk.Canvas(
            main_frame, width=120, height=100,
            bg='#2d7d32', highlightthickness=0
        )
        self.logo_canvas.pack(pady=(36, 10))
        self._draw_bee_bitmap(self.logo_canvas, 60, 52)

        # Title
        title_label = tk.Label(
            main_frame,
            text="Varroa Detector",
            font=('Segoe UI', 28, 'bold'),
            fg='#ffc107',
            bg='#2d7d32'
        )
        title_label.pack(pady=(4, 6))

        # Subtitle
        subtitle_label = tk.Label(
            main_frame,
            text="AI-Powered Mite Survival Assessment Tool",
            font=('Segoe UI', 13),
            fg='white',
            bg='#2d7d32'
        )
        subtitle_label.pack(pady=(0, 30))

        # Loading text
        loading_label = tk.Label(
            main_frame,
            text="Loading...",
            font=('Segoe UI', 12),
            fg='white',
            bg='#2d7d32'
        )
        loading_label.pack(pady=(10, 0))

        # Progress bar (decorative, timed to the fixed splash duration - not
        # tied to backend work, so it always fills smoothly)
        progress_frame = tk.Frame(main_frame, bg='#2d7d32')
        progress_frame.pack(pady=20, padx=90, fill='x')

        self.progress_bar = tk.Canvas(
            progress_frame,
            height=6,
            bg='#1b5e20',
            highlightthickness=0
        )
        self.progress_bar.pack(fill='x')

        # Animate on the main thread via .after() - a background thread
        # calling into Tk (the previous approach) is unsafe and would raise
        # "main thread is not in main loop" if the window closes mid-animation.
        self._progress_start = time.monotonic()
        self._animate_progress_step()

    @staticmethod
    def _draw_bee_bitmap(canvas, cx, cy):
        """Draw a small flat-style bee icon from plain shapes."""
        # Wings
        canvas.create_oval(cx - 46, cy - 34, cx - 8, cy - 2, fill='#eafaf1', outline='#a5d6a7')
        canvas.create_oval(cx + 8, cy - 34, cx + 46, cy - 2, fill='#eafaf1', outline='#a5d6a7')
        # Body
        canvas.create_oval(cx - 30, cy - 18, cx + 30, cy + 24, fill='#ffc107', outline='#3e2723', width=2)
        # Stripes
        for dx in (-15, 0, 15):
            canvas.create_rectangle(cx + dx - 4, cy - 18, cx + dx + 4, cy + 24, fill='#3e2723', outline='')
        # Head
        canvas.create_oval(cx - 13, cy - 32, cx + 13, cy - 10, fill='#3e2723', outline='')
        # Antennae
        canvas.create_line(cx - 6, cy - 30, cx - 12, cy - 42, fill='#3e2723', width=2)
        canvas.create_line(cx + 6, cy - 30, cx + 12, cy - 42, fill='#3e2723', width=2)

    def _animate_progress_step(self):
        try:
            if self._closed or not self.progress_bar.winfo_exists():
                return

            elapsed = time.monotonic() - self._progress_start
            fraction = min(1.0, elapsed / max(self.duration / 1000, 0.001))

            width = self.progress_bar.winfo_width()
            self.progress_bar.delete("all")
            self.progress_bar.create_rectangle(
                0, 0, width * fraction, 6,
                fill='#ffc107', outline=''
            )
        except (tk.TclError, RuntimeError):
            return

        if fraction < 1.0 and not self._closed:
            self.splash.after(30, self._animate_progress_step)

    def close_splash(self):
        self._closed = True
        if hasattr(self, 'splash'):
            try:
                self.splash.destroy()
            except (tk.TclError, RuntimeError):
                pass


class ModernVarroaDetectorApp:
    def __init__(self):
        # Main Tk root (prefer TkinterDnD if available so we can enable DnD before building widgets)
        try:
            from tkinterdnd2 import TkinterDnD, DND_FILES  # type: ignore
            self.root = TkinterDnD.Tk()
            self.dnd_available = True
            self.DND_FILES = DND_FILES
            print("[OK] Drag-and-drop support enabled (tkinterdnd2 detected)")
        except Exception:
            self.root = tk.Tk()
            self.dnd_available = False
            self.DND_FILES = None
            print("[INFO] tkinterdnd2 not available at startup - drag-and-drop disabled (click to browse still works)")

        # Set window icon (taskbar + title bar) to app icon when possible
        try:
            icon_path = os.path.join(os.path.dirname(__file__), 'app', 'icons', 'app_icon.ico')
            if not os.path.exists(icon_path):
                # fallbacks
                icon_path = os.path.join(os.path.dirname(__file__), 'app', 'icons', 'honeycomb_logo_transparent.ico')
            if os.path.exists(icon_path):
                try:
                    # Windows .ico preferred
                    self.root.iconbitmap(icon_path)
                except Exception:
                    # Fallback to iconphoto if .ico fails
                    try:
                        img = tk.PhotoImage(file=icon_path)
                        self.root.iconphoto(True, img)
                    except Exception:
                        pass
        except Exception:
            pass

        # Initialize text verification attributes early
        self.analysis_complete_flag = False
        self.zones_locked = False
        self.mite_zones = []
        self.current_hover_zone = None
        self.selected_zone = None  # Currently selected zone for persistent display
        self.zone_coordinates = []
        self.canvas_scale = 1.0
        self.canvas_offset_x = 0
        self.canvas_offset_y = 0
        self.text_verification_active = False
        self.analysis_paused = False
        self.recording1_pause = False
        self.continue_analysis_params = None

        # MiteManager integration and restoration settings
        self.mite_manager = None
        self._original_zone_coordinates = None
        # If True, restore original zone coordinates and remove saved MiteManager on completion
        self.restore_zones_on_completion = True

        # Hide main window initially and show splash
        self.root.withdraw()
        self.splash = SplashScreen(duration=1200)
        self.root.after(1300, self.initialize_main_window)
        
    def initialize_main_window(self):
        """Initialize the main application window after splash screen"""
        self.root.title("Varroa Detector - AI-Powered Mite Analysis")
        self.root.geometry("1000x800")
        self.root.minsize(900, 700)
        
        # Configure modern styling
        self.setup_modern_styles()
        # Load MiteManager stage if available
        mite_manager_path = os.path.join(os.path.dirname(__file__), "classes", "mite_manager.plk")
        if os.path.exists(mite_manager_path):
            from classes.MiteManager import MiteManager
            with open(mite_manager_path, 'rb') as f:
                self.mite_manager = pickle.load(f)
            print(f"[OK] Loaded MiteManager at startup with {len(self.mite_manager.zones)} zones")
        
        # Variables
        self.selected_folder = tk.StringVar()
        self.analysis_name = tk.StringVar(value="analysis_1")
        self.plates_per_recording = tk.StringVar(value="1")
        self.dead_streak = tk.StringVar(value="2")
        self.enable_ocr = tk.BooleanVar(value=False)
        self._ocr_enabled_for_run = True
        self._manual_labels_prompted = False
        self.analysis_running = False
        self.results_path = None
        self.temp_results_dir = None  # Store temp directory path
        self.current_image = None
        self.image_display_label = None
        
        # Track changes to plates_per_recording for zone overlay updates
        self.plates_per_recording.trace('w', self.on_zone_selection_change)
        
        # Create UI elements
        self.setup_ui()
        
        # Center the window after UI is created
        self.center_window()
        
        # Show main window
        self.root.deiconify()
        
        # Ensure centering after window is shown (sometimes needed for proper sizing)
        self.root.after(100, self.center_window)
    
    def setup_modern_styles(self):
        """Configure modern light green visual styling"""
        # Modern light color scheme with green accents
        self.colors = {
            'bg_primary': '#ffffff',       # White background
            'bg_secondary': '#f8fdf8',     # Very light green tint
            'bg_tertiary': '#e8f5e8',      # Light green background
            'accent': '#2d7d32',           # Deep green accent
            'accent_hover': '#388e3c',     # Lighter green hover
            'success': '#4caf50',          # Success green
            'warning': '#ff9800',          # Orange
            'error': '#f44336',            # Red
            'text_primary': '#1b5e20',     # Dark green text
            'text_secondary': '#2e7d32',   # Medium green text
            'text_muted': '#6a7c59',       # Muted green text
            'surface': '#f1f8e9',          # Light green surface
            'gradient_start': '#66bb6a',   # Green gradient start
            'gradient_end': '#81c784',     # Green gradient end
            'bee_yellow': '#ffc107',       # Bee yellow accent
            'honeycomb': '#fff3c4'         # Honeycomb color
        }
        
        # Configure root
        self.root.configure(bg=self.colors['bg_primary'])
        
        # Modern fonts
        self.fonts = {
            'title': ('Segoe UI', 28, 'bold'),
            'heading': ('Segoe UI', 16, 'bold'),
            'subheading': ('Segoe UI', 12, 'bold'),
            'body': ('Segoe UI', 10),
            'small': ('Segoe UI', 9)
        }
        
        # Configure ttk styles for modern look
        style = ttk.Style()
        
        # Configure modern button style with rounded appearance
        style.configure('Modern.TButton',
                       background=self.colors['accent'],
                       foreground='white',
                       borderwidth=0,
                       focuscolor='none',
                       relief='flat',
                       padding=(25, 15))
        
        style.map('Modern.TButton',
                 background=[('active', self.colors['accent_hover']),
                           ('pressed', self.colors['accent'])])
        
        # Configure modern frame style with softer appearance
        style.configure('Card.TFrame',
                       background=self.colors['bg_secondary'],
                       borderwidth=0,
                       relief='flat')
        
        # Configure modern progressbar with rounded look
        style.configure('Modern.Horizontal.TProgressbar',
                       background=self.colors['accent'],
                       troughcolor=self.colors['bg_tertiary'],
                       borderwidth=0,
                       lightcolor=self.colors['accent'],
                       darkcolor=self.colors['accent'],
                       relief='flat')
    
    def center_window(self):
        """Center the window on the screen"""
        # Force window to update and get accurate dimensions
        self.root.update_idletasks()
        
        # Get screen dimensions
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # Get window dimensions
        window_width = self.root.winfo_width()
        window_height = self.root.winfo_height()
        
        # If window size is not yet calculated, use the requested size
        if window_width <= 1:
            window_width = self.root.winfo_reqwidth()
        if window_height <= 1:
            window_height = self.root.winfo_reqheight()
            
        # If still no proper size, use default geometry
        if window_width <= 1 or window_height <= 1:
            window_width = 1000
            window_height = 800
        
        # Calculate center position
        x = (screen_width // 2) - (window_width // 2)
        y = (screen_height // 2) - (window_height // 2)
        
        # Ensure window doesn't go off screen
        x = max(0, min(x, screen_width - window_width))
        y = max(0, min(y, screen_height - window_height))
        
        # Set window position and size
        self.root.geometry(f'{window_width}x{window_height}+{x}+{y}')
        
        # Force another update to ensure positioning takes effect
        self.root.update_idletasks()
    
    def cleanup_previous_results(self):
        """Clean up any previous analysis results at startup when no files are in use"""
        try:
            outputs_dir = os.path.join(os.getcwd(), "outputs")
            if not os.path.exists(outputs_dir):
                return
            
            print("[INFO] Cleaning up previous analysis results...")
            
            # More aggressive cleanup approach
            import subprocess
            import time
            
            # Remove all reanalysis directories
            for item in os.listdir(outputs_dir):
                if item.startswith("reanalysis"):
                    reanalysis_path = os.path.join(outputs_dir, item)
                    if os.path.isdir(reanalysis_path):
                        try:
                            # Try multiple approaches for stubborn folders
                            success = self.force_remove_directory(reanalysis_path)
                            if success:
                                print(f"[OK] Removed: {item}")
                            else:
                                print(f"[WARN] Could not remove {item} - will try alternative approach")
                                # Alternative: try to remove individual files first
                                self.remove_files_recursively(reanalysis_path)
                        except Exception as e:
                            print(f"[WARN] Could not remove {item}: {e}")
            
            # Also clean up the results folder if it exists
            results_path = os.path.join(outputs_dir, "results")
            if os.path.exists(results_path):
                try:
                    success = self.force_remove_directory(results_path)
                    if success:
                        print("[OK] Removed: results folder")
                    else:
                        print("[WARN] Could not remove results folder - trying alternative approach")
                        self.remove_files_recursively(results_path)
                except Exception as e:
                    print(f"[WARN] Could not remove results folder: {e}")
            
            print("[OK] Startup cleanup completed!")
            
        except Exception as e:
            print(f"[WARN] Error during startup cleanup: {e}")
    
    def force_remove_directory(self, directory_path):
        """Force remove a directory using multiple methods"""
        import time
        import subprocess
        
        # Method 1: Try normal removal first
        try:
            # Set all files as writable
            for root, dirs, files in os.walk(directory_path):
                for d in dirs:
                    try:
                        os.chmod(os.path.join(root, d), 0o777)
                    except:
                        pass
                for f in files:
                    try:
                        os.chmod(os.path.join(root, f), 0o777)
                    except:
                        pass
            
            shutil.rmtree(directory_path)
            return True
        except:
            pass
        
        # Method 2: Try Windows rmdir command
        try:
            subprocess.run(['rmdir', '/S', '/Q', directory_path], 
                          shell=True, check=False, 
                          capture_output=True, timeout=10)
            if not os.path.exists(directory_path):
                return True
        except:
            pass
        
        # Method 3: Try PowerShell Remove-Item
        try:
            cmd = f'Remove-Item -Path "{directory_path}" -Recurse -Force -ErrorAction SilentlyContinue'
            subprocess.run(['powershell', '-Command', cmd], 
                          check=False, capture_output=True, timeout=10)
            if not os.path.exists(directory_path):
                return True
        except:
            pass
        
        return False
    
    def remove_files_recursively(self, directory_path):
        """Try to remove individual files when directory removal fails"""
        try:
            for root, dirs, files in os.walk(directory_path, topdown=False):
                # Remove files first
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        os.chmod(file_path, 0o777)
                        os.remove(file_path)
                    except:
                        try:
                            # Try force delete with Windows attrib command
                            subprocess.run(['attrib', '-R', '-S', '-H', file_path], 
                                         shell=True, capture_output=True, timeout=5)
                            os.remove(file_path)
                        except:
                            pass
                
                # Then try to remove directories
                for dir in dirs:
                    dir_path = os.path.join(root, dir)
                    try:
                        os.rmdir(dir_path)
                    except:
                        pass
            
            # Finally try to remove the root directory
            try:
                os.rmdir(directory_path)
            except:
                pass
                
        except Exception as e:
            print(f"Error in file removal: {e}")

    def setup_ui(self):
        """Create and arrange all UI elements with modern design"""
        
        # Create main container with scrolling capability
        main_canvas = tk.Canvas(self.root, bg=self.colors['bg_primary'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=main_canvas.yview)
        scrollable_frame = tk.Frame(main_canvas, bg=self.colors['bg_primary'])
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: main_canvas.configure(scrollregion=main_canvas.bbox("all"))
        )
        
        main_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        main_canvas.configure(yscrollcommand=scrollbar.set)
        
        # Pack canvas and scrollbar
        main_canvas.pack(side="left", fill="both", expand=True, padx=20, pady=20)
        scrollbar.pack(side="right", fill="y")
        
        # Title section
        self.create_title_section(scrollable_frame)
        
        # Drag and drop section
        self.create_drag_drop_section(scrollable_frame)
        
        # Configuration section
        self.create_configuration_section(scrollable_frame)
        
        # Image preview section
        self.create_image_preview_section(scrollable_frame)
        
        # Progress section
        self.create_progress_section(scrollable_frame)
        
        # Action buttons section
        self.create_action_buttons_section(scrollable_frame)
        
        # Results section
        self.create_results_section(scrollable_frame)
        
        # Bind mousewheel to canvas
        def _on_mousewheel(event):
            main_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        main_canvas.bind_all("<MouseWheel>", _on_mousewheel)
        # Enable drag-and-drop functionality
        self.setup_drag_drop()
        
    def create_title_section(self, parent):
        """Create modern title section with gradient effect"""
        title_frame = tk.Frame(parent, bg=self.colors['bg_primary'], height=140)
        title_frame.pack(fill="x", pady=(0, 30))
        title_frame.pack_propagate(False)
        
        # Main title with modern styling
        title_label = tk.Label(
            title_frame,
            text="Varroa Detector",
            font=self.fonts['title'],
            bg=self.colors['bg_primary'],
            fg=self.colors['gradient_end']
        )
        title_label.pack(pady=(15, 5))
        
        # Subtitle with better styling
        subtitle_label = tk.Label(
            title_frame,
            text="AI-powered analysis of bee mite images using advanced YOLO detection",
            font=self.fonts['body'],
            bg=self.colors['bg_primary'],
            fg=self.colors['text_secondary']
        )
        subtitle_label.pack(pady=(0, 8))
        
        # Status indicator
        self.status_label = tk.Label(
            title_frame,
            text="● Ready",
            font=self.fonts['small'],
            bg=self.colors['bg_primary'],
            fg=self.colors['success']
        )
        self.status_label.pack(pady=(0, 5))

    @staticmethod
    def _draw_folder_bitmap(canvas, cx, cy, color):
        """Draw a small flat folder icon from plain shapes (no emoji glyph)."""
        canvas.create_polygon(
            cx - 18, cy - 6,
            cx - 6, cy - 6,
            cx - 2, cy - 10,
            cx + 10, cy - 10,
            cx + 10, cy - 6,
            cx + 18, cy - 6,
            cx + 18, cy + 10,
            cx - 18, cy + 10,
            fill=color, outline=''
        )

    def create_drag_drop_section(self, parent):
        """Create modern drag and drop area"""
        # Card container with softer styling
        card_frame = tk.Frame(parent, bg=self.colors['bg_secondary'], relief='flat', borderwidth=0)
        card_frame.pack(fill="x", pady=(0, 25), padx=15)
        
        # Section header
        header_frame = tk.Frame(card_frame, bg=self.colors['bg_secondary'])
        header_frame.pack(fill="x", padx=20, pady=(20, 10))
        
        title_label = tk.Label(
            header_frame,
            text="Dataset Input",
            font=self.fonts['heading'],
            bg=self.colors['bg_secondary'],
            fg=self.colors['text_primary']
        )
        title_label.pack(anchor="w")
        
        # Drag and drop area
        self.drop_frame = tk.Frame(
            card_frame,
            bg=self.colors['bg_tertiary'],
            relief='ridge',
            borderwidth=2,
            height=120
        )
        self.drop_frame.pack(fill="x", padx=20, pady=(0, 10))
        self.drop_frame.pack_propagate(False)
        
        # Drop area content
        drop_content = tk.Frame(self.drop_frame, bg=self.colors['bg_tertiary'])
        drop_content.place(relx=0.5, rely=0.5, anchor="center")
        
        self.drop_icon = tk.Canvas(
            drop_content, width=40, height=30,
            bg=self.colors['bg_tertiary'], highlightthickness=0
        )
        self.drop_icon.pack()
        self._draw_folder_bitmap(self.drop_icon, 20, 17, self.colors['text_muted'])
        
        self.drop_text = tk.Label(
            drop_content,
            text="Drag & drop folder here or click to browse",
            font=self.fonts['body'],
            bg=self.colors['bg_tertiary'],
            fg=self.colors['text_muted']
        )
        self.drop_text.pack(pady=(5, 0))
        
        # Selected folder display
        self.folder_display = tk.Label(
            card_frame,
            textvariable=self.selected_folder,
            font=self.fonts['small'],
            bg=self.colors['bg_secondary'],
            fg=self.colors['accent'],
            wraplength=800,
            justify="left"
        )
        self.folder_display.pack(fill="x", padx=20, pady=(0, 20))
        
        # Bind click event to browse
        self.drop_frame.bind("<Button-1>", lambda e: self.browse_folder())
        for widget in [drop_content, self.drop_icon, self.drop_text]:
            widget.bind("<Button-1>", lambda e: self.browse_folder())
    
    def setup_drag_drop(self):
        """Register drop target if tkinterdnd2 was available at construction time."""
        if not getattr(self, 'dnd_available', False):
            # Already informed user in __init__
            return
        try:
            # Ensure drop_frame exists
            if not hasattr(self, 'drop_frame'):
                return
            self.drop_frame.drop_target_register(self.DND_FILES)
            self.drop_frame.dnd_bind('<<Drop>>', self.on_drop)
            print("[OK] Drag-and-drop area registered")
        except Exception as e:
            print(f"[WARN] Failed to enable drag-and-drop: {e}")
    
    def on_drop(self, event):
        """Handle drag and drop events"""
        files = event.data.split()
        if files:
            folder_path = files[0].strip('{}')
            if os.path.isdir(folder_path):
                self.selected_folder.set(folder_path)
                self.animate_drop_success()
                self.load_and_display_first_image(folder_path)
            else:
                print("WARNING: Invalid Drop - Please drop a folder, not a file.")
    
    def animate_drop_success(self):
        """Animate successful drop"""
        original_bg = self.drop_frame.cget('bg')
        self.drop_frame.configure(bg=self.colors['success'])
        self.drop_text.configure(text="Folder loaded successfully!", fg=self.colors['text_primary'])
        
        # Reset after animation
        self.root.after(1500, lambda: [
            self.drop_frame.configure(bg=original_bg),
            self.drop_text.configure(text="Drag & drop folder here or click to browse", 
                                   fg=self.colors['text_muted'])
        ])
    
    def on_zone_selection_change(self, *args):
        """Handle changes to zone selection - update image overlay"""
        # Refresh the zone overlay whenever the plates_per_recording selection changes.
        # If a dataset folder is selected, reload the first image from that folder so
        # the overlay matches the chosen coordinate file. Otherwise just refresh the
        # current image if available.
        try:
            if hasattr(self, 'selected_folder') and self.selected_folder.get():
                self.load_and_display_first_image(self.selected_folder.get())
            else:
                # Refresh the currently displayed image (if any)
                self.refresh_zone_display()
        except Exception as e:
            print(f"Warning: Failed to update overlay after zone selection change: {e}")
    
    def refresh_zone_display(self):
        """Refresh the zone display to reflect updated MiteManager data"""
        print("[INFO] Refreshing zone display...")
        try:
            if hasattr(self, 'selected_folder') and self.selected_folder and hasattr(self.selected_folder, 'get'):
                folder_path = self.selected_folder.get()
                if folder_path:
                    print(f"[INFO] Refreshing zones for folder: {folder_path}")
                    self.load_and_display_first_image(folder_path)
                    return
            
            # Alternative: try to refresh the current image if it exists
            if hasattr(self, 'current_pil_image') and self.current_pil_image:
                print("[INFO] Refreshing current image with zone overlay")
                # Convert PIL image to numpy array for zone overlay
                image_array = np.array(self.current_pil_image)
                image_with_zones = self.apply_zone_overlay(image_array)
                self.display_image(image_with_zones)
                return
                
            print("[WARN] Cannot refresh zones - no image loaded or folder selected")
        except Exception as e:
            print(f"[ERROR] Error refreshing zone display: {e}")
    
    def load_and_display_first_image(self, folder_path):
        """Load and display the first image from the dataset with zone overlay"""
        try:
            # Find first image in dataset
            first_image_path = self.find_first_image(folder_path)
            if not first_image_path:
                self.update_image_display_error("No images found in dataset")
                return
            
            # Load image
            image = cv2.imread(first_image_path)
            if image is None:
                self.update_image_display_error("Could not load image")
                return
            
            # Convert to RGB
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
            # Apply zone overlay
            image_with_zones = self.apply_zone_overlay(image_rgb)
            
            # Convert to PIL and display
            try:
                if self._original_zone_coordinates is None and self.zone_coordinates:
                    # Keep a shallow copy of coordinates so we can restore them later
                    self._original_zone_coordinates = list(self.zone_coordinates)
                    print(f"INFO: Captured original coordinate-file zone snapshot ({len(self._original_zone_coordinates)} zones)")
            except Exception:
                pass

            self.display_image(image_with_zones)
            
        except Exception as e:
            self.update_image_display_error(f"Error loading image: {str(e)}")
    
    def find_first_image(self, folder_path):
        """Find the first .bmp image in the dataset folder"""
        try:
            # Look for subfolders first
            subfolders = sorted([
                os.path.join(folder_path, d)
                for d in os.listdir(folder_path)
                if os.path.isdir(os.path.join(folder_path, d))
            ])
            
            search_paths = subfolders if subfolders else [folder_path]
            
            for search_path in search_paths:
                for root, dirs, files in os.walk(search_path):
                    bmp_files = sorted([f for f in files if f.lower().endswith('.bmp')])
                    if bmp_files:
                        return os.path.join(root, bmp_files[0])
            
            return None
            
        except Exception as e:
            print(f"Error finding first image: {e}")
            return None
    
    def apply_zone_overlay(self, image):
        """Apply zone bounding boxes overlay to the image"""
        try:
            # Decide which overlay to use:
            # - Use MiteManager overlay when zones are locked or during text verification/pause
            #   so detected colors and annotations are visible during verification.
            # - Prefer coordinate-file overlay when zones are unlocked so the user can
            #   change plates-per-recording (1/2) and see the zoneing reset.
            use_mite_manager_overlay = False
            if self.mite_manager and hasattr(self.mite_manager, 'zones'):
                # Only use the MiteManager overlay when zones are locked
                # (analysis running / during verification pause). Otherwise prefer
                # coordinate-file overlay so the plates-per-recording selection
                # can be changed and colors reset.
                if self.zones_locked or self.recording1_pause:
                    use_mite_manager_overlay = True

            if use_mite_manager_overlay:
                return self.apply_mite_manager_overlay(image)
            return self.apply_coordinate_file_overlay(image)
                
        except Exception as e:
            print(f"Error applying zone overlay: {e}")
            return image
    
    def apply_mite_manager_overlay(self, image):
        """Apply zone overlay using MiteManager data"""
        # Convert to PIL for drawing
        pil_image = Image.fromarray(image)
        draw = ImageDraw.Draw(pil_image)
        
        # Clear and rebuild zone coordinates from MiteManager
        self.zone_coordinates = []
        
        # Process MiteManager zones
        for zone_idx, mite_zone in enumerate(self.mite_manager.zones):
            # Get zone coordinates
            x1, y1, x2, y2 = mite_zone.x1, mite_zone.y1, mite_zone.x2, mite_zone.y2
            
            # Store zone coordinates for interaction (use zone_idx as class_id)
            self.zone_coordinates.append((zone_idx, x1, y1, x2, y2))
            
            # Get mite count for this zone
            mite_count = len(mite_zone.mites) if hasattr(mite_zone, 'mites') else 0
            
            # Get zone text label first (needed for debug output)
            if hasattr(mite_zone, 'zone_id') and mite_zone.zone_id:
                zone_text = str(mite_zone.zone_id)
            else:
                zone_text = f"zone not loaded"
            
            # Determine colors based on selection state and mite presence
            if self.selected_zone == zone_idx:
                # Selected zone - use bright blue/purple
                outline_color = (255, 100, 255)  # Bright magenta for selected
                line_width = 6
                color_status = f"SELECTED ZONE - {mite_count} mites"
            elif mite_count > 0:
                # Zone has detected mites - always use green to indicate data found
                outline_color = (50, 255, 50)  # Bright green when mites detected
                line_width = 4
                if self.zones_locked:
                    color_status = f"MITES DETECTED (green) - {mite_count} mites - LOCKED"
                else:
                    color_status = f"MITES DETECTED (green) - {mite_count} mites - UNLOCKED"
            elif self.zones_locked:
                # Zone has no mites and is locked - use red
                outline_color = (200, 50, 50)  # Red when locked and no mites
                line_width = 5
                color_status = "NO MITES (red) - LOCKED"
            else:
                # Zone has no mites and is unlocked - use orange
                outline_color = (255, 165, 0)  # Orange when unlocked and no mites
                line_width = 3
                color_status = "NO MITES (orange) - UNLOCKED"
                
            print(f"Zone {zone_idx} ({zone_text}): {color_status}")
                
            # Draw rectangle outline
            draw.rectangle([x1, y1, x2, y2], outline=outline_color, width=line_width)
            
            # Add zone label using actual zone_id from MiteManager
            # Zone text already defined above, just add lock indicator if needed
            if self.zones_locked:
                zone_text += " (locked)"

            # Add visual indicators based on mite detection status
            if mite_count > 0:
                zone_text += f" ({mite_count} mites detected)"
            else:
                zone_text += f" (No mites)"
            
            try:
                # Try to use a font, fallback to default if not available
                font = ImageFont.truetype("arial.ttf", 16)
            except:
                font = ImageFont.load_default()
            
            # Draw text background
            text_bbox = draw.textbbox((x1, y1-25), zone_text, font=font)
            bg_color = outline_color
            draw.rectangle(text_bbox, fill=bg_color)
            draw.text((x1, y1-25), zone_text, fill=(255, 255, 255), font=font)
            
            # Add click indicator if analysis is completed or during recording 1 pause
            if (self.analysis_complete_flag or self.recording1_pause) and not self.zones_locked and mite_count > 0:
                click_text = "Click to verify"
                click_bbox = draw.textbbox((x1, y2+5), click_text, font=font)
                draw.rectangle(click_bbox, fill=(100, 100, 255))
                draw.text((x1, y2+5), click_text, fill=(255, 255, 255), font=font)
        
        return np.array(pil_image)
    
    def apply_coordinate_file_overlay(self, image):
        """Apply zone overlay using coordinate files (fallback method)"""
        num_zones = int(self.plates_per_recording.get())
        coordinates_file = f"Zoning/coordinates{num_zones}.txt"
        
        if not os.path.exists(coordinates_file):
            return image
        
        # Convert to PIL for drawing
        pil_image = Image.fromarray(image)
        draw = ImageDraw.Draw(pil_image)
        
        # Read zone coordinates and store for interaction
        self.zone_coordinates = []
        with open(coordinates_file, 'r') as f:
            lines = f.readlines()
        
        # Define colors for different zone types
        colors = {
            0: (255, 100, 100, 128),  # Red with transparency for class 0
            1: (100, 255, 100, 128)   # Green with transparency for class 1
        }
        
        # Draw each zone
        for zone_idx, line in enumerate(lines):
            parts = line.strip().split()
            if len(parts) >= 5:
                class_id = int(parts[0])
                x1, y1, x2, y2 = map(float, parts[1:5])
                
                # Convert coordinates to integers
                x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                
                # Store zone coordinates for interaction
                self.zone_coordinates.append((class_id, x1, y1, x2, y2))
                
                # Get color for this class, considering selection state
                if self.selected_zone is not None and zone_idx == self.selected_zone:
                    # This zone is selected
                    outline_color = (255, 100, 255)  # Bright magenta for selected
                    line_width = 6
                elif self.zones_locked:
                    outline_color = (200, 50, 50)  # Red when locked
                    line_width = 5
                else:
                    outline_color = colors.get(class_id, (100, 100, 255, 128))[:3]
                    line_width = 3
                
                draw.rectangle([x1, y1, x2, y2], outline=outline_color, width=line_width)
                
                # Add zone label with lock indicator
                zone_text = f"Zone {class_id}"
                if self.zones_locked:
                    zone_text += " (locked)"
                
                try:
                    # Try to use a font, fallback to default if not available
                    font = ImageFont.truetype("arial.ttf", 16)
                except:
                    font = ImageFont.load_default()
                
                # Draw text background
                text_bbox = draw.textbbox((x1, y1-25), zone_text, font=font)
                bg_color = outline_color
                draw.rectangle(text_bbox, fill=bg_color)
                draw.text((x1, y1-25), zone_text, fill=(255, 255, 255), font=font)
                
                # Add click indicator if analysis is completed or during recording 1 pause
                if (self.analysis_complete_flag or self.recording1_pause) and not self.zones_locked:
                    click_text = "Click to verify"
                    click_bbox = draw.textbbox((x1, y2+5), click_text, font=font)
                    draw.rectangle(click_bbox, fill=(100, 100, 255))
                    draw.text((x1, y2+5), click_text, fill=(255, 255, 255), font=font)
        
        return np.array(pil_image)
    
    def display_image(self, image_array):
        """Display the image in the GUI canvas"""
        try:
            # Hide fallback label if showing
            self.image_display_label.pack_forget()
            
            # Convert to PIL
            pil_image = Image.fromarray(image_array)
            
            # Calculate display size (maintain aspect ratio, max 400x300 for left panel)
            max_width, max_height = 400, 300
            img_width, img_height = pil_image.size
            
            # Calculate scaling factor
            scale_w = max_width / img_width
            scale_h = max_height / img_height
            self.canvas_scale = min(scale_w, scale_h)
            
            # Resize image
            new_width = int(img_width * self.canvas_scale)
            new_height = int(img_height * self.canvas_scale)
            pil_image_resized = pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Configure canvas size
            self.image_canvas.configure(width=new_width, height=new_height)
            
            # Calculate centering offsets
            canvas_width = self.image_canvas.winfo_reqwidth()
            canvas_height = self.image_canvas.winfo_reqheight()
            self.canvas_offset_x = max(0, (canvas_width - new_width) // 2)
            self.canvas_offset_y = max(0, (canvas_height - new_height) // 2)
            
            # Convert to PhotoImage
            photo = ImageTk.PhotoImage(pil_image_resized)
            
            # Clear canvas and add image
            self.image_canvas.delete("all")
            self.image_canvas.create_image(
                self.canvas_offset_x, self.canvas_offset_y, 
                anchor="nw", image=photo
            )
            
            # Store reference to prevent garbage collection
            self.image_canvas.photo = photo
            
        except Exception as e:
            self.update_image_display_error(f"Error displaying image: {str(e)}")
    
    def update_image_display_error(self, error_message):
        """Update image display with error message"""
        # Show fallback label with error
        self.image_display_label.pack(expand=True, pady=50)
        self.image_display_label.configure(
            image='',
            text=f"{error_message}",
            font=self.fonts['body'],
            fg=self.colors['error']
        )
        if hasattr(self.image_display_label, 'image'):
            self.image_display_label.image = None
        
        # Clear canvas
        if hasattr(self, 'image_canvas'):
            self.image_canvas.delete("all")
    
    def create_configuration_section(self, parent):
        """Create modern configuration section"""
        card_frame = tk.Frame(parent, bg=self.colors['bg_secondary'], relief='flat', borderwidth=0)
        card_frame.pack(fill="x", pady=(0, 25), padx=15)
        
        # Header
        header_frame = tk.Frame(card_frame, bg=self.colors['bg_secondary'])
        header_frame.pack(fill="x", padx=20, pady=(20, 15))
        
        title_label = tk.Label(
            header_frame,
            text="Analysis Configuration",
            font=self.fonts['heading'],
            bg=self.colors['bg_secondary'],
            fg=self.colors['text_primary']
        )
        title_label.pack(anchor="w")
        
        # Subtitle for reanalysis mode
        subtitle_label = tk.Label(
            header_frame,
            text="Running in Reanalysis Mode",
            font=self.fonts['small'],
            bg=self.colors['bg_secondary'],
            fg=self.colors['accent']
        )
        subtitle_label.pack(anchor="w", pady=(5, 0))
        
        # Configuration grid
        config_frame = tk.Frame(card_frame, bg=self.colors['bg_secondary'])
        config_frame.pack(fill="x", padx=20, pady=(0, 20))
        
        # Grid setup with modern entries
        configs = [
            ("Analysis Name:", self.analysis_name, "entry"),
            ("sample rows per plate:", self.plates_per_recording, "combo", ["1", "2"]),
            ("Dead Streak (frames):", self.dead_streak, "entry"),
            ("Automatic Text Recognition (OCR):", self.enable_ocr, "checkbox")
        ]
        
        for i, config in enumerate(configs):
            label_text, variable, widget_type = config[:3]
            
            # Label
            label = tk.Label(
                config_frame,
                text=label_text,
                font=self.fonts['body'],
                bg=self.colors['bg_secondary'],
                fg=self.colors['text_secondary'],
                anchor="w"
            )
            label.grid(row=i, column=0, sticky="w", pady=8, padx=(0, 20))
            
            # Widget
            if widget_type == "entry":
                widget = tk.Entry(
                    config_frame,
                    textvariable=variable,
                    font=self.fonts['body'],
                    bg=self.colors['surface'],
                    fg=self.colors['text_primary'],
                    relief='flat',
                    borderwidth=0,
                    width=30,
                    insertbackground=self.colors['text_primary']
                )
                widget.grid(row=i, column=1, sticky="ew", pady=10, padx=(15, 0), ipady=10)
            
            elif widget_type == "combo":
                values = config[3]
                widget = ttk.Combobox(
                    config_frame,
                    textvariable=variable,
                    values=values,
                    state="readonly",
                    width=28,
                    font=self.fonts['body']
                )
                widget.grid(row=i, column=1, sticky="ew", pady=8, ipady=6)
                
                # Store reference to plates combobox for zone locking
                if variable == self.plates_per_recording:
                    self.plates_combobox = widget

            elif widget_type == "checkbox":
                widget = tk.Checkbutton(
                    config_frame,
                    variable=variable,
                    text="Disable if analysis crashes on a slow/low-memory computer\n(zone labels are then entered manually)",
                    justify="left",
                    font=self.fonts['small'],
                    bg=self.colors['bg_secondary'],
                    fg=self.colors['text_secondary'],
                    activebackground=self.colors['bg_secondary'],
                    selectcolor=self.colors['surface'],
                    anchor="w"
                )
                widget.grid(row=i, column=1, sticky="w", pady=8, padx=(15, 0))

        # Configure grid weights
        config_frame.columnconfigure(1, weight=1)
    
    def create_image_preview_section(self, parent):
        """Create image preview section with zone overlay and text verification"""
        card_frame = tk.Frame(parent, bg=self.colors['bg_secondary'], relief='flat', borderwidth=0)
        card_frame.pack(fill="x", pady=(0, 25), padx=15)
        
        # Header
        header_frame = tk.Frame(card_frame, bg=self.colors['bg_secondary'])
        header_frame.pack(fill="x", padx=20, pady=(20, 10))
        
        title_label = tk.Label(
            header_frame,
            text="Image Preview with Zone Overlay",
            font=self.fonts['heading'],
            bg=self.colors['bg_secondary'],
            fg=self.colors['text_primary']
        )
        title_label.pack(anchor="w")
        
        subtitle_label = tk.Label(
            header_frame,
            text="Preview of the first image with zone boundaries. Click zones to verify text during analysis pause or after completion.",
            font=self.fonts['small'],
            bg=self.colors['bg_secondary'],
            fg=self.colors['text_secondary']
        )
        subtitle_label.pack(anchor="w", pady=(5, 0))
        
        # Main content frame with image and info panel
        content_frame = tk.Frame(card_frame, bg=self.colors['bg_secondary'])
        content_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        # Left side: Image display
        left_frame = tk.Frame(content_frame, bg=self.colors['bg_secondary'])
        left_frame.pack(side="left", fill="both", expand=True)
        
        # Create a scrollable canvas for the image
        canvas_frame = tk.Frame(left_frame, bg=self.colors['surface'], relief='flat', bd=1)
        canvas_frame.pack(fill="both", expand=True, pady=10)
        
        # Create canvas for interactive image
        self.image_canvas = tk.Canvas(
            canvas_frame,
            bg=self.colors['surface'],
            highlightthickness=0
        )
        self.image_canvas.pack(fill="both", expand=True)
        
        # Bind canvas events for text verification
        self.image_canvas.bind("<Motion>", self.on_image_hover)
        self.image_canvas.bind("<Button-1>", self.on_image_click)
        self.image_canvas.bind("<Leave>", self.on_image_leave)
        
        # Fallback image display label
        self.image_display_label = tk.Label(
            canvas_frame,
            text="Select a dataset folder to see the first image with zone overlay",
            font=self.fonts['body'],
            bg=self.colors['surface'],
            fg=self.colors['text_muted'],
            wraplength=400,
            justify='center'
        )
        self.image_display_label.pack(expand=True, pady=50)
        
        # Right side: Zone info panel
        self.create_zone_info_panel(content_frame)
        
        # Initialize text verification state
        self.analysis_complete_flag = False
        self.zones_locked = False
        self.mite_zones = []  # Will store detected mite zones with text
        self.current_hover_zone = None
        self.zone_coordinates = []  # Zone boundary coordinates
        self.canvas_scale = 1.0
        self.canvas_offset_x = 0
        self.canvas_offset_y = 0
    
    def create_zone_info_panel(self, parent):
        """Create the zone information panel on the right side"""
        # Right side: Zone info panel
        right_frame = tk.Frame(parent, bg=self.colors['bg_tertiary'], relief='flat', bd=1)
        right_frame.pack(side="right", fill="y", padx=(15, 0))
        right_frame.configure(width=300)
        right_frame.pack_propagate(False)
        
        # Panel header
        panel_header = tk.Label(
            right_frame,
            text="Zone Information",
            font=self.fonts['subheading'],
            bg=self.colors['bg_tertiary'],
            fg=self.colors['text_primary']
        )
        panel_header.pack(pady=(15, 10))
        
        # Zone status indicator
        self.zone_status_frame = tk.Frame(right_frame, bg=self.colors['bg_tertiary'])
        self.zone_status_frame.pack(fill="x", padx=10, pady=(0, 15))
        
        self.zone_lock_status = tk.Label(
            self.zone_status_frame,
            text="Zones Unlocked",
            font=self.fonts['small'],
            bg=self.colors['bg_tertiary'],
            fg=self.colors['warning']
        )
        self.zone_lock_status.pack()
        
        # Current hover info
        hover_frame = tk.Frame(right_frame, bg=self.colors['surface'], relief='flat', bd=1)
        hover_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        tk.Label(
            hover_frame,
            text="Current Zone:",
            font=self.fonts['small'],
            bg=self.colors['surface'],
            fg=self.colors['text_secondary']
        ).pack(pady=(10, 5))
        
        self.hover_zone_info = tk.Label(
            hover_frame,
            text="Hover over a zone to see details",
            font=self.fonts['body'],
            bg=self.colors['surface'],
            fg=self.colors['text_muted'],
            wraplength=250,
            justify='center'
        )
        self.hover_zone_info.pack(pady=(0, 10))
        
    # (Removed) Mite results and text verification UI blocks
    
    def on_image_hover(self, event):
        """Handle mouse hover over the image canvas"""
        if not self.zone_coordinates:
            return
            
        # Get mouse coordinates relative to the image
        canvas_x = self.image_canvas.canvasx(event.x)
        canvas_y = self.image_canvas.canvasy(event.y)
        
        # Convert canvas coordinates to image coordinates
        img_x = int((canvas_x - self.canvas_offset_x) / self.canvas_scale)
        img_y = int((canvas_y - self.canvas_offset_y) / self.canvas_scale)
        
        # Check which zone we're hovering over
        hovered_zone = self.get_zone_at_point(img_x, img_y)
        
        # Only update hover info if no zone is currently selected
        if self.selected_zone is None and hovered_zone != self.current_hover_zone:
            self.current_hover_zone = hovered_zone
            self.update_hover_info(hovered_zone)
            
        # Change cursor if over a clickable zone (after analysis or during recording 1 pause)
        if (self.analysis_complete_flag or self.recording1_pause) and hovered_zone is not None:
            self.image_canvas.configure(cursor="hand2")
        else:
            self.image_canvas.configure(cursor="")
    
    def on_image_click(self, event):
        """Handle mouse click on the image canvas"""
        # Allow zone clicking if analysis is complete OR if we're in recording 1 pause
        if not (self.analysis_complete_flag or self.recording1_pause) or not self.zone_coordinates:
            return
            
        # Get mouse coordinates relative to the image
        canvas_x = self.image_canvas.canvasx(event.x)
        canvas_y = self.image_canvas.canvasy(event.y)
        
        # Convert canvas coordinates to image coordinates
        img_x = int((canvas_x - self.canvas_offset_x) / self.canvas_scale)
        img_y = int((canvas_y - self.canvas_offset_y) / self.canvas_scale)
        
        # Check which zone was clicked
        clicked_zone = self.get_zone_at_point(img_x, img_y)
        
        if clicked_zone is not None:
            # Toggle zone selection
            if self.selected_zone == clicked_zone:
                # Deselect if already selected
                self.selected_zone = None
                self.update_zone_info_display(None)
            else:
                # Select the zone
                self.selected_zone = clicked_zone
                self.update_zone_info_display(clicked_zone)
                # Enable text verification mode
                self.text_verification_active = True
                self.update_verify_button_state()
            
            # Refresh display to show selection visually - use immediate update
            print(f"[INFO] Zone {clicked_zone + 1} {'deselected' if self.selected_zone is None else 'selected'}")
            self.root.after_idle(self.refresh_zone_display)  # Use after_idle for immediate update
        else:
            # Clicked outside any zone - deselect
            self.selected_zone = None
            self.text_verification_active = False
            self.update_zone_info_display(None)
            self.update_verify_button_state()
            # Refresh display to remove selection - use immediate update
            self.root.after_idle(self.refresh_zone_display)
    
    def on_image_leave(self, event):
        """Handle mouse leaving the image canvas"""
        self.current_hover_zone = None
        self.update_hover_info(None)
        self.image_canvas.configure(cursor="")
    
    def get_zone_at_point(self, x, y):
        """Get the zone index at the given point coordinates using MiteManager zones"""
        # Try to use MiteManager zones first (more accurate)
        if hasattr(self, 'mite_manager') and self.mite_manager and hasattr(self.mite_manager, 'zones'):
            for i, zone in enumerate(self.mite_manager.zones):
                # Check if point is inside the zone using coordinate bounds
                if zone.x1 <= x <= zone.x2 and zone.y1 <= y <= zone.y2:
                    return i
            return None
        
        # Fallback to zone_coordinates if MiteManager not available
        for i, (zone_class, x1, y1, x2, y2) in enumerate(self.zone_coordinates):
            if x1 <= x <= x2 and y1 <= y <= y2:
                return i
        return None
    
    def update_hover_info(self, zone_index):
        """Update the hover information panel using MiteManager data"""
        if zone_index is None:
            self.hover_zone_info.configure(
                text="Hover over a zone to see details",
                fg=self.colors['text_muted']
            )
            return
            
        # Use MiteManager data if available (prioritize this)
        if hasattr(self, 'mite_manager') and self.mite_manager and hasattr(self.mite_manager, 'zones'):
            if zone_index < len(self.mite_manager.zones):
                zone = self.mite_manager.zones[zone_index]
                
                # Get zone ID and mite count
                zone_id = getattr(zone, 'zone_id', f'Zone {zone_index + 1}')
                mite_count = len(zone.mites) if hasattr(zone, 'mites') else 0
                
                # Display zone info
                zone_info = f"{zone_id}\nMites: {mite_count}"
                
                # Add click hint if there are mites
                if mite_count > 0:
                    zone_info += "\n\nClick to verify text"
                
                self.hover_zone_info.configure(
                    text=zone_info,
                    fg=self.colors['text_primary']
                )
                
                print(f"Debug: MiteManager zone {zone_index}: ID='{zone_id}', mites={mite_count}")
                return
        
        # Fallback to zone_coordinates if MiteManager not available
        if zone_index < len(self.zone_coordinates):
            # Get zone info from mite_zones data
            zone_mites = [mite for mite in self.mite_zones if mite.get('zone_id') == zone_index]
            mite_count = len(zone_mites)
            zone_label = f"Zone not loaded"
            
            # Try to get zone label from first mite in the zone
            if zone_mites:
                zone_label = zone_mites[0].get('zone_label', f"Zone {zone_index + 1}")
            
            zone_info = f"{zone_label}\nMites: {mite_count}"
            
            if mite_count > 0:
                zone_info += "\n\nClick to verify text"
            
            self.hover_zone_info.configure(
                text=zone_info,
                fg=self.colors['text_primary']
            )
            
            print(f"Debug: Fallback zone {zone_index}: label='{zone_label}', mites={mite_count}")
    
    def update_zone_info_display(self, zone_index):
        """Update the zone information display for selected zone with text editing capability"""
        if zone_index is None:
            # Clear the display and show default hover text
            self.hover_zone_info.configure(
                text="Hover over a zone to see details",
                fg=self.colors['text_muted']
            )
            # Clear any text editing widgets if they exist
            if hasattr(self, 'zone_text_editor_frame'):
                self.zone_text_editor_frame.destroy()
                delattr(self, 'zone_text_editor_frame')
            return
        
        # Get zone data
        zone_data = self.get_zone_data(zone_index)
        if not zone_data:
            return
        
        # Display persistent zone info
        zone_info = f"SELECTED: {zone_data['zone_label']}\nMites: {zone_data['mite_count']}"
        if zone_data['detected_text']:
            zone_info += f"\nDetected: {zone_data['detected_text']}"
        zone_info += "\n\nClick zone again to deselect"
        
        self.hover_zone_info.configure(
            text=zone_info,
            fg=self.colors['accent']
        )
        
        # Create text editor if it doesn't exist
        self.create_zone_text_editor(zone_index, zone_data)
    
    def get_zone_data(self, zone_index):
        """Get comprehensive zone data for display and editing"""
        zone_data = {
            'zone_label': f'Zone {zone_index + 1}',
            'mite_count': 0,
            'detected_text': '',
            'zone_id': zone_index
        }
        
        # Use MiteManager data if available
        if hasattr(self, 'mite_manager') and self.mite_manager and hasattr(self.mite_manager, 'zones'):
            if zone_index < len(self.mite_manager.zones):
                zone = self.mite_manager.zones[zone_index]
                
                zone_data['zone_label'] = getattr(zone, 'zone_id', f'Zone {zone_index + 1}')
                zone_data['mite_count'] = len(zone.mites) if hasattr(zone, 'mites') else 0
                
                # Get detected text from text zones
                if hasattr(zone, 'text_zones') and zone.text_zones:
                    for text_zone in zone.text_zones:
                        if hasattr(text_zone, 'text') and text_zone.text:
                            zone_data['detected_text'] = text_zone.text
                            break
                
                return zone_data
        
        # Fallback to mite_zones data
        zone_mites = [mite for mite in self.mite_zones if mite.get('zone_id') == zone_index]
        zone_data['mite_count'] = len(zone_mites)
        
        if zone_mites:
            zone_data['zone_label'] = zone_mites[0].get('zone_label', f'Zone {zone_index + 1}')
            zone_data['detected_text'] = zone_mites[0].get('detected_text', '')
        
        return zone_data
    
    def create_zone_text_editor(self, zone_index, zone_data):
        """Create inline text editor for the selected zone"""
        # Remove existing editor if any
        if hasattr(self, 'zone_text_editor_frame'):
            self.zone_text_editor_frame.destroy()
        
        # Find the parent frame for the zone info (should be right_frame)
        parent = self.hover_zone_info.master
        
        # Create editor frame
        self.zone_text_editor_frame = tk.Frame(parent, bg=self.colors['surface'], relief='flat', bd=1)
        self.zone_text_editor_frame.pack(fill="x", padx=10, pady=(10, 0))
        
        # Editor title
        editor_title = tk.Label(
            self.zone_text_editor_frame,
            text="Edit Zone ID:",
            font=self.fonts['small'],
            bg=self.colors['surface'],
            fg=self.colors['text_secondary']
        )
        editor_title.pack(anchor="w", padx=10, pady=(10, 5))
        
        # Text input
        self.zone_text_entry = tk.Entry(
            self.zone_text_editor_frame,
            font=self.fonts['body'],
            bg=self.colors['bg_primary'],
            fg=self.colors['text_primary'],
            relief='flat',
            bd=1
        )
        self.zone_text_entry.pack(fill="x", padx=10, pady=(0, 5))
        
        # Set current text
        current_text = zone_data.get('detected_text', zone_data['zone_label'])
        self.zone_text_entry.delete(0, tk.END)
        self.zone_text_entry.insert(0, current_text)
        
        # Update button
        update_button = tk.Button(
            self.zone_text_editor_frame,
            text="Update Zone ID",
            font=self.fonts['small'],
            bg=self.colors['success'],
            fg='white',
            relief='flat',
            pady=5,
            command=lambda: self.update_zone_text(zone_index)
        )
        update_button.pack(fill="x", padx=10, pady=(0, 10))
    
    def update_zone_text(self, zone_index):
        """Update the zone text/ID with the entered value"""
        if not hasattr(self, 'zone_text_entry'):
            return
        
        new_text = self.zone_text_entry.get().strip()
        if not new_text:
            print("WARNING: Invalid Input - Zone ID cannot be empty")
            return
        
        # Update MiteManager zones if available
        if hasattr(self, 'mite_manager') and self.mite_manager and hasattr(self.mite_manager, 'zones'):
            if zone_index < len(self.mite_manager.zones):
                zone = self.mite_manager.zones[zone_index]
                
                # Update zone ID
                if hasattr(zone, 'zone_id'):
                    zone.zone_id = new_text
                
                # Update text zones
                if hasattr(zone, 'text_zones') and zone.text_zones:
                    for text_zone in zone.text_zones:
                        if hasattr(text_zone, 'text'):
                            text_zone.text = new_text
                else:
                    # Create text zone if it doesn't exist (simplified)
                    print(f"Creating new text zone for zone {zone_index} with text: {new_text}")

                # Persist the updated MiteManager immediately so zone_id changes are not lost
                try:
                    if hasattr(self, 'mite_manager') and self.mite_manager:
                        self.mite_manager.save()
                        print(f"[OK] Persisted MiteManager after updating zone {zone_index}")
                except Exception as e:
                    print(f"Warning: Could not persist MiteManager after zone update: {e}")
        
        # Update mite_zones data as fallback
        zone_mites = [mite for mite in self.mite_zones if mite.get('zone_id') == zone_index]
        for mite in zone_mites:
            mite['detected_text'] = new_text
            mite['zone_label'] = new_text
            mite['text_verified'] = True
        
        # Refresh display
        self.update_zone_info_display(zone_index)
        self.root.after_idle(self.refresh_zone_display)  # Use immediate refresh
        
        print(f"[OK] Zone ID updated to: {new_text}")  # Print instead of popup
    
    def update_verify_button_state(self):
        """Update the state of verification buttons based on current conditions"""
        # Text verification UI removed; ensure any external callers won't fail
        # If widgets exist, update them safely; otherwise do nothing
        if hasattr(self, 'verify_button') or hasattr(self, 'verify_all_button'):
            try:
                if (self.analysis_complete_flag or self.recording1_pause) and self.zone_coordinates:
                    if hasattr(self, 'verify_button'):
                        try:
                            self.verify_button.configure(text="Click Zone to Edit Text", bg=self.colors['accent'])
                        except Exception:
                            pass
                    if hasattr(self, 'verify_all_button'):
                        try:
                            self.verify_all_button.configure(bg=self.colors['warning'] if not self.analysis_paused else self.colors['success'])
                        except Exception:
                            pass
                else:
                    if hasattr(self, 'verify_button'):
                        try:
                            self.verify_button.configure(text="Click Zone to Edit Text", bg=self.colors['text_muted'])
                        except Exception:
                            pass
                    if hasattr(self, 'verify_all_button'):
                        try:
                            self.verify_all_button.configure(bg=self.colors['text_muted'])
                        except Exception:
                            pass
            except Exception:
                pass
    
    def start_text_verification_mode(self):
        """Start or end text verification mode"""
        if self.recording1_pause:
            # During recording 1 pause, this button should do nothing special
            # The verification is already active due to the pause
            print("INFO: Text verification is already active during recording 1 pause. Click on zones to edit their IDs. Use 'Continue Analysis' to proceed.")
            return
            
        if not self.analysis_paused:
            # Start verification mode - pause analysis
            self.analysis_paused = True
            self.text_verification_active = True
            # No UI action required (UI removed)
            print("INFO: Analysis paused for text verification (UI removed).")
        else:
            # End verification mode
            self.end_text_verification_mode()
    
    def end_text_verification_mode(self):
        """End text verification mode and resume analysis"""
        if self.recording1_pause:
            # During recording 1 pause, don't end verification mode
            # User should use the Continue Analysis button instead
            print("INFO: During recording 1 pause, please use the 'Continue Analysis' button to proceed.")
            return
            
        self.analysis_paused = False
        self.text_verification_active = False
        
        # Deselect any selected zone
        self.selected_zone = None
        self.update_zone_info_display(None)
        
    # No UI updates required (verification UI removed)
        
    # Show confirmation
    print("INFO: Verification complete. Analysis resumed.")
    
    # Text verification dialog and save methods removed
    
    def update_mite_list_display(self):
        """Update the mite list display in the zone info panel"""
        if not hasattr(self, 'mite_listbox'):
            return
            
        self.mite_listbox.delete(0, tk.END)
        
        if not self.mite_zones:
            self.mite_listbox.insert(0, "No analysis results yet")
            return
        
        for mite in self.mite_zones:
            status_icon = "[verified]" if mite.get('text_verified', False) else "[pending]"
            status = mite.get('status', 'unknown')
            zone_id = mite.get('zone_id', 'N/A')
            mite_id = mite.get('mite_id', 'unknown')

            display_text = f"{status_icon} {mite_id} (Zone {zone_id + 1}) - {status}"
            self.mite_listbox.insert(tk.END, display_text)
    
    def create_progress_section(self, parent):
        """Create the analysis status section.

        Earlier versions drove a determinate progress bar from a handful of
        hardcoded percentages (10/20/40/80/100). Since most of that range is
        spent inside a single opaque backend call, the bar would jump once
        then sit still for the bulk of the run - reading as stuck rather than
        working. A plain status message plus an indeterminate busy bar (only
        animates while work is actually happening, makes no completion claim)
        is a more honest and much less janky substitute.
        """
        card_frame = tk.Frame(parent, bg=self.colors['bg_secondary'], relief='flat', borderwidth=0)
        card_frame.pack(fill="x", pady=(0, 25), padx=15)

        # Header
        header_frame = tk.Frame(card_frame, bg=self.colors['bg_secondary'])
        header_frame.pack(fill="x", padx=20, pady=(20, 15))

        title_label = tk.Label(
            header_frame,
            text="Analysis Status",
            font=self.fonts['heading'],
            bg=self.colors['bg_secondary'],
            fg=self.colors['text_primary']
        )
        title_label.pack(anchor="w")

        # Status content
        progress_content = tk.Frame(card_frame, bg=self.colors['bg_secondary'])
        progress_content.pack(fill="x", padx=20, pady=(0, 20))

        # Status label
        self.progress_label = tk.Label(
            progress_content,
            text="Ready to start analysis",
            font=self.fonts['body'],
            bg=self.colors['bg_secondary'],
            fg=self.colors['text_secondary']
        )
        self.progress_label.pack(pady=(0, 15))

        # Busy indicator: animates only while work is in progress, makes no
        # claim about how much is left.
        self.progress_bar = ttk.Progressbar(
            progress_content,
            mode='indeterminate',
            length=600,
            style='Modern.Horizontal.TProgressbar'
        )
        self.progress_bar.pack()

    def start_busy_indicator(self, message: str = "Running analysis..."):
        """Show the busy indicator is animating and update the status message."""
        if hasattr(self, 'progress_label'):
            try:
                self.progress_label.configure(text=message, fg=self.colors.get('text_primary', 'black'))
            except Exception:
                pass
        if hasattr(self, 'progress_bar'):
            try:
                self.progress_bar.start(12)
            except Exception:
                pass

    def stop_busy_indicator(self, final_message: str = "Analysis complete", color: str = None):
        """Stop the busy indicator and show a final status message."""
        if hasattr(self, 'progress_bar'):
            try:
                self.progress_bar.stop()
            except Exception:
                pass
        if hasattr(self, 'progress_label'):
            try:
                self.progress_label.configure(text=final_message, fg=color or self.colors.get('success', 'green'))
            except Exception:
                pass


    def create_action_buttons_section(self, parent):
        """Create modern action buttons"""
        button_frame = tk.Frame(parent, bg=self.colors['bg_primary'])
        button_frame.pack(fill="x", pady=(10, 30), padx=20)
        
        # Start button with more rounded appearance
        self.start_button = tk.Button(
            button_frame,
            text="Start Analysis",
            font=self.fonts['subheading'],
            bg=self.colors['success'],
            fg='white',
            relief='flat',
            padx=45,
            pady=18,
            command=self.start_analysis,
            cursor='hand2',
            bd=0
        )
        self.start_button.pack(side="left", expand=True, fill="x", padx=(0, 15))
        
        # Stop button with softer styling
        self.stop_button = tk.Button(
            button_frame,
            text="Stop",
            font=self.fonts['subheading'],
            bg=self.colors['error'],
            fg='white',
            relief='flat',
            padx=45,
            pady=18,
            command=self.stop_analysis,
            state="disabled",
            cursor='hand2',
            bd=0
        )
        self.stop_button.pack(side="right", padx=(15, 0))
        
        # Button hover effects
        self.add_hover_effect(self.start_button, self.colors['success'], '#8cc85d')
        self.add_hover_effect(self.stop_button, self.colors['error'], '#e64553')
    
    def add_hover_effect(self, button, normal_color, hover_color):
        """Add hover effect to button"""
        def on_enter(e):
            if button['state'] != 'disabled':
                button.configure(bg=hover_color)
        
        def on_leave(e):
            if button['state'] != 'disabled':
                button.configure(bg=normal_color)
        
        button.bind("<Enter>", on_enter)
        button.bind("<Leave>", on_leave)
    
    def create_results_section(self, parent):
        """Create modern results section"""
        card_frame = tk.Frame(parent, bg=self.colors['bg_secondary'], relief='flat', borderwidth=0)
        card_frame.pack(fill="x", pady=(0, 25), padx=15)
        
        # Header
        header_frame = tk.Frame(card_frame, bg=self.colors['bg_secondary'])
        header_frame.pack(fill="x", padx=20, pady=(20, 15))
        
        title_label = tk.Label(
            header_frame,
            text="Results & Download",
            font=self.fonts['heading'],
            bg=self.colors['bg_secondary'],
            fg=self.colors['text_primary']
        )
        title_label.pack(anchor="w")
        
        # Results content
        results_content = tk.Frame(card_frame, bg=self.colors['bg_secondary'])
        results_content.pack(fill="x", padx=20, pady=(0, 20))
        
        # Results info
        self.results_info = tk.Label(
            results_content,
            text="No analysis completed yet",
            font=self.fonts['body'],
            bg=self.colors['bg_secondary'],
            fg=self.colors['text_muted']
        )
        self.results_info.pack(pady=(0, 15))
        
        # Buttons frame
        buttons_frame = tk.Frame(results_content, bg=self.colors['bg_secondary'])
        buttons_frame.pack(fill="x")
        
        # Download ZIP button (centered)
        self.download_button = tk.Button(
            buttons_frame,
            text="Download Results",
            font=self.fonts['body'],
            bg=self.colors['warning'],
            fg='white',
            relief='flat',
            padx=20,
            pady=10,
            command=self.download_results_zip,
            state="disabled",
            cursor='hand2'
        )
        self.download_button.pack(expand=True, fill="x")
        
        # Add hover effects
        self.add_hover_effect(self.download_button, self.colors['warning'], '#fab387')
    
    def browse_folder(self):
        """Open file dialog to select folder"""
        folder_path = filedialog.askdirectory(
            title="Select Dataset Folder",
            initialdir=os.getcwd()
        )
        
        if folder_path:
            self.selected_folder.set(folder_path)
            self.animate_drop_success()
            self.load_and_display_first_image(folder_path)
    
    def validate_inputs(self):
        """Validate user inputs"""
        if not self.selected_folder.get():
            print("ERROR: Please select a dataset folder")
            return False
        
        if not os.path.exists(self.selected_folder.get()):
            print("ERROR: Selected dataset folder does not exist")
            return False
        
        name = self.analysis_name.get().strip()
        if not name:
            print("ERROR: Please enter an analysis name")
            return False
        
        # Validate dead streak (must be positive integer)
        try:
            streak_val = int(self.dead_streak.get())
            if streak_val <= 0:
                print("ERROR: Dead Streak must be a positive integer")
                return False
        except ValueError:
            print("ERROR: Dead Streak must be a positive integer")
            return False
        
        return True
    
    def start_analysis(self):
        """Start the analysis process"""
        if not self.validate_inputs():
            return
        
        # Check if text verification is active
        if self.analysis_paused and not self.recording1_pause:
            print("WARNING: Text verification is in progress. Please finish verifying texts before starting a new analysis.")
            return
        
        # Check if we're in recording 1 pause (should use continue instead)
        if self.recording1_pause:
            print("WARNING: Recording 1 is complete. Please use 'Continue Analysis' to proceed with recording 2, or start a new analysis session.")
            return
        
        # Update UI state
        self.analysis_running = True
        self.start_button.configure(state="disabled", bg=self.colors['bg_tertiary'])
        self.stop_button.configure(state="normal", bg=self.colors['error'])
        self.status_label.configure(text="● Running", fg=self.colors['warning'])
        self.start_busy_indicator("Initializing analysis...")
        
        # Lock zones immediately when analysis starts to prevent changes during analysis
        self.lock_zones()
        
        # Start monitoring for MiteManager file during analysis
        self.start_mite_manager_monitoring()
        
        # Refresh image display to show locked zones
        if self.selected_folder.get():
            self.load_and_display_first_image(self.selected_folder.get())
        
        # Get parameters
        folder_path = self.selected_folder.get()
        name = self.analysis_name.get().strip()
        num_per_plate = int(self.plates_per_recording.get())
        reanalyze = True  # Always run in reanalysis mode
        num_recordings = 2  # Default value for reanalysis
        dead_streak = int(self.dead_streak.get())
        enable_text_recognition = self.enable_ocr.get()
        # Remembered so the recording-0 pause knows whether to prompt for
        # manual zone labels (OCR never ran, so zone IDs are still blank).
        self._ocr_enabled_for_run = enable_text_recognition
        self._manual_labels_prompted = False

        # Store parameters for potential continuation after recording 1
        self.continue_analysis_params = (folder_path, name, num_per_plate, reanalyze, num_recordings)

        # Start analysis in separate thread
        analysis_thread = threading.Thread(
            target=self.run_analysis,
            args=(folder_path, name, num_per_plate, reanalyze, num_recordings, dead_streak, enable_text_recognition),
            daemon=True
        )
        analysis_thread.start()
    
    def start_mite_manager_monitoring(self):
        """Start monitoring for MiteManager file during analysis"""
        self.mite_manager_loaded = False
        self.check_for_mite_manager()
    
    def check_for_mite_manager(self):
        """Periodically check for MiteManager file and load it when available"""
        if not self.analysis_running or self.mite_manager_loaded:
            return
            
        try:
            mite_manager_path = os.path.join(os.path.dirname(__file__), "classes", "mite_manager.plk")
            
            if os.path.exists(mite_manager_path):
                print(f"[INFO] Found MiteManager during analysis: {mite_manager_path}")

                # Automatically load the saved MiteManager (no prompt) and pause for verification
                try:
                    with open(mite_manager_path, 'rb') as f:
                        self.mite_manager = pickle.load(f)

                    self.mite_manager_loaded = True
                    print(f"[OK] Auto-loaded MiteManager during analysis with {len(self.mite_manager.zones)} zones")

                    # Pause analysis after recording 1 for text verification
                    self.pause_after_recording1()

                    # Update zone display with new colors to reflect detected mites
                    self.root.after(100, self.refresh_zone_display)  # Small delay to ensure UI is ready

                    # Update zone display if image is loaded (legacy method)
                    if hasattr(self, 'current_pil_image') and self.current_pil_image:
                        # Refresh the image display with updated zone info
                        if hasattr(self, 'selected_folder') and self.selected_folder.get():
                            self.load_and_display_first_image(self.selected_folder.get())

                    return
                except Exception as e:
                    print(f"Error auto-loading MiteManager during analysis: {e}")
                
        except Exception as e:
            print(f"Error loading MiteManager during analysis: {e}")
        
        # Check again in 2 seconds if analysis is still running
        if self.analysis_running:
            self.root.after(2000, self.check_for_mite_manager)
    
    def pause_after_recording1(self):
        """Pause analysis after recording 1 for text verification"""
        print("[INFO] Pausing analysis after recording 1 for text verification...")

        # Set pause flags
        self.recording1_pause = True
        self.analysis_paused = True

        # Stop the analysis monitoring but keep the analysis running state temporarily
        # This prevents the analysis thread from being considered "complete"
        self.analysis_running = False  # This stops the monitoring loop

        # Unlock zones so they can be interacted with
        self.unlock_zones()

        # Update UI to show pause state
        self.root.after(0, self.update_ui_for_recording1_pause)

        # Show user notification (non-blocking)
        self.root.after(100, lambda: print(
            "INFO: Recording 1 analysis is complete! You can now verify and edit zone IDs. Click 'Continue Analysis' to proceed with recording 2."
        ))
    
    def simulate_recording1_pause(self):
        """Simulate recording 1 pause when analysis completed without triggering it"""
        print("[INFO] Simulating recording 1 pause behavior...")
        
        # Don't show the notification popup since analysis is already complete
        # Just enable text verification state
        self.recording1_pause = False  # Don't set true since analysis is complete
        self.analysis_paused = False   # Analysis is done, not paused
        
        # But enable verification features as if we paused
        self.text_verification_active = True
        
        # Update button states to show verification is available
        self.update_verify_button_state()
    
    def update_ui_for_recording1_pause(self):
        """Update UI elements for recording 1 pause state"""
        # Show orange verification prompt above progress bar
        if hasattr(self, 'progress_label'):
            try:
                self.progress_label.configure(
                    text="Verify texts and continue",
                    fg=self.colors.get('warning', 'orange')
                )
            except Exception:
                pass

        # Stop the busy indicator during verification - nothing is running.
        # (Not stop_busy_indicator(): that would overwrite the warning-colored
        # message just set above.)
        if hasattr(self, 'progress_bar'):
            try:
                self.progress_bar.stop()
            except Exception:
                pass

        # Update status
        if hasattr(self, 'status_label'):
            self.status_label.configure(text="Paused for verification", fg=self.colors.get('warning', 'orange'))
        
        # Replace start button with continue button
        if hasattr(self, 'start_button'):
            self.start_button.configure(
                text="Continue Analysis",
                command=self.continue_analysis,
                state="normal",
                bg=self.colors.get('accent', 'blue')  # Use accent color with fallback
            )
        
        # Enable verification buttons
        self.update_verify_button_state()
    
    def pause_for_text_verification(self, mite_manager_instance):
        """Callback function called by main.py after recording 1 to pause for text verification.
        Behavior: save the received manager to disk, prompt the user to load it now; if the user
        confirms, reload from disk and set up the recording1 pause UI so edits operate on the
        persisted stage (ensuring recording 2 will use user-updated zone IDs).
        """
        print("[INFO] Analysis paused after recording 1 - starting text verification")

        # Store the mite manager instance for text verification
        self.mite_manager = mite_manager_instance

        # Persist the received manager immediately to ensure disk copy exists
        try:
            if hasattr(self.mite_manager, 'save'):
                self.mite_manager.save()
                print(f"[OK] Saved MiteManager to disk from pause callback: {getattr(self.mite_manager, 'save_path', 'classes/mite_manager.plk')}")
        except Exception as e:
            print(f"Warning: could not save MiteManager from pause callback: {e}")

        # Auto-reload the saved manager immediately so the UI edits operate on the persisted stage
        try:
            mite_manager_path = os.path.join(os.path.dirname(__file__), "classes", "mite_manager.plk")
            if os.path.exists(mite_manager_path):
                with open(mite_manager_path, 'rb') as f:
                    self.mite_manager = pickle.load(f)
                    print(f"[INFO] Auto-reloaded MiteManager from disk for verification: {mite_manager_path}")
            else:
                print(f"[WARN] Expected saved MiteManager not found at: {mite_manager_path}")
        except Exception as e:
            print(f"Warning: failed to auto-reload MiteManager from disk: {e}")

        # Trigger recording 1 pause setup on UI thread so edits are available
        self.root.after(0, self.setup_recording1_pause)

        # No need to block here - the main.py will handle the waiting
        print("[INFO] GUI pause setup complete - text editing should now be available")
        return True
    
    def setup_recording1_pause(self):
        """Setup UI for recording 1 pause (called on UI thread)"""
        # Enable recording 1 pause mode
        self.recording1_pause = True
        self.analysis_paused = True
        # Update progress label to instruct the user
        try:
            pause_message = (
                "Verify the read zone text, then press continue..." if self._ocr_enabled_for_run
                else "Enter zone labels, then press continue..."
            )
            self.update_progress(60, pause_message)
        except Exception:
            pass
        
        # If we have a mite manager from the pause callback, use it directly
        if hasattr(self, 'mite_manager') and self.mite_manager:
            print(f"[OK] Using MiteManager from analysis pause with {len(self.mite_manager.zones)} zones")
            self.load_mite_data_from_manager()
        else:
            # Fallback to loading from files
            self.load_analysis_results()

        # OCR never ran for this analysis, so every zone still has its
        # default "EMPTY" label - point the user at the existing per-zone
        # editor (click a zone -> inline text box in the panel on the
        # right) instead of leaving them to notice "EMPTY" zone names later.
        if not self._ocr_enabled_for_run and not self._manual_labels_prompted:
            self._manual_labels_prompted = True
            self.root.after(150, self.prompt_manual_zone_labels)

    def prompt_manual_zone_labels(self):
        """Point the user at the existing per-zone text editor for every zone
        that has mites but no label, since OCR was disabled for this run.

        Reuses the click-to-edit flow already used to correct OCR mistakes
        (on_image_click -> update_zone_info_display -> create_zone_text_editor
        -> update_zone_text) rather than adding a separate input dialog.
        """
        if not self.mite_manager or not getattr(self.mite_manager, 'zones', None):
            return

        unlabeled = [
            i for i, zone in enumerate(self.mite_manager.zones)
            if len(getattr(zone, 'mites', [])) > 0 and getattr(zone, 'zone_id', None) in (None, "EMPTY")
        ]
        if not unlabeled:
            return

        if hasattr(self, 'status_label'):
            self.status_label.configure(
                text=f"Click each highlighted zone below to enter its label ({len(unlabeled)} left)",
                fg=self.colors.get('warning', 'orange')
            )

        # Open the editor for the first one so the panel is visible immediately.
        self.selected_zone = unlabeled[0]
        self.text_verification_active = True
        self.update_zone_info_display(self.selected_zone)
        self.update_verify_button_state()
        self.root.after_idle(self.refresh_zone_display)

        # Update buttons to show continue state
        if hasattr(self, 'analyze_button'):
            self.analyze_button.configure(
                text="Continue to Recording 2",
                state="normal",
                command=self.continue_analysis,
                bg=self.colors.get('accent', 'blue')
            )
        
        # Enable verification buttons
        self.update_verify_button_state()

        # Start checking analysis state periodically
        self.check_analysis_state()

    def load_mite_data_from_manager(self):
        """Load mite data directly from the MiteManager instance (for immediate pause)"""
        if not self.mite_manager or not hasattr(self.mite_manager, 'zones'):
            print("[ERROR] No valid MiteManager available")
            return False
        
        try:
            print(f"[INFO] Loading mite data from MiteManager with {len(self.mite_manager.zones)} zones")
            
            # Extract mite data from MiteManager zones
            self.mite_zones = []
            self.zone_coordinates = []  # Also populate zone coordinates for UI
            zone_index = 0
            
            for zone in self.mite_manager.zones:
                # Get zone coordinates
                if hasattr(zone, 'coords') and zone.coords:
                    x1, y1, x2, y2 = zone.coords
                else:
                    # Default coordinates if not available
                    x1, y1, x2, y2 = 0, 0, 100, 100
                
                # Count mites in this zone
                mite_count = len(zone.mites) if hasattr(zone, 'mites') else 0
                
                # Create zone data structure
                zone_data = {
                    'zone_id': f"Zone {zone_index + 1}",
                    'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2,
                    'mite_count': mite_count,
                    'mites': zone.mites if hasattr(zone, 'mites') else [],
                    'zone_index': zone_index
                }
                
                self.mite_zones.append(zone_data)
                
                # Also add to zone_coordinates for UI compatibility
                self.zone_coordinates.append((zone_index, x1, y1, x2, y2))
                
                zone_index += 1
            
            print(f"[OK] Successfully loaded {len(self.mite_zones)} zones for text verification")
            print(f"[INFO] Zone coordinates: {len(self.zone_coordinates)} zones ready for editing")
            
            # Refresh the zone display to show current mite data
            self.refresh_zone_display()
            
            # Enable text editing immediately
            self.unlock_zones()
            
            return True
            
        except Exception as e:
            print(f"[ERROR] Error loading mite data from manager: {e}")
            return False
    
    def check_analysis_state(self):
        """Periodically check if analysis is paused and needs UI updates"""
        try:
            from main import get_analysis_state
            state = get_analysis_state()
            
            # If analysis just became paused and we haven't handled it yet
            if state.paused and not self.recording1_pause and state.mite_manager:
                print("[INFO] Detected analysis pause - updating GUI...")
                self.mite_manager = state.mite_manager
                self.setup_recording1_pause()
                
        except Exception as e:
            # Silently handle import errors (analysis might not be running)
            pass
        
        # Schedule next check if analysis is still running
        if self.analysis_running or hasattr(self, 'recording1_pause'):
            self.root.after(1000, self.check_analysis_state)  # Check every second
    
    def continue_analysis(self):
        """Continue analysis from recording 1 pause"""
        if not self.recording1_pause:
            return
        
        print("[INFO] Continuing analysis from recording 1...")
        
        # Reset pause flags
        self.recording1_pause = False
        self.analysis_paused = False
        
        # Lock zones again for continued analysis
        self.lock_zones()
        
        # Clear any selected zones
        self.selected_zone = None
        self.update_zone_info_display(None)
        
        # Update UI back to running state
        self.analysis_running = True
        if hasattr(self, 'start_button'):
            self.start_button.configure(
                text="Start Analysis",
                command=self.start_analysis,
                state="disabled",
                bg=self.colors.get('bg_tertiary', 'lightgray')
            )
        
        if hasattr(self, 'stop_button'):
            self.stop_button.configure(state="normal", bg=self.colors.get('error', 'red'))
        
        # Resume the busy indicator now that recording 2 is starting
        self.start_busy_indicator("Processing recordings...")

        if hasattr(self, 'status_label'):
            self.status_label.configure(text="● Running", fg=self.colors.get('warning', 'orange'))
        
        # Continue with the remaining analysis (recording 2)
        # Use the new system to signal continuation
        try:
            from main import continue_analysis_from_gui
            continue_analysis_from_gui()
            print("[OK] Analysis continuation signal sent successfully")
        except Exception as e:
            print(f"[ERROR] Error continuing analysis: {e}")
            
        
        # Note: The original analysis thread will now continue with recording 2
    
    def run_analysis(self, folder_path, name, num_per_plate, reanalyze, num_recordings, dead_streak, enable_text_recognition=True):
        """Run the analysis in a separate thread.

        Status text is only updated at real milestones (not on a timer with
        made-up percentages) - the busy indicator communicates "still
        working" for whatever happens in between.
        """
        try:
            self.root.after(0, lambda: self.update_progress(0, "Setting up analysis environment..."))

            # Create temporary directory for this analysis
            self.temp_results_dir = tempfile.mkdtemp(prefix="varroa_analysis_", suffix=f"_{name}")
            print(f"[INFO] Created temporary analysis directory: {self.temp_results_dir}")

            # Lazy import to avoid issues at startup
            try:
                from main import predict
            except ImportError as e:
                raise RuntimeError(f"Could not import analysis module: {e}")

            detecting_message = (
                "Detecting mites and reading zone text..." if enable_text_recognition
                else "Detecting mites..."
            )
            self.root.after(0, lambda: self.update_progress(0, detecting_message))

            # Run the actual prediction with temporary output folder and pause callback.
            # This single call covers detection, OCR, tracking and report generation for
            # every recording - only the recording-0 pause interrupts it.
            predict(
                folder_path=folder_path,
                name=name,
                num_per_plate=num_per_plate,
                reanalyze=reanalyze,
                discobox_run=False,
                num_recordings=num_recordings,
                count=2,
                output_folder=self.temp_results_dir,  # Use temp directory
                pause_callback=self.pause_for_text_verification,
                dead_streak=dead_streak,
                enable_text_recognition=enable_text_recognition
            )

            # Set results path to the temporary directory
            self.results_path = self.temp_results_dir
            print(f"[OK] Analysis completed in: {self.temp_results_dir}")

            # Update UI on completion
            self.root.after(0, self.analysis_completed)

        except Exception as e:
            error_msg = f"Analysis failed: {str(e)}"
            self.root.after(0, lambda: self.analysis_failed(error_msg))
    
    def update_progress(self, value, message):
        """Update the status message.

        `value` is kept in the signature for backward compatibility with
        existing call sites (main.py's pause callback passes one), but no
        longer drives a fake percentage - see create_progress_section().
        """
        if hasattr(self, 'progress_label'):
            self.progress_label.configure(text=message)
        if hasattr(self, 'root'):
            self.root.update_idletasks()

    def analysis_completed(self):
        """Handle successful analysis completion"""
        self.analysis_running = False
        self.analysis_complete_flag = True  # Mark analysis as completed for text verification
        self.stop_busy_indicator("Analysis complete!")
        
        # Reset recording 1 pause flags since full analysis is now complete
        self.recording1_pause = False
        self.analysis_paused = False
        
        # Unlock zones to show the updated colors based on detected mites
        self.unlock_zones()
        
        # Update verification button states
        self.update_verify_button_state()
        
        # Reset start button back to normal start analysis function
        if hasattr(self, 'start_button'):
            self.start_button.configure(
                text="Start Analysis",
                command=self.start_analysis,
                state="normal", 
                bg=self.colors.get('success', 'green')
            )
        if hasattr(self, 'stop_button'):
            self.stop_button.configure(state="disabled", bg=self.colors.get('bg_tertiary', 'lightgray'))
        if hasattr(self, 'progress_label'):
            self.progress_label.configure(text="Analysis completed successfully!",
                                        fg=self.colors.get('success', 'green'))
        if hasattr(self, 'status_label'):
            self.status_label.configure(text="● Complete", fg=self.colors.get('success', 'green'))
        
        # Update results section if it exists
        if hasattr(self, 'results_info'):
            self.results_info.configure(
                text="Analysis completed! Results are ready for download.",
                fg=self.colors.get('success', 'green')
            )
        if hasattr(self, 'download_button'):
            self.download_button.configure(state="normal", bg=self.colors.get('warning', 'orange'))
        
        # Load analysis results for text verification
        self.load_analysis_results()
        
        # Check if we should simulate recording 1 pause behavior
        if hasattr(self, 'mite_manager') and self.mite_manager and not self.recording1_pause:
            # If mites were detected and we haven't set up recording 1 pause, do it now
            mites_found = any(len(zone.mites) > 0 if hasattr(zone, 'mites') else False 
                             for zone in getattr(self.mite_manager, 'zones', []))
            
            if mites_found:
                print("[INFO] Simulating recording 1 pause - mites detected, enabling verification")
                self.simulate_recording1_pause()
        
        # Enable text verification if UI exists
        if hasattr(self, 'verify_button'):
            self.verify_button.configure(
                text="Click zones to verify text",
                state="normal",
                bg=self.colors.get('accent', 'blue')
            )
        
        # Refresh image display with locked zones if possible
        if hasattr(self, 'selected_folder') and self.selected_folder.get():
            self.load_and_display_first_image(self.selected_folder.get())
        
        # Optional cleanup: restore original zone coordinates and remove saved
        # MiteManager stage if the user opted into automatic cleanup.
        if getattr(self, 'restore_zones_on_completion', False):
            print("INFO: restore_zones_on_completion enabled - performing cleanup of saved stage and zones")
            try:
                self.clear_saved_stage(delete_pickle=True, restore_coords=True)
            except Exception as cleanup_error:
                print(f"WARNING: cleanup during analysis_completed failed: {cleanup_error}")

        # Show completion message (non-blocking)
        print("SUCCESS: Analysis completed successfully! Results are ready for download. Zones are now locked. Click on zones to verify detected text.")

    def lock_zones(self):
        """Lock zones to prevent modification after analysis"""
        self.zones_locked = True
        
        # Update zone lock status if UI elements exist
        if hasattr(self, 'zone_lock_status'):
            self.zone_lock_status.configure(
                text="Zones Locked",
                fg=self.colors['success'] if hasattr(self, 'colors') else 'green'
            )
        
        # Disable zone selection controls if they exist
        if hasattr(self, 'plates_combobox'):
            self.plates_combobox.configure(state="disabled")
    
    def unlock_zones(self):
        """Unlock zones to allow modification"""
        self.zones_locked = False
        
        # Update zone lock status if UI elements exist
        if hasattr(self, 'zone_lock_status'):
            self.zone_lock_status.configure(
                text="Zones Unlocked",
                fg=self.colors['warning'] if hasattr(self, 'colors') else 'orange'
            )
        
        # Enable zone selection controls if they exist
        if hasattr(self, 'plates_combobox'):
            self.plates_combobox.configure(state="readonly")
        
        # Refresh zone display to show updated colors
        if hasattr(self, 'root'):
            self.root.after(100, self.refresh_zone_display)  # Small delay to ensure UI is ready
        else:
            self.refresh_zone_display()
    
    def load_analysis_results(self):
        """Load analysis results and populate mite data from MiteManager"""
        if not hasattr(self, 'results_path') or not self.results_path:
            print("No results path available, creating dummy data for testing")
            self.create_dummy_mite_data()
            return
            
        try:
            # Try multiple locations for the MiteManager
            search_paths = [
                # Look in the classes directory (where it's normally saved)
                os.path.join(os.path.dirname(__file__), "classes", "mite_manager.plk"),
                # Look in the results path if provided
                os.path.join(self.results_path, "mite_manager.plk") if self.results_path else None,
                # Look for it in the results/recording folder structure
                os.path.join(self.results_path, "results", "recording1", "mite_manager.plk") if self.results_path else None
            ]
            
            # Filter out None paths
            search_paths = [path for path in search_paths if path]
            
            mite_manager_found = False
            
            for mite_manager_path in search_paths:
                if os.path.exists(mite_manager_path):
                    print(f"Loading MiteManager from: {mite_manager_path}")
                    
                    # Import MiteManager and pickle
                    import pickle
                    from classes.MiteManager import MiteManager
                    
                    # Load the MiteManager
                    with open(mite_manager_path, 'rb') as f:
                        self.mite_manager = pickle.load(f)
                    
                    print(f"[OK] Loaded MiteManager with {len(self.mite_manager.zones)} zones")
                    mite_manager_found = True
                    
                    # Update zone display colors to reflect detected mites
                    self.refresh_zone_display()
                    
                    break
            
            if mite_manager_found:
                # Extract mite data from MiteManager zones
                self.mite_zones = []
                zone_index = 0
                
                for zone in self.mite_manager.zones:
                    print(f"Processing zone {zone_index}: '{zone.zone_id}' with {len(zone.mites)} mites")
                    
                    for mite_idx, mite in enumerate(zone.mites):
                        mite_data = {
                            'mite_id': mite.mite_id,
                            'zone_id': zone_index,  # Use zone index for UI
                            'zone_label': str(zone.zone_id),  # Store the actual zone label
                            'status': 'alive' if mite.alive else 'dead',
                            'max_diff': getattr(mite, 'max_diff', 0),
                            'local_diff': getattr(mite, 'local_avg_diff', 0),
                            'recording': 1,  # Default recording number
                            'detected_text': f"{zone.zone_id}",  # Use zone label as detected text
                            'text_verified': False,
                            'bbox': (mite.bbox.x, mite.bbox.y, mite.bbox.x + mite.bbox.w, mite.bbox.y + mite.bbox.h)
                        }
                        self.mite_zones.append(mite_data)
                    
                    zone_index += 1
                
                print(f"[OK] Extracted {len(self.mite_zones)} mites from MiteManager")
                
                # Update mite list display
                self.update_mite_list_display()
                
                # Refresh zone display to show updated colors based on detected mites
                self.refresh_zone_display()

                # If zone coordinates were populated from the MiteManager, capture an
                # immutable snapshot so we can restore them later when the user
                # wants to start a fresh analysis.
                if getattr(self, 'zone_coordinates', None) and self._original_zone_coordinates is None:
                    try:
                        self._original_zone_coordinates = list(self.zone_coordinates)
                        print(f"Saved original zone coordinates snapshot ({len(self._original_zone_coordinates)} zones)")
                    except Exception:
                        self._original_zone_coordinates = None
                
                return
                
        except Exception as e:
            print(f"Error loading MiteManager: {e}")
            print("Falling back to CSV parsing...")
        
        # Fallback to CSV parsing if MiteManager loading fails
        self._load_from_csv_fallback()
    
    def _load_from_csv_fallback(self):
        """Fallback method to load from CSV files if MiteManager is not available"""
            
        try:
            # Look for CSV results file
            results_files = []
            for root, dirs, files in os.walk(self.results_path):
                for file in files:
                    if file.endswith('.csv') and 'results' in file.lower():
                        results_files.append(os.path.join(root, file))
            
            if not results_files:
                print("No CSV results file found")
                return
                
            # Read the first results file
            results_file = results_files[0]
            print(f"Loading results from: {results_file}")
            
            # Parse CSV results
            try:
                import pandas as pd
                df = pd.read_csv(results_file)
                
                self.mite_zones = []
                for index, row in df.iterrows():
                    mite_data = {
                        'mite_id': row.get('mite ID', f'mite_{index}'),
                        'zone_id': int(row.get('zone ID', 0)),
                        'status': row.get('status', 'unknown'),
                        'max_diff': row.get('max diff', 0),
                        'local_diff': row.get('local diff', 0),
                        'recording': row.get('recording', 0),
                        'detected_text': f"Mite {row.get('mite ID', f'mite_{index}')} - {row.get('status', 'unknown')}",
                        'text_verified': False
                    }
                    self.mite_zones.append(mite_data)
                
            except ImportError:
                # Fallback to manual CSV parsing if pandas not available
                with open(results_file, 'r') as f:
                    lines = f.readlines()
                    if len(lines) > 1:  # Skip header
                        headers = lines[0].strip().split(',')
                        self.mite_zones = []
                        
                        for i, line in enumerate(lines[1:]):
                            values = line.strip().split(',')
                            if len(values) >= len(headers):
                                mite_data = {
                                    'mite_id': values[0] if len(values) > 0 else f'mite_{i}',
                                    'zone_id': int(values[1]) if len(values) > 1 and values[1].isdigit() else 0,
                                    'status': values[2] if len(values) > 2 else 'unknown',
                                    'max_diff': float(values[3]) if len(values) > 3 and values[3].replace('.','').isdigit() else 0,
                                    'local_diff': float(values[4]) if len(values) > 4 and values[4].replace('.','').isdigit() else 0,
                                    'recording': int(values[5]) if len(values) > 5 and values[5].isdigit() else 0,
                                    'detected_text': f"Mite {values[0] if len(values) > 0 else f'mite_{i}'} - {values[2] if len(values) > 2 else 'unknown'}",
                                    'text_verified': False
                                }
            print(f"Loaded {len(self.mite_zones)} mites from CSV")
            
            # Update mite list display
            self.update_mite_list_display()
            
        except Exception as e:
            print(f"Error loading CSV results: {e}")
            # Create dummy data for testing if no results found
            self.create_dummy_mite_data()
            
            print(f"Loaded {len(self.mite_zones)} mites from results")
            
            # Update mite list display
            self.update_mite_list_display()
            
        except Exception as e:
            print(f"Error loading analysis results: {e}")
            # Create dummy data for testing if no results found
            self.create_dummy_mite_data()
    
    def create_dummy_mite_data(self):
        """Create dummy mite data for testing when no results are available"""
        print("Creating dummy mite data for testing")
        self.mite_zones = [
            {
                'mite_id': 'mite_001',
                'zone_id': 0,
                'zone_label': 'A1',
                'status': 'alive',
                'max_diff': 15.2,
                'local_diff': 12.8,
                'recording': 1,
                'detected_text': 'A1',
                'text_verified': False
            },
            {
                'mite_id': 'mite_002',
                'zone_id': 0,
                'zone_label': 'A1',
                'status': 'dead',
                'max_diff': 8.1,
                'local_diff': 6.5,
                'recording': 1,
                'detected_text': 'A1',
                'text_verified': False
            },
            {
                'mite_id': 'mite_003',
                'zone_id': 1,
                'zone_label': 'B2',
                'status': 'alive',
                'max_diff': 18.7,
                'local_diff': 16.2,
                'recording': 1,
                'detected_text': 'B2',
                'text_verified': False
            },
            {
                'mite_id': 'mite_004',
                'zone_id': 2,
                'zone_label': 'C1', 
                'status': 'alive',
                'max_diff': 22.3,
                'local_diff': 19.1,
                'recording': 1,
                'detected_text': 'C1',
                'text_verified': False
            }
        ]
        
        # Also create dummy zone coordinates for testing hover functionality
        self.zone_coordinates = [
            (0, 50, 50, 200, 150),   # Zone A1 (zone_id=0)
            (1, 250, 100, 400, 200), # Zone B2 (zone_id=1) 
            (2, 100, 250, 300, 350)  # Zone C1 (zone_id=2)
        ]
        
        print(f"Created {len(self.mite_zones)} dummy mites in {len(self.zone_coordinates)} zones")
        self.update_mite_list_display()
    
    def analysis_failed(self, error_msg):
        """Handle analysis failure"""
        self.analysis_running = False
        
        # Unlock zones since analysis failed
        self.unlock_zones()
        
        self.start_button.configure(state="normal", bg=self.colors['success'])
        self.stop_button.configure(state="disabled", bg=self.colors['bg_tertiary'])
        self.stop_busy_indicator("Analysis failed", color=self.colors['error'])
        self.status_label.configure(text="● Error", fg=self.colors['error'])

        # Refresh image display to show unlocked zones
        if self.selected_folder.get():
            self.load_and_display_first_image(self.selected_folder.get())

        # Show error message (non-blocking)
        print(f"ERROR: Analysis Failed - {error_msg}")
    
    def stop_analysis(self):
        """Stop the current analysis"""
        if self.analysis_running:
            self.analysis_running = False
            
            # Unlock zones since analysis was stopped
            self.unlock_zones()
            
            self.start_button.configure(state="normal", bg=self.colors['success'])
            self.stop_button.configure(state="disabled", bg=self.colors['bg_tertiary'])
            self.stop_busy_indicator("Analysis stopped", color=self.colors['warning'])
            self.status_label.configure(text="● Stopped", fg=self.colors['warning'])
            
            # Refresh image display to show unlocked zones
            if self.selected_folder.get():
                self.load_and_display_first_image(self.selected_folder.get())
            
            print("INFO: Analysis has been stopped")
    
    def download_results_zip(self):
        """Create and download results as ZIP file, then clean up temporary folder"""
        if not self.results_path or not os.path.exists(self.results_path):
            print("WARNING: No results folder found to download")
            return
        
        try:
            # Ask user where to save the ZIP
            analysis_name = self.analysis_name.get().strip() or "analysis"
            default_filename = f"{analysis_name}.zip"
            
            zip_path = filedialog.asksaveasfilename(
                title="Save Results ZIP",
                defaultextension=".zip",
                filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")],
                initialdir=os.path.expanduser("~/Downloads"),
                initialfile=default_filename
            )
            
            if not zip_path:
                return
            
            # Create progress dialog
            progress_window = tk.Toplevel(self.root)
            progress_window.title("Creating ZIP...")
            progress_window.geometry("400x120")
            progress_window.configure(bg=self.colors['bg_secondary'])
            progress_window.transient(self.root)
            progress_window.grab_set()
            
            # Center the progress window
            progress_window.update_idletasks()
            x = (progress_window.winfo_screenwidth() // 2) - 200
            y = (progress_window.winfo_screenheight() // 2) - 60
            progress_window.geometry(f"400x120+{x}+{y}")
            
            progress_label = tk.Label(
                progress_window,
                text="Creating ZIP file...",
                font=self.fonts['body'],
                bg=self.colors['bg_secondary'],
                fg=self.colors['text_primary']
            )
            progress_label.pack(pady=20)
            
            zip_progress = ttk.Progressbar(
                progress_window,
                mode='indeterminate',
                length=300,
                style='Modern.Horizontal.TProgressbar'
            )
            zip_progress.pack(pady=(0, 20))
            zip_progress.start()
            
            # Create ZIP in separate thread
            def create_zip():
                try:
                    # Determine the results folder to zip (use temp directory)
                    folder_to_zip = self.results_path
                    
                    if not folder_to_zip or not os.path.exists(folder_to_zip):
                        raise Exception("No results folder found to zip")
                    
                    # Update progress text
                    self.root.after(0, lambda: progress_label.configure(text="Compressing files..."))
                    
                    # Create the ZIP file with the contents of the temporary results folder
                    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for root, dirs, files in os.walk(folder_to_zip):
                            for file in files:
                                file_path = os.path.join(root, file)
                                # Create archive path relative to the folder being zipped
                                # This puts files directly in the ZIP root, not in a subfolder
                                arc_path = os.path.relpath(file_path, folder_to_zip)
                                zipf.write(file_path, arc_path)
                    
                    # Update progress text
                    self.root.after(0, lambda: progress_label.configure(text="Cleaning up temporary files..."))
                    
                    # Clean up the temporary directory
                    if self.temp_results_dir and os.path.exists(self.temp_results_dir):
                        try:
                            shutil.rmtree(self.temp_results_dir)
                            print(f"[OK] Cleaned up temporary directory: {self.temp_results_dir}")
                            self.temp_results_dir = None
                            self.results_path = None
                        except Exception as cleanup_error:
                            print(f"[WARN] Warning: Could not clean up temp directory: {cleanup_error}")
                            # Don't fail the whole operation for cleanup issues
                    
                    # Get folder name for success message
                    folder_name = "analysis_results"
                    
                    # Close progress window and show success (non-blocking)
                    self.root.after(0, lambda: [
                        progress_window.destroy(),
                        self.download_button.configure(state="disabled", bg=self.colors['bg_tertiary']),
                        self.results_info.configure(text="Results downloaded and temporary files cleaned up", fg=self.colors['text_muted']),
                        print(f"INFO: Analysis results successfully saved to: {zip_path} (size: {self.get_file_size(zip_path)})")
                    ])
                    
                except Exception as e:
                    error_msg = str(e)
                    self.root.after(0, lambda: [
                        progress_window.destroy(),
                        print(f"ERROR: Failed to create ZIP file: {error_msg}")
                    ])
            
            # Start ZIP creation
            threading.Thread(target=create_zip, daemon=True).start()
            
        except Exception as e:
            print(f"ERROR: Failed to download results: {e}")
    
    def safe_remove_folder(self, folder_path):
        """Safely remove a folder with retry logic for Windows permission issues"""
        import time
        max_retries = 5
        delay = 1  # seconds
        
        for attempt in range(max_retries):
            try:
                if os.path.exists(folder_path):
                    # First try to make all files writable
                    for root, dirs, files in os.walk(folder_path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            try:
                                os.chmod(file_path, 0o777)
                            except:
                                pass  # Ignore chmod errors
                    
                    # Try to remove the folder
                    shutil.rmtree(folder_path)
                    print(f"Successfully removed folder: {folder_path}")
                    return
                    
            except PermissionError as e:
                print(f"Attempt {attempt + 1}: Permission error removing {folder_path}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff
                else:
                    print(f"Failed to remove folder after {max_retries} attempts. Manual cleanup may be required.")
                    # Don't raise the exception - just log it and continue
                    
            except Exception as e:
                print(f"Unexpected error removing folder {folder_path}: {e}")
                break

    def clear_saved_stage(self, delete_pickle=False, restore_coords=False):
        """Clear saved mite manager stage and optionally restore zone coordinates.

        delete_pickle: if True, attempt to remove classes/mite_manager.plk
        restore_coords: if True, restore zone_coordinates from the saved snapshot
        """
        # 1) Delete the pickled MiteManager if requested
        if delete_pickle:
            try:
                pickle_path = os.path.join(os.path.dirname(__file__), 'classes', 'mite_manager.plk')
                if os.path.exists(pickle_path):
                    try:
                        os.remove(pickle_path)
                        print(f"INFO: Removed saved MiteManager: {pickle_path}")
                    except Exception as e:
                        print(f"WARNING: Could not remove {pickle_path}: {e}")
                else:
                    print(f"INFO: No saved MiteManager found at {pickle_path}")
            except Exception as e:
                print(f"WARNING: Unexpected error trying to delete saved stage: {e}")

        # 2) Clear in-memory analysis-derived state to avoid stale overlays
        try:
            self.mite_manager = None
            self.mite_zones = []
            self.selected_zone = None
            self.current_hover_zone = None
            self.analysis_complete_flag = False
            self.analysis_paused = False
            self.recording1_pause = False
            print("[OK] Cleared in-memory MiteManager and analysis state")
        except Exception as e:
            print(f"Warning: could not clear in-memory state: {e}")

        # 3) Restore coordinates if requested and snapshot exists
        if restore_coords and getattr(self, '_original_zone_coordinates', None) is not None:
            try:
                self.zone_coordinates = list(self._original_zone_coordinates)
                print(f"INFO: Restored original zone coordinates ({len(self.zone_coordinates)} zones)")
            except Exception as e:
                print(f"WARNING: Failed to restore original zone coordinates: {e}")

        # 4) Force UI to reload first image / reapply coordinate overlay to reflect cleared state
        try:
            if hasattr(self, 'selected_folder') and self.selected_folder.get():
                self.load_and_display_first_image(self.selected_folder.get())
            else:
                self.refresh_zone_display()

            # Ensure UI elements reflect unlocked/clean state
            try:
                self.unlock_zones()
                self.update_verify_button_state()
            except Exception:
                pass

            print("[INFO] UI refreshed after clearing saved stage")
        except Exception as e:
            print(f"Warning: could not refresh UI after clearing stage: {e}")

    def get_file_size(self, file_path):
        """Get human readable file size"""
        size = os.path.getsize(file_path)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    
    def run(self):
        """Start the application"""
        self.root.mainloop()


def main():
    """Main entry point"""
    try:
        app = ModernVarroaDetectorApp()
        app.run()
    except Exception as e:
        print(f"ERROR: Failed to start application: {e}")


if __name__ == "__main__":
    main()
