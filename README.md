# Varroa Detector 🐝  
AI-powered analysis of Discobox data using advanced YOLO-based detection.  

This tool automates the detection and classification of **Varroa destructor mites** from Discobox recordings. It identifies mites, processes experimental annotations, and provides detailed survival analyses.  

---

## 🚀 Features  
- Automated detection of **Varroa mites** using a fine-tuned YOLO model.  
- Classification of mites as **alive or dead** based on pixel-difference motion tracking.  
- Easy-to-use GUI for dataset upload, configuration, and verification.  
- Exportable results in structured **Excel files** and images for further analysis.  
- Built-in visualization of survival rates, mite movements, and detection performance.  

---

## ⚙️ Installation  

### Prerequisites  
- [Miniforge](https://conda-forge.org/miniforge/)  
- [Git](https://git-scm.com/downloads)  

### Steps  
```bash
# 1. Clone the repository
git clone https://github.com/Mateo-Schaerer-Gonzalez/Agroscope_Varoa_detector.git

# 2. Navigate into the project directory
cd Agroscope_Varoa_detector

# 3. Run the installation script
# Windows
install.cmd

# Linux
chmod +x install.sh
./install.sh
```

The Linux installer creates/updates a conda environment from `env_linux.yaml`, a `run_varroa_detector.sh` launcher script, and an application menu / desktop entry named "Varroa Detector".
---

## ▶️ Usage  

1. **Prepare your recording data**  
   - Use a fine black pen for labeling zones.  
   - Recommended recording parameters:  
     ```
     vent time = 20
     led1 time = 20
     led2 time = 20
     frame count = 30
     fps = 30
     vent = 255
     led1 = 255
     led2 = 255
     ```  
   - Each zone = 1–2 lines of handwriting (system will auto-assign zones).  
   - If using dead controls, freeze mites ≥2h before recording.  

2. **Launch the software**  
   - Double-click the desktop icon.  
   - Upload Discobox recording data (full folder of `.bmp` images).  

3. **Configure analysis**  
   - Enter analysis name.  
   - Set number of samples per plate.  
   - Define **dead streak** (consecutive frames required to classify mite as dead).  

4. **Verify and edit labels**  
   - Hover/click zones to check and correct text labels.  
   - Group zones by giving them the same name.  

5. **Run the analysis & export results**  
   - Download results as a `.zip` containing:  
     - `recording_summary.xlsx` – overview of survival data.  
     - `mites.xlsx` – detailed per-zone detection results.  
     - Images (`.png`) of survival curves, movement plots, and mite cutouts.  

---

## 📊 Results & Metrics  

- **Survival curves** across recordings and zones.  
- **Mite movement plots** (pixel-difference analysis).  
- **Detection model** performance (precision, recall, mAP).  
- Accuracy of alive/dead classification:  
  - Max Difference: **88.5%** (FPR 4%, FNR 19.5%)  
  - Local Difference: **87.8%** (FPR 4%, FNR 21.0%)  

---

## 🔬 Model Training  
- Based on **Yániz et al. (2025)** open-source YOLO model.  
- Fine-tuned on **512 Discobox images** (80/20 train/val split).  
- Trained for **70 epochs**, freezing top 100 layers.  
- No signs of overfitting; strong recall and mAP@50.  

---

## 📖 References  
- Ultralytics (2023). *Performance Metrics Deep Dive*. [Docs](https://docs.ultralytics.com/de/guides/yolo-performance-metrics/)  
- Yániz, Jesús et al. (2025). *An AI-Based Open-Source Software for Varroa Mite Fall Analysis in Honeybee Colonies*. **Agriculture**
