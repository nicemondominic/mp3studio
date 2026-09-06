# 🎵 MP3 Studio

**MP3 Studio** is a modern desktop audio utility built with **Python, PySide6, and FFmpeg**. It provides a simple graphical interface for extracting, editing, merging, previewing, and managing audio files without requiring users to work directly with FFmpeg commands.

The project is designed to be practical, lightweight, and easy to use while still providing useful controls for everyday audio workflows.

---

## ✨ Features

### 🎬 Extract Audio

Extract audio from video or media files using FFmpeg.

**Features include:**
- Support for common video/audio input formats supported by FFmpeg
- Output format selection
- Custom output filename
- Output files saved to `assets/output/`
- Audio waveform preview
- Audio playback and seeking
- FFmpeg-powered processing

---

### 🎚️ Audio Studio

Work with multiple audio tracks in one workspace.

**Features include:**
- Add multiple audio files
- Individual track playback
- Per-track volume control
- Fade in
- Fade out
- Play from a selected position
- Play to a selected position
- Auto Play
- Repeat
- Audio presets
- Move tracks
- Duplicate tracks
- Remove tracks
- Per-track seeking
- Individual waveform visualization

Audio Studio is useful for quickly organizing and previewing several audio files before processing them.

---

### ✂️ Audio Editor

Edit an individual audio file with non-destructive editing controls.

**Available controls:**
- Trim start
- Trim end
- Volume
- Fade in
- Fade out
- Playback speed
- Normalize audio
- Preview edited audio
- Export edited audio
- Multiple output formats
- Waveform visualization

The editor also includes an editing history system.

#### Editing History

The menu toolbar provides:

- **Undo**
- **Redo**
- **Reset Current Edit**

This allows you to experiment with editing settings without permanently modifying the original source file.

---

### 🔗 Audio Merger

Combine multiple audio files into one final audio file.

Audio Merger is designed around a timeline-based workflow.

**Features include:**
- Add multiple audio files
- Automatic sequential placement
- Manual timeline positioning
- Per-track source start
- Per-track source end
- Timeline start position
- Volume
- Pan
- Mute
- Solo
- Fade in
- Fade out
- Individual track playback
- Individual track seeking
- Waveform visualization for tracks
- Final mix preview
- Final output waveform
- Export final merged audio

New tracks are automatically placed sequentially by default, while manual timeline positions can be used when overlapping audio is desired.

> **Note:** The Crossfade control is part of the Audio Merger interface and is intended for smooth transitions between adjacent tracks.

---

### 🏷️ Metadata Editor

Edit common audio metadata without modifying the original source file.

**Supported metadata fields:**
- Title
- Artist
- Album
- Genre
- Year
- Track
- Comment

The metadata editor reads existing tags with FFprobe and writes the edited metadata to a new output file.

This keeps the original audio file untouched.

---

## 🌊 Waveform Visualization

Waveforms are available throughout the application to make audio navigation easier.

Waveform support is provided in:

- Extract Audio
- Audio Studio
- Audio Editor
- Audio Merger
- Audio Merger final preview
- Metadata Editor

The waveform allows you to visually understand the audio and interact with the playback position.

---

## ⌨️ Keyboard Controls

### Spacebar

Press:

**`Space`**

to play/pause or resume audio in the applicable sections.

The global spacebar handler is designed to work without interfering with normal text-entry controls such as:

- Text fields
- Spin boxes
- Combo boxes

---

## 🖥️ User Interface

MP3 Studio uses a clean desktop-oriented interface built with PySide6.

The interface includes:

- Top navigation
- Dedicated feature sections
- Blue action buttons
- White/light workspace
- Audio waveforms
- Playback controls
- Track cards
- Editing controls
- Menu toolbar
- About dialog
- Application icon

---

## ℹ️ About MP3 Studio

The application includes an **About MP3 Studio** option in the menu toolbar.

The About dialog provides information about:

- Application name
- Version
- Application description
- Developer
- Technology stack
- GitHub project

**Created by Nicemon Dominic**

GitHub:

https://github.com/nicemondominic

---

## 🧰 Technology Stack

MP3 Studio is built using:

| Technology | Purpose |
|---|---|
| Python | Core application language |
| PySide6 | Desktop GUI |
| Qt Multimedia | Audio playback |
| FFmpeg | Audio processing |
| FFprobe | Media information and metadata inspection |
| QPainter | Waveform rendering |

---

## 📁 Project Structure

```text
MP3_Studio/
│
├── main.py
│
├── core/
│   └── ffmpeg.py
│
├── ui/
│   └── main_window.py
│
├── assets/
│   ├── output/
│   ├── mp3_studio.ico
│   └── mp3_studio_icon.png
│
└── README.md
```

### `main.py`

Application entry point.

Starts the MP3 Studio desktop application.

### `ui/main_window.py`

Contains the main PySide6 interface, navigation, audio controls, waveform widgets, dialogs, and user interaction logic.

### `core/ffmpeg.py`

Contains FFmpeg-related processing and command generation.

### `assets/output/`

Default location for generated audio files.

### `assets/mp3_studio.ico`

Windows application icon.

### `assets/mp3_studio_icon.png`

PNG version of the application icon.

---

# 🚀 Installation

## Requirements

Before running MP3 Studio, install:

- Python 3.10 or newer
- FFmpeg
- FFprobe
- PySide6

---

## 1. Clone the repository

