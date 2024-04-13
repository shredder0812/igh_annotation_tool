# IGH Annotation Tool

## Introduction
This tool is designed for physicians to mark the location of lesions in endoscopic images. The collected data will be used to develop applications for lesion detection and tracking in endoscopic images.

## Usage
### With Python files

- Clone this repository.
```bash
git clone https://github.com/shredder0812/igh_annotation_tool.git
```

- Install requirements.
```bash
pip install -r requirements.txt
```

- Run `main.py` and use.
```bash
python  main.py
```
### With Executable files
- Download .exe files from Google Drive: 
<a href="https://drive.google.com/drive/folders/1w7Hv20d_KkRX8ELBXcDjtHqB5vwzFnFq?usp=sharing" target="_blank">Annotation Tool (Executable files)</a>

## Tool Tutorials

When running the main.py file, a window will appear prompting you to select an MP4 file (recommended video size is 1280x1024). After selecting the file, you will see the main interface as shown in the following image:

<p align="center">
  <img src="demo_tool.png" width=1280><br/>
  <i>IGH Annotation Tool Demo</i>
</p>

**Notes**
- When selecting the input video, it is important to note that for each video, create an empty folder to contain that video. After interacting with the tool and exiting the tool, the data for each video will be automatically saved into the corresponding folder containing that video.
- Below are the tool files that can be used with each video size and the size at which the data will be saved:

| File                   | Video's size           | Data format    |
| ---------------------- | ---------------------- | -------------- |
| `annotation.py`        | **1280x1024**          | **1280x1024**  |
| `annotation640x512.py` | **1280x1024; 640x512** | **1280x1024**  |
| `annotation640data.py` | **640x512**            | **640x512**    |

### Information displayed
- Frame: Frame number from the video (counting from 1).
- Boxes: Number of Bounding Boxes in the current frame.
- Object ID: Serial number of the object in the video.
- Class: Name of the object, describing the type of damage.
- Tutorial: Instructions for keyboard shortcuts.

### How to draw Bounding Box

Bounding Box is drawn by selecting two points (these two points are located in 2 opposite corners of the Box). 

While drawing, the Bounding Box line will be green. Once two points are selected, indicating the completion of drawing, the Box will be displayed on the screen with a red border. At the same time, the Boxes panel will count the number of boxes in the frame.

### Shortcuts

- N: Move to the next Frame of the current Frame (Frame increases by 1 unit).
- B: Return to the Frame before the current Frame (Frame is reduced by 1 unit).
- R: Delete the Bounding Box just drawn (Boxes are reduced by 1 unit).
- F: Increase the object's serial number (Increase Object ID by 1 unit).
- D: Reduce the object's serial number (Reduce Object ID by 1 unit and cannot decrease to 0).
- C: Change the object name (Class will change to A, B, C, D, E and A respectively).
- Esc: Exit the tool.

### Saved data

After exiting the tool, saved data includes:
- A gt.txt file contains Ground Truth information in the following form:
  
`{frame_number}, {object_id}, {xmin}, {ymin}, {width}, {height}, {conf}, x, y, z`

- A class.txt file contains information about which Frame, which Object ID and which Class, stored in the form:
  
 `{frame_number}, {object_id}, {class}`