```bash
git clone https://github.com/nicemondominic/mp3studio.git
cd mp3studio
```

Replace the repository URL with your actual GitHub repository URL if the repository name is different.

---

## 2. Create a virtual environment

### Windows

```powershell
python -m venv .venv
```

Activate it:

```powershell
.venv\Scripts\activate
```

### Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
```

---

## 3. Install dependencies

```bash
pip install PySide6
```

If the project later includes a `requirements.txt`, install everything with:

```bash
pip install -r requirements.txt
```

---

# 🎬 Install FFmpeg

MP3 Studio relies on FFmpeg for media processing.

Verify that FFmpeg is available:

```bash
ffmpeg -version
```

Also verify FFprobe:

```bash
ffprobe -version
```

If both commands return version information, MP3 Studio can use them.

Make sure the FFmpeg executables are available in your system `PATH`, or configure the application to use their executable locations.

---

# ▶️ Running the Application

From the project directory:

```bash
python main.py
```

The MP3 Studio window should open.

---

# 🔄 Typical Workflow

## Extract audio from a video

1. Open **Extract Audio**
2. Select a video/media file
3. Choose the output format
4. Enter an output filename
5. Process the file
6. Find the generated file in:

```text
assets/output/
```

---

## Edit an audio file

1. Open **Audio Editor**
2. Load an audio file
3. Adjust trim points
4. Change volume if required
5. Add fade in/out
6. Adjust playback speed
7. Enable normalization if required
8. Preview the result
9. Export the edited audio

The source file remains unchanged.

---

## Merge audio files

1. Open **Audio Merger**
2. Add multiple audio files
3. Review each waveform
4. Adjust source start/end points
5. Adjust timeline positions
6. Set volume/pan/fade controls
7. Preview the final mix
8. Export the merged audio

Tracks are automatically arranged sequentially when added, unless you manually change their timeline positions.

---

## Edit metadata

1. Open **Metadata Editor**
2. Select an audio file
3. Review existing metadata
4. Change the required fields
5. Export the tagged file

The original file is not overwritten.

---

# 🛡️ Non-Destructive Workflow

MP3 Studio is designed to avoid unnecessarily modifying the original source files.

Editing and metadata operations generate new output files rather than directly replacing the source.

This makes it safer to experiment with:

- Trimming
- Volume changes
- Fades
- Speed changes
- Normalization
- Metadata changes

---

# 📦 Output

Generated files are stored by default in:

```text
assets/output/
```

Depending on the operation, the output can be:

- MP3
- WAV
- M4A
- AAC
- FLAC
- OGG
- Other formats supported by the configured FFmpeg workflow

Actual format availability depends on the installed FFmpeg build and the application's export options.

---

# 🎨 Application Icon

MP3 Studio includes its own application branding.

The icon is used for:

- Main window
- Windows taskbar
- Application identity
- About dialog
- Windows `.ico` resource

This helps distinguish MP3 Studio from the default Python application icon when running on Windows.

---

# 🧪 Project Status

MP3 Studio is an actively developed project.

Current functionality includes:

- [x] Audio extraction
- [x] Audio playback
- [x] Audio Studio
- [x] Audio Editor
- [x] Audio Merger
- [x] Metadata Editor
- [x] Waveform visualization
- [x] Audio seeking
- [x] Spacebar play/pause
- [x] Undo/Redo editing history
- [x] Application icon
- [x] About dialog
- [x] FFmpeg integration
- [x] FFprobe integration

More improvements and features can be added as development continues.

---

# 🗺️ Possible Future Improvements

Potential future features include:

- More advanced waveform editing
- Multi-format batch conversion
- Batch metadata editing
- Drag-and-drop audio importing
- More audio effects
- Equalizer
- Noise reduction
- Compressor
- Reverb
- Echo
- Pitch adjustment
- More advanced crossfades
- Audio visualization improvements
- Export presets
- Recent files
- Custom output folders
- Portable Windows build
- Windows installer
- Linux package
- macOS package
- Dark mode
- Custom keyboard shortcuts

---

# 🤝 Contributing

Contributions, suggestions, and improvements are welcome.

If you would like to contribute:

1. Fork the repository
2. Create a new branch

```bash
git checkout -b feature/my-feature
```

3. Make your changes
4. Test the application
5. Commit your changes

```bash
git commit -m "Add new audio feature"
```

6. Push your branch

```bash
git push origin feature/my-feature
```

7. Open a Pull Request

---

# 🐛 Reporting Issues

If you encounter a problem, please open a GitHub issue and include:

- Operating system
- Python version
- FFmpeg version
- Steps to reproduce the issue
- Expected behavior
- Actual behavior
- Error message or screenshot, if available

This makes it easier to reproduce and fix the problem.

---

# 📜 License

Choose and add the license that you want to use for the project before publishing the repository.

For example, if you decide to use the MIT License, add a `LICENSE` file containing the official MIT License text.

---

# 👨‍💻 Author

## Nicemon Dominic

Created and developed by **Nicemon Dominic**.

GitHub:

https://github.com/nicemondominic

---

# ⭐ Support the Project

If you find MP3 Studio useful:

- ⭐ Star the repository
- 🐛 Report bugs
- 💡 Suggest features
- 🔧 Contribute improvements
- 📢 Share the project

Every contribution helps the project grow.

---

## ❤️ MP3 Studio

**A simple, modern desktop audio toolkit powered by Python, PySide6 and FFmpeg.**

**Created by Nicemon Dominic**
