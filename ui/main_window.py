from pathlib import Path
import json
import os
import subprocess
import struct

from PySide6.QtCore import Qt, QUrl, QProcess, QTimer, Signal, QRectF, QEvent
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QPushButton, QFileDialog, QLineEdit, QComboBox, QProgressBar,
    QMessageBox, QFormLayout, QDoubleSpinBox, QStackedWidget,
    QListWidget, QListWidgetItem, QGroupBox, QSizePolicy, QScrollArea,
    QSlider, QCheckBox, QToolButton, QAbstractItemView, QApplication, QMenu, QStyle, QDialog, QDialogButtonBox
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QAction, QIcon

from core.ffmpeg import probe, build_command, build_edit_command, build_mixer_command, ffmpeg_available

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "assets" / "output"
PRESET_DIR = ROOT / "assets" / "presets"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PRESET_DIR.mkdir(parents=True, exist_ok=True)

APP_STYLE = """
QMainWindow, QWidget {
    background: #ffffff;
    color: #172033;
    font-family: "Segoe UI";
    font-size: 14px;
}
QFrame#topbar {
    background: #ffffff;
    border-bottom: 1px solid #e7ebf2;
}
QLabel#brand {
    color: #1155cc;
    font-size: 22px;
    font-weight: 800;
}
QLabel#status, QLabel#muted {
    color: #64748b;
}
QLabel#bigTitle {
    font-size: 27px;
    font-weight: 800;
}
QPushButton {
    background: #1769e0;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 9px 15px;
    font-weight: 700;
}
QPushButton:hover { background: #0f5dcc; }
QPushButton:pressed { background: #0b4da9; }
QPushButton:disabled { background: #cbd5e1; color: white; }
QPushButton#nav, QToolButton#smallTool {
    background: transparent;
    color: #64748b;
    border-radius: 8px;
    padding: 9px 15px;
}
QPushButton#nav:hover, QToolButton#smallTool:hover {
    background: #f1f6ff;
    color: #1155cc;
}
QPushButton#nav[active="true"] {
    background: #eaf2ff;
    color: #1155cc;
}
QPushButton#secondary, QToolButton#smallTool {
    background: #f3f6fa;
    color: #334155;
    border: 1px solid #dbe2ea;
}
QPushButton#secondary:hover, QToolButton#smallTool:hover { background: #e9eef5; }
QPushButton#danger {
    background: #fff1f2;
    color: #be123c;
    border: 1px solid #fecdd3;
}
QGroupBox {
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    margin-top: 12px;
    padding: 17px;
    font-weight: 800;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 5px;
    color: #172033;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: #ffffff;
    border: 1px solid #cfd8e3;
    border-radius: 8px;
    padding: 8px 10px;
    min-height: 18px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #1769e0;
}
QSlider::groove:horizontal {
    height: 5px;
    background: #dce4ee;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    width: 14px;
    margin: -5px 0;
    background: #1769e0;
    border-radius: 7px;
}
QCheckBox { spacing: 7px; }
QProgressBar {
    background: #edf2f7;
    border: none;
    border-radius: 6px;
    height: 11px;
    text-align: center;
}
QProgressBar::chunk {
    background: #1769e0;
    border-radius: 6px;
}
QLabel#dropzone {
    background: #f8fbff;
    border: 2px dashed #9ab8e8;
    border-radius: 14px;
    color: #4b6384;
    font-size: 15px;
}
QFrame#track {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
}
QFrame#trackPlaying {
    background: #f7fbff;
    border: 1px solid #8fb5ed;
    border-radius: 12px;
}
QLabel#trackNumber {
    background: #eaf2ff;
    color: #1155cc;
    border-radius: 15px;
    font-weight: 800;
    padding: 6px 9px;
}
QLabel#missing {
    color: #be123c;
    font-weight: 700;
}
"""

def fmt_time(seconds):
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def fmt_size(size):
    value = float(size)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


class WaveformWidget(QWidget):
    """Lightweight real waveform display for any FFmpeg-supported audio file."""
    seekRequested = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.samples = []
        self.duration = 0.0
        self.cursor = 0.0
        self.selection_start = None
        self.selection_end = None
        self.setMinimumHeight(130)
        self.setMouseTracking(True)

    def set_audio(self, path, duration=None):
        self.samples = []
        self.duration = float(duration or 0)
        try:
            cmd = [
                "ffmpeg", "-v", "error", "-i", str(path),
                "-ac", "1", "-ar", "8000", "-f", "s16le", "-"
            ]
            raw = subprocess.run(cmd, capture_output=True, timeout=30).stdout
            values = struct.unpack("<%dh" % (len(raw)//2), raw[:len(raw)//2*2])
            if values:
                bins = max(300, min(1800, self.width() * 2))
                step = max(1, len(values)//bins)
                self.samples = [
                    max(abs(v) for v in values[i:i+step]) / 32768.0
                    for i in range(0, len(values), step)
                ]
        except Exception:
            self.samples = []
        self.update()

    def set_cursor(self, seconds):
        self.cursor = max(0.0, min(float(seconds), self.duration or 0))
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.duration > 0:
            self._seek_at(event.position().x())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self.duration > 0:
            self._seek_at(event.position().x())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def _seek_at(self, x):
        seconds = max(0.0, min(1.0, x / max(1, self.width()))) * self.duration
        self.cursor = seconds
        self.seekRequested.emit(seconds)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(8, 12, -8, -12)
        painter.fillRect(rect, QColor("#f8fbff"))
        painter.setPen(QPen(QColor("#cbd5e1"), 1))
        mid = rect.center().y()
        painter.drawLine(rect.left(), mid, rect.right(), mid)

        if self.samples:
            pen = QPen(QColor("#1769e0"), 1)
            painter.setPen(pen)
            n = len(self.samples)
            for i, amp in enumerate(self.samples):
                x = rect.left() + (i / max(1, n-1)) * rect.width()
                h = amp * rect.height() * 0.46
                painter.drawLine(x, mid-h, x, mid+h)

        if self.duration > 0:
            x = rect.left() + (self.cursor / self.duration) * rect.width()
            painter.setPen(QPen(QColor("#e11d48"), 2))
            painter.drawLine(x, rect.top(), x, rect.bottom())

        painter.end()

class DropLabel(QLabel):
    def __init__(self, callback):
        super().__init__("Drop a video or audio file here\n\nRelease to load the file")
        self.callback = callback
        self.setObjectName("dropzone")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(145)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            self.callback(urls[0].toLocalFile())
        event.acceptProposedAction()

class AudioTrackWidget(QFrame):
    play_requested = Signal(object)
    remove_requested = Signal(object)
    duplicate_requested = Signal(object)
    move_up_requested = Signal(object)
    move_down_requested = Signal(object)
    changed = Signal()
    seek_requested = Signal(object, int)

    def __init__(self, data, index):
        super().__init__()
        self.data = data
        self.index = index
        self.duration = float(data.get("duration", 0))
        self.missing = not Path(data["path"]).exists()
        self.setObjectName("track")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(145)
        self.build()
        self.refresh()

    def build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(13, 11, 13, 11)
        outer.setSpacing(8)

        top = QHBoxLayout()
        self.number = QLabel()
        self.number.setObjectName("trackNumber")
        top.addWidget(self.number)

        self.name = QLabel()
        self.name.setWordWrap(False)
        self.name.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        top.addWidget(self.name, 1)

        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedWidth(45)
        self.play_btn.clicked.connect(lambda: self.play_requested.emit(self))
        top.addWidget(self.play_btn)

        self.up_btn = QToolButton()
        self.up_btn.setObjectName("smallTool")
        self.up_btn.setText("↑")
        self.up_btn.clicked.connect(lambda: self.move_up_requested.emit(self))
        top.addWidget(self.up_btn)

        self.down_btn = QToolButton()
        self.down_btn.setObjectName("smallTool")
        self.down_btn.setText("↓")
        self.down_btn.clicked.connect(lambda: self.move_down_requested.emit(self))
        top.addWidget(self.down_btn)

        self.dup_btn = QToolButton()
        self.dup_btn.setObjectName("smallTool")
        self.dup_btn.setText("⧉")
        self.dup_btn.clicked.connect(lambda: self.duplicate_requested.emit(self))
        top.addWidget(self.dup_btn)

        self.mute = QCheckBox("Mute")
        self.mute.toggled.connect(self.on_changed)
        top.addWidget(self.mute)

        self.solo = QCheckBox("Solo")
        self.solo.toggled.connect(self.on_changed)
        top.addWidget(self.solo)

        self.remove_btn = QPushButton("Remove")
        self.remove_btn.setObjectName("danger")
        self.remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        top.addWidget(self.remove_btn)
        outer.addLayout(top)

        if self.missing:
            self.missing_label = QLabel("⚠ File not found — use Locate to repair this track")
            self.missing_label.setObjectName("missing")
            outer.addWidget(self.missing_label)

        self.waveform = WaveformWidget()
        self.waveform.set_audio(self.data["path"], self.duration)
        self.waveform.seekRequested.connect(
            lambda sec: self.seek_requested.emit(
                self, int(sec / max(0.001, self.duration) * 1000)
            )
        )
        outer.addWidget(self.waveform)

        playback = QHBoxLayout()
        playback.setSpacing(9)

        self.position_label = QLabel("00:00")
        self.position_label.setObjectName("muted")
        self.position_label.setFixedWidth(72)

        self.position_slider = SeekSlider(Qt.Horizontal)
        self.position_slider.setRange(0, 1000)
        self.position_slider.setValue(0)
        self.position_slider.setToolTip("Seek through this audio")
        self.position_slider.seekRequested.connect(
            lambda value: self.seek_requested.emit(self, value)
        )

        self.duration_label = QLabel(fmt_time(self.duration))
        self.duration_label.setObjectName("muted")
        self.duration_label.setFixedWidth(72)

        playback.addWidget(QLabel("Playback"))
        playback.addWidget(self.position_label)
        playback.addWidget(self.position_slider, 1)
        playback.addWidget(self.duration_label)
        outer.addLayout(playback)

        grid = QHBoxLayout()
        grid.setSpacing(10)

        grid.addWidget(QLabel("Volume"))
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(int(self.data.get("volume", 100)))
        self.volume.valueChanged.connect(self.on_changed)
        grid.addWidget(self.volume, 1)
        self.volume_value = QLabel()
        self.volume_value.setFixedWidth(42)
        grid.addWidget(self.volume_value)

        self.fade_in = QDoubleSpinBox()
        self.fade_in.setRange(0, 3600)
        self.fade_in.setDecimals(2)
        self.fade_in.setSuffix(" s")
        self.fade_in.setValue(float(self.data.get("fade_in", 0)))
        self.fade_in.valueChanged.connect(self.on_changed)
        grid.addWidget(QLabel("Fade in"))
        grid.addWidget(self.fade_in)

        self.fade_out = QDoubleSpinBox()
        self.fade_out.setRange(0, 3600)
        self.fade_out.setDecimals(2)
        self.fade_out.setSuffix(" s")
        self.fade_out.setValue(float(self.data.get("fade_out", 0)))
        self.fade_out.valueChanged.connect(self.on_changed)
        grid.addWidget(QLabel("Fade out"))
        grid.addWidget(self.fade_out)
        outer.addLayout(grid)

        range_row = QHBoxLayout()
        range_row.setSpacing(10)

        self.start = QDoubleSpinBox()
        self.start.setRange(0, max(self.duration, 0.01))
        self.start.setDecimals(2)
        self.start.setSuffix(" s")
        self.start.setValue(float(self.data.get("start", 0)))
        self.start.valueChanged.connect(self.range_changed)
        range_row.addWidget(QLabel("Play from"))
        range_row.addWidget(self.start)

        self.end = QDoubleSpinBox()
        self.end.setRange(0, max(self.duration, 0.01))
        self.end.setDecimals(2)
        self.end.setSuffix(" s")
        self.end.setValue(float(self.data.get("end", self.duration)))
        self.end.valueChanged.connect(self.range_changed)
        range_row.addWidget(QLabel("to"))
        range_row.addWidget(self.end)

        self.locate_btn = QPushButton("Locate")
        self.locate_btn.setObjectName("secondary")
        self.locate_btn.clicked.connect(self.locate)
        range_row.addStretch()
        range_row.addWidget(self.locate_btn)
        outer.addLayout(range_row)

    def refresh(self):
        self.number.setText(f"{self.index + 1:02d}")
        self.name.setText(Path(self.data["path"]).name)
        self.name.setToolTip(self.data["path"])
        self.volume_value.setText(f"{self.volume.value()}%")
        self.play_btn.setText("⏸" if self.play_btn.property("playing") else "▶")
        self.duration_label.setText(fmt_time(self.duration))

    def range_changed(self):
        if self.end.value() < self.start.value():
            self.end.blockSignals(True)
            self.end.setValue(self.start.value())
            self.end.blockSignals(False)
        self.data["start"] = self.start.value()
        self.data["end"] = self.end.value()
        self.changed.emit()

    def on_changed(self):
        self.data["volume"] = self.volume.value()
        self.data["fade_in"] = self.fade_in.value()
        self.data["fade_out"] = self.fade_out.value()
        self.data["mute"] = self.mute.isChecked()
        self.data["solo"] = self.solo.isChecked()
        self.changed.emit()

    def locate(self):
        path, _ = QFileDialog.getOpenFileName(self, "Locate Audio File")
        if not path:
            return
        try:
            info = probe(path)
            if not info["audio"]:
                raise RuntimeError("The selected file has no audio stream.")
        except Exception as e:
            QMessageBox.warning(self, "Invalid Audio", str(e))
            return
        self.data["path"] = str(Path(path).resolve())
        self.data["duration"] = info["duration"]
        self.duration = info["duration"]
        self.missing = False
        self.data["end"] = info["duration"]
        self.changed.emit()

    def set_playback_position(self, position, end=None):
        end = float(end if end is not None else self.data.get("end", self.duration))
        start = float(self.data.get("start", 0))
        span = max(0.01, end - start)
        current = max(start, min(float(position), end))
        value = int(((current - start) / span) * 1000)
        self.position_slider.blockSignals(True)
        self.position_slider.setValue(max(0, min(1000, value)))
        self.position_slider.blockSignals(False)
        self.position_label.setText(fmt_time(current))
        self.duration_label.setText(fmt_time(end))

    def to_dict(self):
        self.data["volume"] = self.volume.value()
        self.data["fade_in"] = self.fade_in.value()
        self.data["fade_out"] = self.fade_out.value()
        self.data["start"] = self.start.value()
        self.data["end"] = self.end.value()
        self.data["mute"] = self.mute.isChecked()
        self.data["solo"] = self.solo.isChecked()
        return dict(self.data)

class SeekSlider(QSlider):
    """Media seek slider: click anywhere to jump, drag to seek."""
    seekRequested = Signal(int)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.orientation() == Qt.Horizontal:
                x = max(0, min(event.position().x(), self.width()))
                ratio = x / max(1, self.width())
                value = self.minimum() + ratio * (self.maximum() - self.minimum())
                self.setValue(int(value))
                self.seekRequested.emit(int(value))
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            if self.orientation() == Qt.Horizontal:
                x = max(0, min(event.position().x(), self.width()))
                ratio = x / max(1, self.width())
                value = self.minimum() + ratio * (self.maximum() - self.minimum())
                self.setValue(int(value))
                self.seekRequested.emit(int(value))
                event.accept()
                return
        super().mouseMoveEvent(event)



class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MP3 Studio")
        self.setWindowIcon(QIcon(str(ROOT / "assets" / "mp3_studio.ico")))
        self.resize(1120, 800)
        self.setMinimumSize(920, 650)
        self.setStyleSheet(APP_STYLE)

        self.input_path = None
        self.media_info = None
        self.process = None
        self.output_path = None
        self.edit_undo = []
        self.edit_redo = []

        self.tracks = []
        self.mixer_tracks = []
        self.current_track_index = -1
        self.studio_playing = False
        self.current_track_started_at = 0
        self.fade_timer = QTimer(self)
        self.fade_timer.setInterval(50)
        self.fade_timer.timeout.connect(self.update_fade)
        self.fade_mode = None

        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(1.0)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.positionChanged.connect(self.player_position_changed)
        self.player.playbackStateChanged.connect(self.player_state_changed)

        self.build_ui()
        QApplication.instance().installEventFilter(self)
        self.build_menus()
        self.update_ffmpeg_status()

    def build_menus(self):
        edit = self.menuBar().addMenu("Edit")
        self.undo_action = QAction("Undo", self)
        self.undo_action.setShortcut("Ctrl+Z")
        self.undo_action.triggered.connect(self.editor_undo_action)
        edit.addAction(self.undo_action)

        self.redo_action = QAction("Redo", self)
        self.redo_action.setShortcut("Ctrl+Y")
        self.redo_action.triggered.connect(self.editor_redo_action)
        edit.addAction(self.redo_action)

        edit.addSeparator()
        reset = QAction("Reset Current Edit", self)
        reset.triggered.connect(self.editor_reset_edit)
        edit.addAction(reset)

        about = self.menuBar().addMenu("About")
        about_action = QAction("About MP3 Studio", self)
        about_action.triggered.connect(self.show_about_dialog)
        about.addAction(about_action)

        view = self.menuBar().addMenu("View")
        waveform = QAction("Waveform Editor", self)
        waveform.triggered.connect(lambda: self.switch_section(2))
        view.addAction(waveform)

    def show_about_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("About MP3 Studio")
        dialog.setWindowIcon(QIcon(str(ROOT / "assets" / "mp3_studio.ico")))
        dialog.setFixedSize(680, 520)
        dialog.setStyleSheet("""
            QDialog { background: #ffffff; }
            QLabel#aboutBrand { color: #1155cc; font-size: 32px; font-weight: 800; }
            QLabel#aboutVersion { color: #64748b; font-size: 15px; font-weight: 600; }
            QLabel#aboutHeading { color: #172033; font-size: 19px; font-weight: 800; }
            QLabel#aboutText { color: #475569; font-size: 14px; line-height: 1.5; }
            QLabel#aboutCredit { color: #172033; font-size: 15px; }
            QLabel#aboutCredit a { color: #1769e0; text-decoration: none; }
            QDialogButtonBox QPushButton { min-width: 90px; }
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(42, 34, 42, 28)
        layout.setSpacing(16)

        title = QLabel("MP3 Studio")
        title.setObjectName("aboutBrand")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        version = QLabel("Version 1.8")
        version.setObjectName("aboutVersion")
        version.setAlignment(Qt.AlignCenter)
        layout.addWidget(version)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #e2e8f0;")
        layout.addWidget(line)

        heading = QLabel("About the App")
        heading.setObjectName("aboutHeading")
        layout.addWidget(heading)

        text = QLabel(
            "MP3 Studio is a desktop audio toolkit built to make everyday audio work "
            "simple and convenient. It brings audio extraction, playback, editing, "
            "merging, waveform visualization, and metadata editing together in one app."
        )
        text.setObjectName("aboutText")
        text.setWordWrap(True)
        layout.addWidget(text)

        creator = QLabel(
            '<b>Created by Nicemon Dominic</b><br><br>'
            'GitHub: <a href="https://github.com/nicemondominic">'
            'github.com/nicemondominic</a><br>'
            'Built with Python, PySide6 and FFmpeg.'
        )
        creator.setObjectName("aboutCredit")
        creator.setOpenExternalLinks(True)
        creator.setWordWrap(True)
        layout.addWidget(creator)

        layout.addStretch()

        copyright_label = QLabel("© 2026 Nicemon Dominic · MP3 Studio")
        copyright_label.setObjectName("aboutVersion")
        copyright_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(copyright_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)

        dialog.exec()

    def build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top = QFrame()
        top.setObjectName("topbar")
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(24, 16, 24, 10)
        top_layout.setSpacing(12)

        first = QHBoxLayout()
        brand = QLabel("MP3 Studio")
        brand.setObjectName("brand")
        first.addWidget(brand)
        first.addStretch()
        self.status_label = QLabel("Checking FFmpeg…")
        self.status_label.setObjectName("status")
        first.addWidget(self.status_label)
        top_layout.addLayout(first)

        nav = QHBoxLayout()
        self.nav_buttons = []
        for index, text in enumerate(["Extract Audio", "Audio Studio", "Audio Editor", "Audio Merger", "Metadata Editor"]):
            b = QPushButton(text)
            b.setObjectName("nav")
            b.setProperty("active", index == 0)
            b.clicked.connect(lambda checked=False, i=index: self.switch_section(i))
            self.nav_buttons.append(b)
            nav.addWidget(b)
        nav.addStretch()
        top_layout.addLayout(nav)
        root.addWidget(top)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.build_extract_page())
        self.stack.addWidget(self.build_studio_page())
        self.stack.addWidget(self.build_editor_page())
        self.stack.addWidget(self.build_mixer_page())
        self.stack.addWidget(self.build_metadata_page())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(self.stack)
        root.addWidget(scroll, 1)
        self.setCentralWidget(central)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Space:
            focus = QApplication.focusWidget()
            if isinstance(focus, (QLineEdit, QDoubleSpinBox, QComboBox)):
                return False

            if hasattr(self, "player") and self.stack.currentIndex() in (0, 1, 2):
                state = self.player.playbackState()
                if state == QMediaPlayer.PlayingState:
                    self.player.pause()
                else:
                    self.player.play()
                return True

            if self.stack.currentIndex() == 3:
                player = getattr(self, "mixer_preview_player", None)
                if player and player.source() and not player.source().isEmpty():
                    if player.playbackState() == QMediaPlayer.PlayingState:
                        player.pause()
                    else:
                        player.play()
                    return True

                final = getattr(self, "mixer_final_player", None)
                if final and final.source() and not final.source().isEmpty():
                    if final.playbackState() == QMediaPlayer.PlayingState:
                        final.pause()
                    else:
                        final.play()
                    return True

        return super().eventFilter(obj, event)

    def switch_section(self, index):
        self.stack.setCurrentIndex(index)
        for i, b in enumerate(self.nav_buttons):
            b.setProperty("active", i == index)
            b.style().unpolish(b)
            b.style().polish(b)


    def build_metadata_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(34, 26, 34, 32)
        layout.setSpacing(14)

        title = QLabel("Metadata Editor")
        title.setObjectName("bigTitle")
        layout.addWidget(title)
        sub = QLabel("Read and edit title, artist, album, genre, year and track information without changing the audio.")
        sub.setObjectName("muted")
        layout.addWidget(sub)

        row = QHBoxLayout()
        choose = QPushButton("Select Audio")
        choose.clicked.connect(self.metadata_select)
        row.addWidget(choose)
        self.metadata_file = QLabel("No audio selected")
        self.metadata_file.setObjectName("muted")
        row.addWidget(self.metadata_file, 1)
        save = QPushButton("Save Metadata")
        save.clicked.connect(self.metadata_save)
        row.addWidget(save)
        layout.addLayout(row)

        self.metadata_waveform = WaveformWidget()
        layout.addWidget(self.metadata_waveform)

        box = QGroupBox("Tags")
        form = QFormLayout(box)
        self.metadata_title = QLineEdit()
        self.metadata_artist = QLineEdit()
        self.metadata_album = QLineEdit()
        self.metadata_genre = QLineEdit()
        self.metadata_year = QLineEdit()
        self.metadata_track = QLineEdit()
        self.metadata_comment = QLineEdit()
        for label, widget in [
            ("Title", self.metadata_title), ("Artist", self.metadata_artist),
            ("Album", self.metadata_album), ("Genre", self.metadata_genre),
            ("Year", self.metadata_year), ("Track", self.metadata_track),
            ("Comment", self.metadata_comment)
        ]:
            form.addRow(label, widget)
        layout.addWidget(box)
        layout.addStretch()
        self.metadata_path = None
        return page

    def metadata_select(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Audio", "", "Audio Files (*.*)"
        )
        if not path:
            return
        self.metadata_path = Path(path)
        self.metadata_file.setText(str(self.metadata_path))
        try:
            info = probe(path)
            self.metadata_waveform.set_audio(path, info["duration"])
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries",
                 "format_tags=title,artist,album,genre,date,track,comment",
                 "-of", "json", path],
                capture_output=True, text=True, encoding="utf-8", errors="replace"
            )
            tags = json.loads(result.stdout or "{}").get("format", {}).get("tags", {})
            self.metadata_title.setText(tags.get("title", ""))
            self.metadata_artist.setText(tags.get("artist", ""))
            self.metadata_album.setText(tags.get("album", ""))
            self.metadata_genre.setText(tags.get("genre", ""))
            self.metadata_year.setText(tags.get("date", ""))
            self.metadata_track.setText(tags.get("track", ""))
            self.metadata_comment.setText(tags.get("comment", ""))
        except Exception as e:
            QMessageBox.warning(self, "Metadata", str(e))

    def metadata_save(self):
        if not self.metadata_path:
            QMessageBox.warning(self, "Metadata", "Select an audio file first.")
            return
        tags = {
            "title": self.metadata_title.text(),
            "artist": self.metadata_artist.text(),
            "album": self.metadata_album.text(),
            "genre": self.metadata_genre.text(),
            "date": self.metadata_year.text(),
            "track": self.metadata_track.text(),
            "comment": self.metadata_comment.text(),
        }
        # Write a new file to keep the source audio untouched.
        out = OUTPUT_DIR / f"{self.metadata_path.stem}_metadata{self.metadata_path.suffix}"
        cmd = ["ffmpeg", "-hide_banner", "-y", "-i", str(self.metadata_path)]
        for k, v in tags.items():
            if v:
                cmd += ["-metadata", f"{k}={v}"]
        cmd += ["-map", "0", "-c", "copy", str(out)]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode == 0:
            QMessageBox.information(self, "Metadata Saved", f"Saved:\n{out}")
        else:
            QMessageBox.critical(self, "Metadata Error", result.stderr[-1500:] or "FFmpeg failed.")

    # ---------- Phase 1 ----------
    def build_extract_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(42, 28, 42, 32)
        layout.setSpacing(16)
        page.setMinimumWidth(760)

        title = QLabel("Extract Audio")
        title.setObjectName("bigTitle")
        layout.addWidget(title)
        sub = QLabel("Extract audio from almost any media format using FFmpeg.")
        sub.setObjectName("muted")
        layout.addWidget(sub)

        self.dropzone = DropLabel(self.load_file)
        layout.addWidget(self.dropzone)
        hint = QLabel("Input can be video or audio. FFmpeg handles supported containers and codecs.")
        hint.setObjectName("muted")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        choose_row = QHBoxLayout()
        choose = QPushButton("Select File")
        choose.clicked.connect(self.select_file)
        choose_row.addWidget(choose)
        self.file_label = QLabel("No file selected")
        self.file_label.setObjectName("muted")
        self.file_label.setWordWrap(True)
        self.file_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        choose_row.addWidget(self.file_label, 1)
        layout.addLayout(choose_row)

        self.extract_waveform = WaveformWidget()
        self.extract_waveform.set_audio("", 0)
        self.extract_waveform.seekRequested.connect(self.extract_seek)
        layout.addWidget(self.extract_waveform)

        info = QGroupBox("Input Information")
        info_layout = QFormLayout(info)
        info_layout.setHorizontalSpacing(28)
        info_layout.setVerticalSpacing(7)
        self.info_file = QLabel("—")
        self.info_duration = QLabel("—")
        self.info_format = QLabel("—")
        self.info_audio = QLabel("—")
        self.info_video = QLabel("—")
        info_layout.addRow("File", self.info_file)
        info_layout.addRow("Duration", self.info_duration)
        info_layout.addRow("Container", self.info_format)
        info_layout.addRow("Audio", self.info_audio)
        info_layout.addRow("Video", self.info_video)
        layout.addWidget(info)

        options = QGroupBox("Output")
        form = QFormLayout(options)
        form.setHorizontalSpacing(28)
        form.setVerticalSpacing(7)

        self.format_combo = QComboBox()
        self.format_combo.addItems(["MP3", "WAV", "FLAC", "AAC", "M4A", "OGG", "OPUS", "AIFF"])
        self.format_combo.currentTextChanged.connect(self.update_format_options)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("output_audio")
        self.bitrate_combo = QComboBox()
        self.bitrate_combo.addItems(["128k", "160k", "192k", "256k", "320k"])
        self.bitrate_combo.setCurrentText("192k")
        self.sample_combo = QComboBox()
        self.sample_combo.addItems(["22050", "32000", "44100", "48000", "96000"])
        self.sample_combo.setCurrentText("44100")
        self.channels_combo = QComboBox()
        self.channels_combo.addItems(["1", "2"])
        self.channels_combo.setCurrentText("2")
        self.bit_depth_combo = QComboBox()
        self.bit_depth_combo.addItems(["16", "24", "32"])
        self.compression_combo = QComboBox()
        self.compression_combo.addItems([str(i) for i in range(13)])
        self.compression_combo.setCurrentText("5")
        self.start_spin = QDoubleSpinBox()
        self.start_spin.setRange(0, 999999)
        self.start_spin.setDecimals(2)
        self.start_spin.setSuffix(" sec")
        self.end_spin = QDoubleSpinBox()
        self.end_spin.setRange(0, 999999)
        self.end_spin.setDecimals(2)
        self.end_spin.setSuffix(" sec")

        form.addRow("Output format", self.format_combo)
        form.addRow("Output name", self.name_edit)
        form.addRow("Bitrate", self.bitrate_combo)
        form.addRow("Sample rate", self.sample_combo)
        form.addRow("Channels", self.channels_combo)
        form.addRow("Bit depth", self.bit_depth_combo)
        form.addRow("FLAC compression", self.compression_combo)
        form.addRow("Start", self.start_spin)
        form.addRow("End", self.end_spin)
        form.addRow("Output folder", QLabel("assets/output/"))
        layout.addWidget(options)

        controls = QHBoxLayout()
        self.preview_button = QPushButton("▶ Preview")
        self.preview_button.setObjectName("secondary")
        self.preview_button.clicked.connect(self.toggle_preview)
        self.preview_button.setEnabled(False)
        controls.addWidget(self.preview_button)
        open_btn = QPushButton("Open Output Folder")
        open_btn.setObjectName("secondary")
        open_btn.clicked.connect(self.open_output_folder)
        controls.addWidget(open_btn)
        controls.addStretch()
        self.extract_button = QPushButton("Extract Audio")
        self.extract_button.clicked.connect(self.start_extraction)
        controls.addWidget(self.extract_button)
        layout.addLayout(controls)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.progress_label = QLabel("Ready")
        self.progress_label.setObjectName("muted")
        layout.addWidget(self.progress_label)

        history = QGroupBox("Recent Exports")
        h = QHBoxLayout(history)
        self.history = QListWidget()
        self.history.setMaximumHeight(100)
        h.addWidget(self.history)
        layout.addWidget(history)
        self.update_format_options()
        return page

    def update_ffmpeg_status(self):
        self.status_label.setText("● FFmpeg Ready" if ffmpeg_available() else "● FFmpeg Not Found")

    def update_format_options(self):
        fmt = self.format_combo.currentText().lower()
        audio = fmt in {"mp3", "aac", "m4a", "ogg", "opus"}
        pcm = fmt in {"wav", "aiff"}
        flac = fmt == "flac"
        for widget in [self.bitrate_combo, self.sample_combo, self.channels_combo]:
            widget.setEnabled(audio or pcm or flac)
        self.bit_depth_combo.setEnabled(pcm)
        self.compression_combo.setEnabled(flac)

    def select_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Video or Audio", "", "Media Files (*)")
        if path:
            self.load_file(path)

    def load_file(self, path):
        try:
            info = probe(str(path))
        except Exception as e:
            QMessageBox.critical(self, "Unable to Load File", str(e))
            return
        if not info["audio"]:
            QMessageBox.warning(self, "No Audio Stream", "This file does not contain an audio stream.")
            return
        self.input_path = str(Path(path).resolve())
        self.media_info = info
        self.file_label.setText(Path(path).name)
        self.info_file.setText(Path(path).name)
        self.info_duration.setText(fmt_time(info["duration"]))
        self.info_format.setText(info["format"])
        a = info["audio"]
        audio_text = a.get("codec_name", "Unknown").upper()
        if a.get("sample_rate"):
            audio_text += f' • {int(a["sample_rate"]):,} Hz'
        if a.get("channels"):
            audio_text += f' • {a["channels"]} ch'
        self.info_audio.setText(audio_text)
        v = info["video"]
        self.info_video.setText(
            f'{v.get("codec_name", "Unknown").upper()} • {v.get("width", "?")} × {v.get("height", "?")}'
            if v else "No video stream"
        )
        self.name_edit.setText(Path(path).stem + "_audio")
        self.start_spin.setValue(0)
        self.end_spin.setValue(info["duration"])
        self.end_spin.setMaximum(max(info["duration"], 0.01))
        self.start_spin.setMaximum(max(info["duration"], 0.01))
        self.preview_button.setEnabled(True)
        self.progress.setValue(0)
        self.progress_label.setText(f"Loaded • {fmt_size(info['size'])}")
        self.player.setSource(QUrl.fromLocalFile(self.input_path))

    def toggle_preview(self):
        if not self.input_path:
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.preview_button.setText("▶ Preview")
        else:
            self.player.play()
            self.preview_button.setText("⏸ Pause")

    def open_output_folder(self):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(OUTPUT_DIR))

    def unique_output(self, base, extension):
        candidate = OUTPUT_DIR / f"{base}.{extension}"
        i = 1
        while candidate.exists():
            candidate = OUTPUT_DIR / f"{base} ({i}).{extension}"
            i += 1
        return candidate

    def start_extraction(self):
        if not self.input_path:
            QMessageBox.warning(self, "Select a File", "Choose a video or audio file first.")
            return
        if not ffmpeg_available():
            QMessageBox.critical(self, "FFmpeg Required", "FFmpeg and ffprobe were not found on PATH.")
            return
        start = self.start_spin.value()
        end = self.end_spin.value()
        duration = self.media_info["duration"]
        if end <= start:
            QMessageBox.warning(self, "Invalid Range", "End time must be greater than start time.")
            return
        end = min(end, duration)
        name = self.name_edit.text().strip() or Path(self.input_path).stem + "_audio"
        for char in '<>:"/\\|?*':
            name = name.replace(char, "_")
        fmt = self.format_combo.currentText().lower()
        output = self.unique_output(name, fmt)
        self.output_path = output
        cmd = build_command(
            self.input_path, str(output), fmt,
            start=start, end=end,
            bitrate=self.bitrate_combo.currentText(),
            sample_rate=self.sample_combo.currentText(),
            channels=self.channels_combo.currentText(),
            bit_depth=self.bit_depth_combo.currentText(),
            compression=self.compression_combo.currentText()
        )
        cmd.insert(1, "-progress")
        cmd.insert(2, "pipe:1")
        cmd.insert(3, "-nostats")
        self.player.stop()
        self.preview_button.setText("▶ Preview")
        self.extract_button.setEnabled(False)
        self.progress.setValue(0)
        self.progress_label.setText("Extracting…")
        self.process = QProcess(self)
        self.process.setProgram(cmd[0])
        self.process.setArguments(cmd[1:])
        self.process.readyReadStandardOutput.connect(self.read_process_output)
        self.process.finished.connect(self.process_finished)
        self.process.errorOccurred.connect(self.process_error)
        self.process.start()

    def read_process_output(self):
        data = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        for line in data.splitlines():
            if line.startswith("out_time_ms="):
                try:
                    seconds = int(line.split("=", 1)[1]) / 1_000_000
                    total = max(0.01, self.end_spin.value() - self.start_spin.value())
                    self.progress.setValue(max(0, min(100, int(seconds / total * 100))))
                except ValueError:
                    pass
            elif line.strip() == "progress=end":
                self.progress.setValue(100)

    def process_error(self, error):
        if error == QProcess.FailedToStart:
            self.extract_button.setEnabled(True)
            self.progress_label.setText("Failed to start FFmpeg.")
            QMessageBox.critical(self, "FFmpeg Error", "FFmpeg could not be started.")

    def process_finished(self, exit_code, exit_status):
        self.extract_button.setEnabled(True)
        if exit_code == 0 and self.output_path and self.output_path.exists():
            self.progress.setValue(100)
            self.progress_label.setText(f"Done • {self.output_path.name}")
            self.history.insertItem(0, QListWidgetItem(f"✓ {self.output_path.name}"))
        else:
            self.progress_label.setText("Extraction failed.")
            QMessageBox.critical(self, "Extraction Failed", "FFmpeg could not complete the extraction.")
        self.process = None

    # ---------- Audio Editor ----------
    def build_editor_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(34, 26, 34, 32)
        layout.setSpacing(14)
        page.setMinimumWidth(760)

        title = QLabel("Audio Editor")
        title.setObjectName("bigTitle")
        layout.addWidget(title)

        sub = QLabel("Load one audio file, edit its range and sound, then export a new file.")
        sub.setObjectName("muted")
        layout.addWidget(sub)

        file_row = QHBoxLayout()
        select = QPushButton("Select Audio")
        select.clicked.connect(self.editor_select_file)
        file_row.addWidget(select)

        self.editor_file_label = QLabel("No audio selected")
        self.editor_file_label.setObjectName("muted")
        self.editor_file_label.setWordWrap(True)
        file_row.addWidget(self.editor_file_label, 1)

        open_out = QPushButton("Open Output Folder")
        open_out.setObjectName("secondary")
        open_out.clicked.connect(self.open_output_folder)
        file_row.addWidget(open_out)
        layout.addLayout(file_row)

        self.editor_wave = QFrame()
        self.editor_wave.setMinimumHeight(120)
        self.editor_wave.setStyleSheet(
            "QFrame { background:#f8fbff; border:1px solid #d9e5f5; border-radius:12px; }"
        )
        wave_layout = QVBoxLayout(self.editor_wave)
        wave_layout.setContentsMargins(18, 15, 18, 15)
        self.editor_wave_title = QLabel("Load an audio file to begin editing")
        self.editor_wave_title.setAlignment(Qt.AlignCenter)
        self.editor_wave_title.setObjectName("muted")
        wave_layout.addWidget(self.editor_wave_title)

        self.editor_waveform = WaveformWidget()
        self.editor_waveform.seekRequested.connect(self.editor_seek_seconds)
        wave_layout.addWidget(self.editor_waveform)
        layout.addWidget(self.editor_wave)

        info = QGroupBox("Audio Information")
        form = QFormLayout(info)
        self.editor_info_duration = QLabel("—")
        self.editor_info_format = QLabel("—")
        self.editor_info_codec = QLabel("—")
        self.editor_info_rate = QLabel("—")
        form.addRow("Duration", self.editor_info_duration)
        form.addRow("Format", self.editor_info_format)
        form.addRow("Codec", self.editor_info_codec)
        form.addRow("Sample rate", self.editor_info_rate)
        layout.addWidget(info)

        edit = QGroupBox("Edit")
        ef = QFormLayout(edit)
        ef.setHorizontalSpacing(28)
        ef.setVerticalSpacing(8)

        range_row = QHBoxLayout()
        self.editor_start = QDoubleSpinBox()
        self.editor_start.setRange(0, 999999)
        self.editor_start.setDecimals(2)
        self.editor_start.setSuffix(" sec")
        self.editor_start.valueChanged.connect(self.editor_update_range)
        range_row.addWidget(self.editor_start)
        range_row.addWidget(QLabel("to"))
        self.editor_end = QDoubleSpinBox()
        self.editor_end.setRange(0, 999999)
        self.editor_end.setDecimals(2)
        self.editor_end.setSuffix(" sec")
        self.editor_end.valueChanged.connect(self.editor_update_range)
        range_row.addWidget(self.editor_end)
        range_row.addStretch()
        ef.addRow("Trim range", range_row)

        self.editor_volume = QSlider(Qt.Horizontal)
        self.editor_volume.setRange(0, 200)
        self.editor_volume.setValue(100)
        self.editor_volume_label = QLabel("100%")
        self.editor_volume.valueChanged.connect(
            lambda v: self.editor_volume_label.setText(f"{v}%")
        )
        vol_row = QHBoxLayout()
        vol_row.addWidget(self.editor_volume, 1)
        vol_row.addWidget(self.editor_volume_label)
        ef.addRow("Volume", vol_row)

        fade_row = QHBoxLayout()
        self.editor_fade_in = QDoubleSpinBox()
        self.editor_fade_in.setRange(0, 3600)
        self.editor_fade_in.setDecimals(2)
        self.editor_fade_in.setSuffix(" sec")
        fade_row.addWidget(QLabel("In"))
        fade_row.addWidget(self.editor_fade_in)
        self.editor_fade_out = QDoubleSpinBox()
        self.editor_fade_out.setRange(0, 3600)
        self.editor_fade_out.setDecimals(2)
        self.editor_fade_out.setSuffix(" sec")
        fade_row.addWidget(QLabel("Out"))
        fade_row.addWidget(self.editor_fade_out)
        fade_row.addStretch()
        ef.addRow("Fade", fade_row)

        self.editor_speed = QComboBox()
        self.editor_speed.addItems(["0.50×", "0.75×", "1.00×", "1.25×", "1.50×", "1.75×", "2.00×"])
        self.editor_speed.setCurrentText("1.00×")
        ef.addRow("Speed", self.editor_speed)

        self.editor_normalize = QCheckBox("Normalize loudness")
        self.editor_normalize.setToolTip("Apply FFmpeg loudness normalization during export.")
        ef.addRow("", self.editor_normalize)
        layout.addWidget(edit)

        output = QGroupBox("Export")
        of = QFormLayout(output)
        self.editor_output_format = QComboBox()
        self.editor_output_format.addItems(["MP3", "WAV", "FLAC", "M4A", "AAC", "OGG", "OPUS", "AIFF"])
        self.editor_output_name = QLineEdit()
        self.editor_output_name.setPlaceholderText("edited_audio")
        self.editor_bitrate = QComboBox()
        self.editor_bitrate.addItems(["128k", "160k", "192k", "256k", "320k"])
        self.editor_bitrate.setCurrentText("192k")
        of.addRow("Format", self.editor_output_format)
        of.addRow("Output name", self.editor_output_name)
        of.addRow("Bitrate", self.editor_bitrate)
        of.addRow("Output folder", QLabel("assets/output/"))
        layout.addWidget(output)

        playback = QHBoxLayout()
        self.editor_position_label = QLabel("00:00")
        self.editor_position_label.setObjectName("muted")
        self.editor_position_label.setFixedWidth(72)
        self.editor_position_slider = SeekSlider(Qt.Horizontal)
        self.editor_position_slider.setRange(0, 1000)
        self.editor_position_slider.seekRequested.connect(self.editor_seek)
        self.editor_duration_label = QLabel("00:00")
        self.editor_duration_label.setObjectName("muted")
        self.editor_duration_label.setFixedWidth(72)
        playback.addWidget(QLabel("Playback"))
        playback.addWidget(self.editor_position_label)
        playback.addWidget(self.editor_position_slider, 1)
        playback.addWidget(self.editor_duration_label)
        layout.addLayout(playback)

        controls = QHBoxLayout()
        self.editor_preview = QPushButton("▶ Preview")
        self.editor_preview.setObjectName("secondary")
        self.editor_preview.clicked.connect(self.editor_toggle_preview)
        self.editor_preview.setEnabled(False)
        controls.addWidget(self.editor_preview)

        controls.addStretch()
        self.editor_export = QPushButton("Export Edited Audio")
        self.editor_export.clicked.connect(self.editor_export_audio)
        self.editor_export.setEnabled(False)
        controls.addWidget(self.editor_export)
        layout.addLayout(controls)

        self.editor_progress = QProgressBar()
        self.editor_progress.setValue(0)
        layout.addWidget(self.editor_progress)
        self.editor_status = QLabel("Ready")
        self.editor_status.setObjectName("muted")
        layout.addWidget(self.editor_status)

        return page

    def editor_select_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Audio File", "",
            "Audio Files (*.mp3 *.wav *.flac *.aac *.m4a *.ogg *.opus *.wma *.aiff *.aif *.alac *.amr);;All Files (*)"
        )
        if path:
            self.editor_load_file(path)

    def editor_load_file(self, path):
        try:
            info = probe(str(path))
            if not info["audio"]:
                raise RuntimeError("The selected file does not contain an audio stream.")
        except Exception as e:
            QMessageBox.critical(self, "Unable to Load Audio", str(e))
            return

        self.editor_input_path = str(Path(path).resolve())
        self.editor_info = info
        duration = float(info["duration"])

        self.editor_file_label.setText(Path(path).name)
        self.editor_wave_title.setText(
            f"Loaded • {Path(path).name} • {fmt_time(duration)}"
        )
        self.editor_info_duration.setText(fmt_time(duration))
        self.editor_waveform.set_audio(path, duration)
        self.editor_info_format.setText(info["format"])
        audio = info["audio"]
        self.editor_info_codec.setText(audio.get("codec_name", "Unknown").upper())
        self.editor_info_rate.setText(
            f'{int(audio["sample_rate"]):,} Hz' if audio.get("sample_rate") else "Unknown"
        )

        self.editor_start.setMaximum(max(duration, 0.01))
        self.editor_end.setMaximum(max(duration, 0.01))
        self.editor_start.setValue(0)
        self.editor_end.setValue(duration)
        self.editor_fade_in.setValue(0)
        self.editor_fade_out.setValue(0)
        self.editor_output_name.setText(Path(path).stem + "_edited")
        self.editor_preview.setEnabled(True)
        self.editor_export.setEnabled(True)
        self.editor_progress.setValue(0)
        self.editor_status.setText("Ready to edit")
        self.editor_player = self.player
        self.editor_player.setSource(QUrl.fromLocalFile(self.editor_input_path))
        self.editor_position_slider.setValue(0)
        self.editor_position_label.setText("00:00")
        self.editor_duration_label.setText(fmt_time(duration))
        try:
            self.player.positionChanged.disconnect(self.editor_position_changed)
        except (RuntimeError, TypeError):
            pass
        self.player.positionChanged.connect(self.editor_position_changed)

    def editor_update_range(self):
        if not hasattr(self, "editor_end"):
            return
        if self.editor_end.value() < self.editor_start.value():
            self.editor_end.blockSignals(True)
            self.editor_end.setValue(self.editor_start.value())
            self.editor_end.blockSignals(False)

    def editor_toggle_preview(self):
        if not getattr(self, "editor_input_path", None):
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.editor_preview.setText("▶ Preview")
        else:
            start = self.editor_start.value()
            self.player.setPosition(int(start * 1000))
            self.player.play()
            self.editor_preview.setText("⏸ Pause")

    def _editor_snapshot(self):
        if not hasattr(self, "editor_start"):
            return None
        return {
            "start": self.editor_start.value(),
            "end": self.editor_end.value(),
            "volume": self.editor_volume.value(),
            "fade_in": self.editor_fade_in.value(),
            "fade_out": self.editor_fade_out.value(),
            "speed": self.editor_speed.value(),
            "normalize": self.editor_normalize.isChecked(),
        }

    def _restore_editor_snapshot(self, snap):
        if not snap:
            return
        self.editor_start.setValue(snap["start"])
        self.editor_end.setValue(snap["end"])
        self.editor_volume.setValue(snap["volume"])
        self.editor_fade_in.setValue(snap["fade_in"])
        self.editor_fade_out.setValue(snap["fade_out"])
        self.editor_speed.setValue(snap["speed"])
        self.editor_normalize.setChecked(snap["normalize"])

    def editor_capture_edit(self):
        snap = self._editor_snapshot()
        if snap:
            self.edit_undo.append(snap)
            self.edit_redo.clear()
            self.undo_action.setEnabled(bool(self.edit_undo))
            self.redo_action.setEnabled(False)

    def editor_undo_action(self):
        if not self.edit_undo:
            return
        current = self._editor_snapshot()
        self.edit_redo.append(current)
        self._restore_editor_snapshot(self.edit_undo.pop())
        self.undo_action.setEnabled(bool(self.edit_undo))
        self.redo_action.setEnabled(True)

    def editor_redo_action(self):
        if not self.edit_redo:
            return
        current = self._editor_snapshot()
        self.edit_undo.append(current)
        self._restore_editor_snapshot(self.edit_redo.pop())
        self.undo_action.setEnabled(bool(self.edit_undo))
        self.redo_action.setEnabled(bool(self.edit_redo))

    def editor_reset_edit(self):
        if not self.editor_info:
            return
        self.editor_capture_edit()
        duration = float(self.editor_info.get("duration", 0))
        self.editor_start.setValue(0)
        self.editor_end.setValue(duration)
        self.editor_volume.setValue(100)
        self.editor_fade_in.setValue(0)
        self.editor_fade_out.setValue(0)
        self.editor_speed.setValue(1.0)
        self.editor_normalize.setChecked(False)

    def editor_export_audio(self):
        if not getattr(self, "editor_input_path", None):
            return

        start = self.editor_start.value()
        end = self.editor_end.value()
        if end <= start:
            QMessageBox.warning(
                self, "Invalid Range",
                "End time must be greater than start time."
            )
            return

        name = self.editor_output_name.text().strip()
        if not name:
            name = Path(self.editor_input_path).stem + "_edited"

        for char in '<>:"/\\|?*':
            name = name.replace(char, "_")

        fmt = self.editor_output_format.currentText().lower()
        output = self.unique_output(name, fmt)
        speed = float(self.editor_speed.currentText().replace("×", ""))

        try:
            cmd = build_edit_command(
                self.editor_input_path,
                str(output),
                fmt,
                start=start,
                end=end,
                volume=self.editor_volume.value(),
                fade_in=min(self.editor_fade_in.value(), end - start),
                fade_out=min(self.editor_fade_out.value(), end - start),
                speed=speed,
                normalize=self.editor_normalize.isChecked(),
                bitrate=self.editor_bitrate.currentText()
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))
            return

        cmd.insert(1, "-progress")
        cmd.insert(2, "pipe:1")
        cmd.insert(3, "-nostats")

        self.player.stop()
        self.editor_preview.setText("▶ Preview")

        self.editor_output_path = output
        self.editor_process = QProcess(self)
        self.editor_process.setProgram(cmd[0])
        self.editor_process.setArguments(cmd[1:])
        self.editor_process.readyReadStandardOutput.connect(
            self.editor_read_progress
        )
        self.editor_process.finished.connect(
            self.editor_export_finished
        )
        self.editor_process.errorOccurred.connect(
            self.editor_export_error
        )

        self.editor_export.setEnabled(False)
        self.editor_progress.setValue(0)
        self.editor_status.setText("Exporting edited audio…")
        self.editor_process.start()

    def editor_read_progress(self):
        if not getattr(self, "editor_process", None):
            return

        data = bytes(
            self.editor_process.readAllStandardOutput()
        ).decode("utf-8", errors="replace")

        total = max(
            0.01,
            self.editor_end.value() - self.editor_start.value()
        )

        for line in data.splitlines():
            if line.startswith("out_time_ms="):
                try:
                    seconds = int(line.split("=", 1)[1]) / 1_000_000
                    percent = int(seconds / total * 100)
                    self.editor_progress.setValue(
                        max(0, min(100, percent))
                    )
                except ValueError:
                    pass

    def editor_export_error(self, error):
        if error == QProcess.FailedToStart:
            self.editor_export.setEnabled(True)
            self.editor_status.setText("FFmpeg could not be started.")
            QMessageBox.critical(
                self,
                "FFmpeg Error",
                "FFmpeg could not be started."
            )

    def editor_export_finished(self, exit_code, exit_status):
        self.editor_export.setEnabled(True)

        if (
            exit_code == 0
            and getattr(self, "editor_output_path", None)
            and self.editor_output_path.exists()
        ):
            self.editor_progress.setValue(100)
            self.editor_status.setText(
                f"Done • {self.editor_output_path.name}"
            )
        else:
            self.editor_status.setText("Export failed.")
            QMessageBox.critical(
                self,
                "Export Failed",
                "FFmpeg could not export the edited audio."
            )

        self.editor_process = None

    def editor_seek_seconds(self, seconds):
        duration = float(self.editor_info.get("duration", 0) if getattr(self, "editor_info", None) else 0)
        if duration <= 0:
            return
        start = float(self.editor_start.value())
        end = float(self.editor_end.value())
        seconds = max(start, min(end, float(seconds)))
        self.player.setPosition(int(seconds * 1000))
        self.player.play()

    def extract_seek(self, seconds):
        # Extract page is informational; seeking the source is intentionally
        # lightweight and does not alter extraction settings.
        if self.input_path:
            self.player.setSource(QUrl.fromLocalFile(str(self.input_path)))
            self.player.setPosition(int(seconds * 1000))
            self.player.play()

    def editor_seek(self, value):
        if not getattr(self, "editor_input_path", None):
            return
        duration = max(0.01, float(self.editor_info.get("duration", 0)))
        start = self.editor_start.value()
        end = self.editor_end.value()
        position = start + (max(0, min(1000, value)) / 1000.0) * max(0.0, end - start)
        was_playing = self.player.playbackState() == QMediaPlayer.PlayingState
        self.player.setPosition(int(min(position, duration) * 1000))
        if was_playing:
            self.player.play()

    def editor_position_changed(self, position):
        if not getattr(self, "editor_input_path", None):
            return
        if self.stack.currentIndex() != 2:
            return
        current = position / 1000.0
        start = self.editor_start.value()
        end = self.editor_end.value()
        if current < start - 0.05:
            return
        current = min(current, end)
        span = max(0.01, end - start)
        value = int(max(0, min(1000, ((current - start) / span) * 1000)))
        self.editor_position_slider.blockSignals(True)
        self.editor_position_slider.setValue(value)
        self.editor_position_slider.blockSignals(False)
        self.editor_position_label.setText(fmt_time(current))
        self.editor_duration_label.setText(fmt_time(end))
        if current >= end - 0.03 and self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.editor_preview.setText("▶ Preview")

    def build_mixer_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(34, 26, 34, 32)
        layout.setSpacing(14)
        page.setMinimumWidth(760)

        title = QLabel("Audio Merger")
        title.setObjectName("bigTitle")
        layout.addWidget(title)
        sub = QLabel("Arrange audio files sequentially, overlap them when needed, add crossfades, and export one merged file.")
        sub.setObjectName("muted")
        layout.addWidget(sub)

        toolbar = QHBoxLayout()
        add = QPushButton("+ Add Audio")
        add.clicked.connect(self.mixer_add_files)
        toolbar.addWidget(add)
        clear = QPushButton("Clear All")
        clear.setObjectName("danger")
        clear.clicked.connect(self.mixer_clear)
        toolbar.addWidget(clear)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        settings = QGroupBox("Mixer")
        s = QHBoxLayout(settings)
        self.mixer_normalize = QCheckBox("Normalize output")
        s.addWidget(self.mixer_normalize)
        s.addWidget(QLabel("Crossfade"))
        self.mixer_crossfade = QDoubleSpinBox()
        self.mixer_crossfade.setRange(0, 120)
        self.mixer_crossfade.setDecimals(2)
        self.mixer_crossfade.setSuffix(" s")
        self.mixer_crossfade.setValue(0)
        self.mixer_crossfade.setToolTip("Crossfade adjacent sequential clips")
        s.addWidget(self.mixer_crossfade)
        s.addWidget(QLabel("Master Volume"))
        self.mixer_master = QSlider(Qt.Horizontal)
        self.mixer_master.setRange(0, 100)
        self.mixer_master.setValue(100)
        self.mixer_master.setMaximumWidth(190)
        self.mixer_master.valueChanged.connect(
            lambda v: self.mixer_master_label.setText(f"{v}%")
        )
        s.addWidget(self.mixer_master)
        self.mixer_master_label = QLabel("100%")
        self.mixer_master_label.setFixedWidth(40)
        s.addWidget(self.mixer_master_label)
        s.addStretch()
        self.mixer_total = QLabel("0 tracks")
        self.mixer_total.setObjectName("muted")
        s.addWidget(self.mixer_total)
        layout.addWidget(settings)

        transport = QHBoxLayout()
        self.mixer_play = QPushButton("▶ Play Mix")
        self.mixer_play.clicked.connect(self.mixer_toggle_play)
        transport.addWidget(self.mixer_play)
        stop = QPushButton("■ Stop")
        stop.setObjectName("secondary")
        stop.clicked.connect(self.mixer_stop)
        transport.addWidget(stop)
        transport.addStretch()
        layout.addLayout(transport)

        final_playback = QGroupBox("Final Mix Preview")
        fp = QVBoxLayout(final_playback)

        self.mixer_final_waveform = WaveformWidget()
        self.mixer_final_waveform.seekRequested.connect(
            lambda sec: self.mixer_seek_final(
                int(sec / max(0.001, float(self.mixer_final_duration or self.mixer_mix_duration())) * 1000)
            )
        )
        fp.addWidget(self.mixer_final_waveform)
        final_top = QHBoxLayout()

        self.mixer_final_play = QPushButton("▶ Play Final Mix")
        self.mixer_final_play.clicked.connect(self.mixer_toggle_final_preview)
        final_top.addWidget(self.mixer_final_play)

        self.mixer_final_time = QLabel("00:00 / 00:00")
        self.mixer_final_time.setObjectName("muted")
        final_top.addWidget(self.mixer_final_time)
        final_top.addStretch()

        self.mixer_final_slider = SeekSlider(Qt.Horizontal)
        self.mixer_final_slider.setRange(0, 1000)
        self.mixer_final_slider.seekRequested.connect(self.mixer_seek_final)
        fp.addLayout(final_top)
        fp.addWidget(self.mixer_final_slider)
        layout.addWidget(final_playback)

        self.mixer_scroll = QScrollArea()
        self.mixer_scroll.setWidgetResizable(True)
        self.mixer_scroll.setFrameShape(QFrame.NoFrame)
        self.mixer_container = QWidget()
        self.mixer_layout = QVBoxLayout(self.mixer_container)
        self.mixer_layout.setContentsMargins(0, 2, 0, 3)
        self.mixer_layout.setSpacing(9)
        self.mixer_empty = QLabel("No mixer tracks yet.\nClick + Add Audio to start.")
        self.mixer_empty.setAlignment(Qt.AlignCenter)
        self.mixer_empty.setObjectName("muted")
        self.mixer_layout.addWidget(self.mixer_empty)
        self.mixer_layout.addStretch()
        self.mixer_scroll.setWidget(self.mixer_container)
        layout.addWidget(self.mixer_scroll, 1)

        export = QGroupBox("Export Mix")
        ef = QFormLayout(export)
        self.mixer_format = QComboBox()
        self.mixer_format.addItems(["MP3", "WAV", "FLAC", "M4A", "AAC", "OGG", "OPUS", "AIFF"])
        self.mixer_name = QLineEdit()
        self.mixer_name.setText("mixed_audio")
        self.mixer_bitrate = QComboBox()
        self.mixer_bitrate.addItems(["128k", "160k", "192k", "256k", "320k"])
        self.mixer_bitrate.setCurrentText("192k")
        ef.addRow("Format", self.mixer_format)
        ef.addRow("Output name", self.mixer_name)
        ef.addRow("Bitrate", self.mixer_bitrate)

        saved_row = QHBoxLayout()
        self.mixer_saved_path = QLineEdit("assets/output/")
        self.mixer_saved_path.setReadOnly(True)
        browse_saved = QPushButton("Choose Save Location")
        browse_saved.setObjectName("secondary")
        browse_saved.clicked.connect(self.mixer_choose_save_location)
        saved_row.addWidget(self.mixer_saved_path, 1)
        saved_row.addWidget(browse_saved)
        ef.addRow("Save mixed audio", saved_row)
        layout.addWidget(export)

        bottom = QHBoxLayout()
        bottom.addStretch()
        self.mixer_export = QPushButton("Export Mix")
        self.mixer_export.clicked.connect(self.mixer_export_audio)
        bottom.addWidget(self.mixer_export)
        layout.addLayout(bottom)

        self.mixer_progress = QProgressBar()
        self.mixer_progress.setValue(0)
        layout.addWidget(self.mixer_progress)
        self.mixer_status = QLabel("Ready")
        self.mixer_status.setObjectName("muted")
        layout.addWidget(self.mixer_status)

        self.mixer_players = []
        self.mixer_playing = False
        self.mixer_preview_player = None
        self.mixer_preview_audio = None
        self.mixer_final_player = QMediaPlayer(self)
        self.mixer_final_audio = QAudioOutput(self)
        self.mixer_final_audio.setVolume(self.mixer_master.value() / 100.0)
        self.mixer_master.valueChanged.connect(
            lambda v: self.mixer_final_audio.setVolume(v / 100.0)
        )
        self.mixer_final_player.setAudioOutput(self.mixer_final_audio)
        self.mixer_final_player.positionChanged.connect(self.mixer_final_position_changed)
        self.mixer_final_player.playbackStateChanged.connect(self.mixer_final_state_changed)
        self.mixer_final_duration = 0
        self.mixer_final_pending_seek = None
        self.mixer_preview_index = -1
        return page

    def mixer_add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Mixer Audio", "", "Audio Files (*);;Common Audio (*.mp3 *.wav *.flac *.aac *.m4a *.ogg *.opus *.wma *.aiff)"
        )
        if not paths:
            return
        # New mixer files are placed sequentially by default.
        # Each new clip starts exactly when the previous clip ends instead of
        # defaulting to timeline position 0 and overlapping it.
        timeline_cursor = self.mixer_mix_duration() if self.mixer_tracks else 0.0

        for path in paths:
            try:
                info = probe(path)
                if not info["audio"]:
                    continue

                duration = max(0.0, float(info["duration"]))
                self.mixer_tracks.append({
                    "path": str(Path(path).resolve()),
                    "duration": duration,
                    "volume": 100,
                    "pan": 0,
                    "mute": False,
                    "solo": False,
                    "source_start": 0,
                    "source_end": duration,
                    "timeline_start": timeline_cursor,
                    "fade_in": 0,
                    "fade_out": 0
                })

                # The next selected file starts at the exact end of this one.
                timeline_cursor += duration
            except Exception:
                pass
        self.mixer_rebuild()

    def mixer_rebuild(self):
        while self.mixer_layout.count():
            item = self.mixer_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.mixer_tracks:
            self.mixer_empty = QLabel("No mixer tracks yet.\nClick + Add Audio to start.")
            self.mixer_empty.setAlignment(Qt.AlignCenter)
            self.mixer_empty.setObjectName("muted")
            self.mixer_layout.addWidget(self.mixer_empty)
            self.mixer_layout.addStretch()
            self.mixer_total.setText("0 tracks")
            return

        for i, track in enumerate(self.mixer_tracks):
            card = QFrame()
            card.setObjectName("track")
            lay = QVBoxLayout(card)
            lay.setContentsMargins(13, 11, 13, 11)
            top = QHBoxLayout()
            n = QLabel(f"{i+1:02d}")
            n.setObjectName("trackNumber")
            top.addWidget(n)
            name = QLabel(Path(track["path"]).name)
            name.setToolTip(track["path"])
            name.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            top.addWidget(name, 1)

            play_track = QPushButton("▶")
            play_track.setFixedWidth(42)
            play_track.setToolTip("Preview this mixer audio")
            play_track.clicked.connect(
                lambda checked=False, i=i: self.mixer_preview_track(i)
            )
            top.addWidget(play_track)

            mute = QCheckBox("Mute")
            mute.setChecked(track["mute"])
            mute.toggled.connect(lambda v, i=i: self.mixer_set(i, "mute", v))
            top.addWidget(mute)
            solo = QCheckBox("Solo")
            solo.setChecked(track["solo"])
            solo.toggled.connect(lambda v, i=i: self.mixer_set(i, "solo", v))
            top.addWidget(solo)
            remove = QPushButton("Remove")
            remove.setObjectName("danger")
            remove.clicked.connect(lambda checked=False, i=i: self.mixer_remove(i))
            top.addWidget(remove)
            lay.addLayout(top)

            playback = QHBoxLayout()
            playback.setSpacing(8)

            track_play = QPushButton("▶")
            track_play.setFixedWidth(42)
            track_play.setToolTip("Play / pause this audio")
            track_play.clicked.connect(
                lambda checked=False, i=i: self.mixer_preview_track(i)
            )

            position = QLabel("00:00")
            position.setObjectName("muted")
            position.setFixedWidth(72)

            seek = SeekSlider(Qt.Horizontal)
            seek.setRange(0, 1000)
            seek.setValue(0)
            seek.setToolTip("Drag to seek through this audio")
            seek.setMinimumWidth(180)
            seek.seekRequested.connect(lambda value, i=i: self.mixer_seek_track(i, value))

            duration_label = QLabel(fmt_time(track["duration"]))
            duration_label.setObjectName("muted")
            duration_label.setFixedWidth(72)

            playback.addWidget(track_play)
            playback.addWidget(position)
            playback.addWidget(seek, 1)
            playback.addWidget(duration_label)
            lay.addLayout(playback)

            # Keep references for live position updates.
            track["_play_button"] = track_play
            track["_position_label"] = position
            track["_position_slider"] = seek
            track["_duration_label"] = duration_label

            controls = QHBoxLayout()
            controls.setSpacing(8)

            controls.addWidget(QLabel("Volume"))
            vol = QSlider(Qt.Horizontal)
            vol.setRange(0, 150)
            vol.setValue(int(track["volume"]))
            vol.setMaximumWidth(150)
            value = QLabel(f'{track["volume"]}%')
            value.setFixedWidth(42)
            vol.valueChanged.connect(
                lambda v, i=i, lab=value: self.mixer_volume_changed(i, v, lab)
            )
            controls.addWidget(vol)
            controls.addWidget(value)

            controls.addWidget(QLabel("Pan"))
            pan = QSlider(Qt.Horizontal)
            pan.setRange(-100, 100)
            pan.setValue(int(track["pan"] * 100))
            pan.setMaximumWidth(120)
            pan_value = QLabel("Center")
            pan_value.setFixedWidth(72)
            pan.valueChanged.connect(
                lambda v, i=i, lab=pan_value: self.mixer_pan_changed(i, v, lab)
            )
            controls.addWidget(pan)
            controls.addWidget(pan_value)

            lay.addLayout(controls)

            range_row = QHBoxLayout()
            range_row.setSpacing(7)

            source_start = QDoubleSpinBox()
            source_start.setRange(0, max(0.01, float(track["duration"])))
            source_start.setDecimals(2)
            source_start.setSuffix(" s")
            source_start.setValue(float(track.get("source_start", 0)))
            source_start.valueChanged.connect(
                lambda v, i=i: self.mixer_range_changed(i, "source_start", v)
            )

            source_end = QDoubleSpinBox()
            source_end.setRange(0, max(0.01, float(track["duration"])))
            source_end.setDecimals(2)
            source_end.setSuffix(" s")
            source_end.setValue(float(track.get("source_end", track["duration"])))
            source_end.valueChanged.connect(
                lambda v, i=i: self.mixer_range_changed(i, "source_end", v)
            )

            timeline_start = QDoubleSpinBox()
            timeline_start.setRange(0, 999999)
            timeline_start.setDecimals(2)
            timeline_start.setSuffix(" s")
            timeline_start.setValue(float(track.get("timeline_start", 0)))
            timeline_start.valueChanged.connect(
                lambda v, i=i: self.mixer_set(i, "timeline_start", v)
            )

            fade_in = QDoubleSpinBox()
            fade_in.setRange(0, 9999)
            fade_in.setDecimals(2)
            fade_in.setSuffix(" s")
            fade_in.setValue(float(track.get("fade_in", 0)))
            fade_in.valueChanged.connect(
                lambda v, i=i: self.mixer_set(i, "fade_in", v)
            )

            fade_out = QDoubleSpinBox()
            fade_out.setRange(0, 9999)
            fade_out.setDecimals(2)
            fade_out.setSuffix(" s")
            fade_out.setValue(float(track.get("fade_out", 0)))
            fade_out.valueChanged.connect(
                lambda v, i=i: self.mixer_set(i, "fade_out", v)
            )

            range_row.addWidget(QLabel("From"))
            range_row.addWidget(source_start)
            range_row.addWidget(QLabel("To"))
            range_row.addWidget(source_end)
            range_row.addWidget(QLabel("Timeline at"))
            range_row.addWidget(timeline_start)
            range_row.addWidget(QLabel("Fade in"))
            range_row.addWidget(fade_in)
            range_row.addWidget(QLabel("Fade out"))
            range_row.addWidget(fade_out)
            lay.addLayout(range_row)
            self.mixer_layout.addWidget(card)

        self.mixer_layout.addStretch()
        self.mixer_total.setText(f"{len(self.mixer_tracks)} tracks")

    def mixer_set(self, index, key, value):
        if index < len(self.mixer_tracks):
            self.mixer_tracks[index][key] = value

    def mixer_volume_changed(self, index, value, label):
        self.mixer_tracks[index]["volume"] = value
        label.setText(f"{value}%")

    def mixer_pan_changed(self, index, value, label):
        self.mixer_tracks[index]["pan"] = value / 100.0
        label.setText("L" if value < 0 else "R" if value > 0 else "Center")

    def mixer_range_changed(self, index, key, value):
        if index >= len(self.mixer_tracks):
            return
        track = self.mixer_tracks[index]
        duration = float(track.get("duration", 0))

        if key == "source_start":
            value = max(0.0, min(float(value), duration))
            track["source_start"] = value
            if float(track.get("source_end", duration)) <= value:
                track["source_end"] = min(duration, value + 0.01)
        else:
            value = max(0.0, min(float(value), duration))
            if value <= float(track.get("source_start", 0)):
                value = min(duration, float(track.get("source_start", 0)) + 0.01)
            track["source_end"] = value

    def mixer_preview_track(self, index):
        if index >= len(self.mixer_tracks):
            return
        track = self.mixer_tracks[index]
        path = Path(track["path"])
        if not path.exists():
            QMessageBox.warning(self, "Missing Audio", f"File not found:\n{path}")
            return

        if (
            self.mixer_preview_index == index
            and self.mixer_preview_player
            and self.mixer_preview_player.playbackState() == QMediaPlayer.PlayingState
        ):
            self.mixer_preview_player.pause()
            if track.get("_play_button"):
                track["_play_button"].setText("▶")
            return

        if (
            self.mixer_preview_index == index
            and self.mixer_preview_player
            and self.mixer_preview_player.playbackState() == QMediaPlayer.PausedState
        ):
            self.mixer_preview_player.play()
            if track.get("_play_button"):
                track["_play_button"].setText("⏸")
            return

        if self.mixer_preview_player:
            self.mixer_preview_player.stop()
            self.mixer_preview_player.deleteLater()

        self.mixer_preview_audio = QAudioOutput(self)
        self.mixer_preview_audio.setVolume(
            (float(track.get("volume", 100)) / 100.0) *
            (self.mixer_master.value() / 100.0)
        )
        self.mixer_preview_player = QMediaPlayer(self)
        self.mixer_preview_player.setAudioOutput(self.mixer_preview_audio)
        self.mixer_preview_player.setSource(QUrl.fromLocalFile(str(path)))
        for t in self.mixer_tracks:
            if t.get("_play_button"):
                t["_play_button"].setText("▶")

        self.mixer_preview_index = index
        self.mixer_preview_player.positionChanged.connect(self.mixer_preview_position_changed)
        self.mixer_preview_player.playbackStateChanged.connect(
            self.mixer_preview_track_state_changed
        )
        self.mixer_preview_player.play()
        if track.get("_play_button"):
            track["_play_button"].setText("⏸")

    def mixer_preview_position_changed(self, position):
        idx = self.mixer_preview_index
        if idx < 0 or idx >= len(self.mixer_tracks):
            return
        track = self.mixer_tracks[idx]
        duration = max(0.01, float(track.get("duration", 0)))
        value = int(max(0, min(1000, (position / 1000.0) / duration * 1000)))
        slider = track.get("_position_slider")
        label = track.get("_position_label")
        if slider:
            slider.blockSignals(True)
            slider.setValue(value)
            slider.blockSignals(False)
        if label:
            label.setText(fmt_time(position / 1000.0))
        wave = track.get("_waveform")
        if wave:
            wave.set_cursor(position / 1000.0)

    def mixer_preview_track_state_changed(self, state):
        idx = self.mixer_preview_index
        if idx < 0 or idx >= len(self.mixer_tracks):
            return
        button = self.mixer_tracks[idx].get("_play_button")
        if button:
            button.setText("⏸" if state == QMediaPlayer.PlayingState else "▶")

    def mixer_seek_track(self, index, value):
        if index < 0 or index >= len(self.mixer_tracks):
            return

        track = self.mixer_tracks[index]
        duration = float(track.get("duration", 0) or 0)
        value = max(0, min(1000, int(value)))
        position = duration * value / 1000.0

        # Clicking/dragging any track's timeline selects that track.
        if index != self.mixer_preview_index or not self.mixer_preview_player:
            self.mixer_preview_track(index)
            if not self.mixer_preview_player:
                return

        # Seek immediately and keep/resume playback at the selected point.
        self.mixer_preview_player.setPosition(int(position * 1000))
        self.mixer_preview_player.play()

        # Update the exact track's UI immediately while dragging.
        slider = track.get("_position_slider")
        label = track.get("_position_label")
        if slider:
            slider.blockSignals(True)
            slider.setValue(value)
            slider.blockSignals(False)
        if label:
            label.setText(fmt_time(position))


    def mixer_toggle_final_preview(self):
        if not self.mixer_tracks:
            return

        # If a rendered preview exists, use it directly.
        preview = getattr(self, "mixer_preview_path", None)
        if preview and preview.exists():
            if self.mixer_final_player.playbackState() == QMediaPlayer.PlayingState:
                self.mixer_final_player.pause()
                return
            if self.mixer_final_player.source().isEmpty():
                self.mixer_final_player.setSource(QUrl.fromLocalFile(str(preview)))
            self.mixer_final_player.play()
            return

        self.mixer_render_final_preview()

    def mixer_render_final_preview(self):
        active = self.mixer_effective_tracks()
        if not active:
            QMessageBox.warning(self, "No Active Tracks", "Unmute at least one mixer track.")
            return

        preview_dir = ROOT / "assets" / "output" / ".preview"
        preview_dir.mkdir(parents=True, exist_ok=True)
        preview_path = preview_dir / "mixer_preview.wav"

        try:
            cmd = build_mixer_command(active, str(preview_path), "wav")
        except Exception as e:
            QMessageBox.critical(self, "Preview Error", str(e))
            return

        self.mixer_preview_path = preview_path
        self.mixer_preview_process = QProcess(self)
        self.mixer_preview_process.setProgram(cmd[0])
        self.mixer_preview_process.setArguments(cmd[1:])
        self.mixer_preview_process.finished.connect(self.mixer_preview_render_finished)
        self.mixer_preview_process.errorOccurred.connect(self.mixer_preview_render_error)
        self.mixer_final_play.setEnabled(False)
        self.mixer_status.setText("Rendering final mix preview…")
        self.mixer_preview_process.start()

    def mixer_preview_render_finished(self, exit_code, exit_status):
        self.mixer_final_play.setEnabled(True)
        if exit_code != 0 or not self.mixer_preview_path.exists():
            self.mixer_status.setText("Final mix preview failed.")
            QMessageBox.critical(self, "Preview Failed", "Could not render the final mix preview.")
            self.mixer_final_pending_seek = None
            return

        pending = getattr(self, "mixer_final_pending_seek", None)
        self.mixer_final_pending_seek = None

        self.mixer_final_player.stop()
        self.mixer_final_player.setSource(QUrl.fromLocalFile(str(self.mixer_preview_path)))
        self.mixer_final_duration = self.mixer_mix_duration()
        if hasattr(self, "mixer_final_waveform") and getattr(self, "mixer_output_path", None):
            self.mixer_final_waveform.set_audio(self.mixer_output_path, self.mixer_final_duration)

        if pending is not None:
            position = self.mixer_final_duration * max(0, min(1000, int(pending))) / 1000.0
            self.mixer_final_player.setPosition(int(position * 1000))

        self.mixer_final_player.play()
        self.mixer_final_play.setText("⏸ Pause Final Mix")
        self.mixer_status.setText("Playing final mix preview…")


    def mixer_preview_render_error(self, error):
        self.mixer_final_play.setEnabled(True)
        if error == QProcess.FailedToStart:
            self.mixer_status.setText("FFmpeg could not be started.")
            QMessageBox.critical(self, "FFmpeg Error", "FFmpeg could not be started.")

    def mixer_final_position_changed(self, position):
        duration = float(self.mixer_final_duration or self.mixer_mix_duration())
        seconds = position / 1000.0
        value = int(max(0, min(1000, seconds / duration * 1000))) if duration > 0 else 0
        self.mixer_final_slider.blockSignals(True)
        self.mixer_final_slider.setValue(value)
        self.mixer_final_slider.blockSignals(False)
        self.mixer_final_time.setText(f"{fmt_time(seconds)} / {fmt_time(duration)}")
        if hasattr(self, "mixer_final_waveform"):
            self.mixer_final_waveform.set_cursor(seconds)

    def mixer_seek_final(self, value):
        value = max(0, min(1000, int(value)))

        if self.mixer_final_player.source().isEmpty():
            self.mixer_final_pending_seek = value
            self.mixer_render_final_preview()
            return

        duration = float(self.mixer_final_duration or self.mixer_mix_duration())
        position = duration * value / 1000.0
        self.mixer_final_player.setPosition(int(position * 1000))
        self.mixer_final_player.play()

        if hasattr(self, "mixer_final_time_label"):
            self.mixer_final_time_label.setText(
                f"{self.format_time(position)} / {self.format_time(duration)}"
            )

    def mixer_final_state_changed(self, state):
        if state == QMediaPlayer.PlayingState:
            self.mixer_final_play.setText("⏸ Pause Final Mix")
        else:
            self.mixer_final_play.setText("▶ Play Final Mix")

    def mixer_remove(self, index):
        self.mixer_stop()
        self.mixer_tracks.pop(index)
        self.mixer_rebuild()

    def mixer_clear(self):
        self.mixer_stop()
        self.mixer_tracks.clear()
        self.mixer_rebuild()

    def mixer_effective_tracks(self):
        solo_exists = any(t.get("solo", False) for t in self.mixer_tracks)
        result = []
        for t in self.mixer_tracks:
            if t.get("mute"):
                continue
            if solo_exists and not t.get("solo"):
                continue
            result.append(t)
        return result

    def mixer_toggle_play(self):
        if not self.mixer_tracks:
            return
        if self.mixer_playing:
            for p in self.mixer_players:
                p.pause()
            self.mixer_playing = False
            self.mixer_play.setText("▶ Play Mix")
            return

        active = self.mixer_effective_tracks()
        if not active:
            QMessageBox.warning(self, "No Active Tracks", "Unmute at least one mixer track.")
            return

        self.mixer_stop()
        self.mixer_players = []
        for track in active:
            player = QMediaPlayer(self)
            audio = QAudioOutput(self)
            audio.setVolume((track["volume"] / 100.0) * (self.mixer_master.value() / 100.0))
            player.setAudioOutput(audio)
            player.setSource(QUrl.fromLocalFile(track["path"]))
            player.play()
            self.mixer_players.append(player)
            # Keep audio object alive through the player.
            player._mp3studio_audio = audio

        self.mixer_playing = True
        self.mixer_play.setText("⏸ Pause Mix")

    def mixer_stop(self):
        for p in getattr(self, "mixer_players", []):
            p.stop()
            p.deleteLater()
        self.mixer_players = []
        self.mixer_playing = False
        if hasattr(self, "mixer_play"):
            self.mixer_play.setText("▶ Play Mix")

    def mixer_choose_save_location(self):
        fmt = self.mixer_format.currentText().lower()
        name = self.mixer_name.text().strip() or "mixed_audio"
        for char in '<>:"/\\|?*':
            name = name.replace(char, "_")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Choose Mixed Audio Location",
            str(OUTPUT_DIR / f"{name}.{fmt}"),
            f"{fmt.upper()} Audio (*.{fmt});;All Files (*)"
        )
        if path:
            self.mixer_saved_path.setText(path)

    def mixer_export_audio(self):
        active = self.mixer_effective_tracks()
        if not active:
            QMessageBox.warning(self, "No Active Tracks", "Add an audio track and make sure it is not muted.")
            return
        name = self.mixer_name.text().strip() or "mixed_audio"
        for char in r'<>:"/\\|?*':
            name = name.replace(char, "_")
        fmt = self.mixer_format.currentText().lower()
        chosen = self.mixer_saved_path.text().strip() if hasattr(self, "mixer_saved_path") else ""
        if chosen and chosen not in {"assets/output/", str(OUTPUT_DIR)}:
            output = Path(chosen)
            if output.suffix.lower() != f".{fmt}":
                output = output.with_suffix(f".{fmt}")
            output.parent.mkdir(parents=True, exist_ok=True)
            if output.exists():
                output = self.unique_output(output.stem, fmt)
        else:
            output = self.unique_output(name, fmt)
        try:
            cmd = build_mixer_command(
                active, str(output), fmt,
                bitrate=self.mixer_bitrate.currentText(),
                normalize=self.mixer_normalize.isChecked()
            )
        except Exception as e:
            QMessageBox.critical(self, "Mixer Error", str(e))
            return

        cmd.insert(1, "-progress")
        cmd.insert(2, "pipe:1")
        cmd.insert(3, "-nostats")
        self.mixer_output_path = output
        self.mixer_process = QProcess(self)
        self.mixer_process.setProgram(cmd[0])
        self.mixer_process.setArguments(cmd[1:])
        self.mixer_process.readyReadStandardOutput.connect(self.mixer_read_progress)
        self.mixer_process.finished.connect(self.mixer_export_finished)
        self.mixer_process.errorOccurred.connect(self.mixer_export_error)
        self.mixer_export.setEnabled(False)
        self.mixer_progress.setValue(0)
        self.mixer_status.setText("Mixing…")
        self.mixer_process.start()

    def mixer_read_progress(self):
        data = bytes(self.mixer_process.readAllStandardOutput()).decode("utf-8", errors="replace")
        for line in data.splitlines():
            if line.startswith("out_time_ms="):
                try:
                    sec = int(line.split("=", 1)[1]) / 1_000_000
                    self.mixer_progress.setValue(min(100, int(sec / max(1, self.mixer_mix_duration()) * 100)))
                except ValueError:
                    pass

    def mixer_mix_duration(self):
        active = self.mixer_effective_tracks()
        if not active:
            return 0.0

        # Always use the full source/timeline duration. No artificial cap.
        return max(
            max(0.0, float(t.get("timeline_start", 0))) +
            max(
                0.0,
                float(t.get("source_end", t.get("duration", 0))) -
                float(t.get("source_start", 0))
            )
            for t in active
        )

    def mixer_export_error(self, error):
        if error == QProcess.FailedToStart:
            self.mixer_export.setEnabled(True)
            self.mixer_status.setText("FFmpeg could not be started.")
            QMessageBox.critical(self, "FFmpeg Error", "FFmpeg could not be started.")

    def mixer_export_finished(self, exit_code, exit_status):
        self.mixer_export.setEnabled(True)
        if exit_code == 0 and getattr(self, "mixer_output_path", None) and self.mixer_output_path.exists():
            self.mixer_progress.setValue(100)
            self.mixer_status.setText(f"Final mix saved • {self.mixer_output_path}")
            # Reload the final preview from the newly exported file.
            self.mixer_final_player.stop()
            self.mixer_final_player.setSource(
                QUrl.fromLocalFile(str(self.mixer_output_path))
            )
            self.mixer_final_duration = self.mixer_mix_duration()
            if hasattr(self, "mixer_final_waveform"):
                self.mixer_final_waveform.set_audio(self.mixer_output_path, self.mixer_final_duration)
            self.mixer_final_slider.setValue(0)
            self.mixer_final_time.setText(
                f"00:00 / {fmt_time(self.mixer_final_duration)}"
            )
        else:
            self.mixer_status.setText("Mix export failed.")
            QMessageBox.critical(self, "Export Failed", "FFmpeg could not create the mixed audio.")
        self.mixer_process = None

        if not getattr(self, "editor_input_path", None):
            return
        start = self.editor_start.value()
        end = self.editor_end.value()
        if end <= start:
            QMessageBox.warning(self, "Invalid Range", "End time must be greater than start time.")
            return

        name = self.editor_output_name.text().strip() or Path(self.editor_input_path).stem + "_edited"
        for char in '<>:"/\\|?*':
            name = name.replace(char, "_")

        fmt = self.editor_output_format.currentText().lower()
        output = self.unique_output(name, fmt)
        speed = float(self.editor_speed.currentText().replace("×", ""))

        try:
            cmd = build_edit_command(
                self.editor_input_path,
                str(output),
                fmt,
                start=start,
                end=end,
                volume=self.editor_volume.value(),
                fade_in=min(self.editor_fade_in.value(), end - start),
                fade_out=min(self.editor_fade_out.value(), end - start),
                speed=speed,
                normalize=self.editor_normalize.isChecked(),
                bitrate=self.editor_bitrate.currentText()
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))
            return

        cmd.insert(1, "-progress")
        cmd.insert(2, "pipe:1")
        cmd.insert(3, "-nostats")

        self.editor_output_path = output
        self.editor_process = QProcess(self)
        self.editor_process.setProgram(cmd[0])
        self.editor_process.setArguments(cmd[1:])
        self.editor_process.readyReadStandardOutput.connect(self.editor_read_progress)
        self.editor_process.finished.connect(self.editor_export_finished)
        self.editor_process.errorOccurred.connect(self.editor_export_error)
        self.editor_export.setEnabled(False)
        self.editor_progress.setValue(0)
        self.editor_status.setText("Exporting edited audio…")
        self.editor_process.start()

    def editor_read_progress(self):
        data = bytes(self.editor_process.readAllStandardOutput()).decode("utf-8", errors="replace")
        total = max(0.01, self.editor_end.value() - self.editor_start.value())
        for line in data.splitlines():
            if line.startswith("out_time_ms="):
                try:
                    sec = int(line.split("=", 1)[1]) / 1_000_000
                    self.editor_progress.setValue(max(0, min(100, int(sec / total * 100))))
                except ValueError:
                    pass

    def editor_export_error(self, error):
        if error == QProcess.FailedToStart:
            self.editor_export.setEnabled(True)
            self.editor_status.setText("FFmpeg could not be started.")
            QMessageBox.critical(self, "FFmpeg Error", "FFmpeg could not be started.")

    def editor_export_finished(self, exit_code, exit_status):
        self.editor_export.setEnabled(True)
        if exit_code == 0 and getattr(self, "editor_output_path", None) and self.editor_output_path.exists():
            self.editor_progress.setValue(100)
            self.editor_status.setText(f"Done • {self.editor_output_path.name}")
        else:
            self.editor_status.setText("Export failed.")
            QMessageBox.critical(self, "Export Failed", "FFmpeg could not export the edited audio.")
        self.editor_process = None

    # ---------- Phase 2 ----------
    def build_studio_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(34, 26, 34, 32)
        layout.setSpacing(13)
        page.setMinimumWidth(760)

        title_row = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Audio Studio")
        title.setObjectName("bigTitle")
        title_box.addWidget(title)
        sub = QLabel("Build a sequence from multiple audio files with per-track playback controls.")
        sub.setObjectName("muted")
        title_box.addWidget(sub)
        title_row.addLayout(title_box, 1)

        add = QPushButton("+ Add Audio")
        add.clicked.connect(self.add_audio_files)
        title_row.addWidget(add)
        add_folder = QPushButton("+ Add Folder")
        add_folder.setObjectName("secondary")
        add_folder.clicked.connect(self.add_audio_folder)
        title_row.addWidget(add_folder)
        layout.addLayout(title_row)

        toolbar = QHBoxLayout()
        save = QPushButton("Save Preset")
        save.clicked.connect(self.save_preset)
        toolbar.addWidget(save)
        load = QPushButton("Import Preset")
        load.setObjectName("secondary")
        load.clicked.connect(self.load_preset)
        toolbar.addWidget(load)
        clear = QPushButton("Clear All")
        clear.setObjectName("danger")
        clear.clicked.connect(self.clear_tracks)
        toolbar.addWidget(clear)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        settings = QGroupBox("Playback")
        s = QHBoxLayout(settings)
        self.auto_play = QCheckBox("Auto Play")
        self.auto_play.setChecked(True)
        self.auto_play.toggled.connect(self.auto_play_changed)
        s.addWidget(self.auto_play)

        self.repeat_play = QCheckBox("Repeat")
        self.repeat_play.toggled.connect(self.repeat_changed)
        self.repeat_play.setToolTip("Repeat the same audio track after it finishes.")
        self.auto_play.setToolTip("Play the next audio track automatically after this one finishes.")
        s.addWidget(self.repeat_play)
        s.addSpacing(18)
        s.addWidget(QLabel("Master Volume"))
        self.master_volume = QSlider(Qt.Horizontal)
        self.master_volume.setRange(0, 100)
        self.master_volume.setValue(100)
        self.master_volume.setMaximumWidth(190)
        self.master_volume.valueChanged.connect(lambda v: self.audio_output.setVolume(v / 100))
        s.addWidget(self.master_volume)
        self.master_volume_label = QLabel("100%")
        self.master_volume_label.setFixedWidth(40)
        self.master_volume.valueChanged.connect(lambda v: self.master_volume_label.setText(f"{v}%"))
        s.addWidget(self.master_volume_label)
        s.addStretch()
        self.total_label = QLabel("0 tracks • 00:00")
        self.total_label.setObjectName("muted")
        s.addWidget(self.total_label)
        layout.addWidget(settings)

        transport = QHBoxLayout()
        self.prev_btn = QPushButton("◀ Previous")
        self.prev_btn.setObjectName("secondary")
        self.prev_btn.clicked.connect(self.play_previous)
        transport.addWidget(self.prev_btn)
        self.play_all_btn = QPushButton("▶ Play All")
        self.play_all_btn.clicked.connect(self.toggle_play_all)
        transport.addWidget(self.play_all_btn)
        self.stop_all_btn = QPushButton("■ Stop")
        self.stop_all_btn.setObjectName("secondary")
        self.stop_all_btn.clicked.connect(self.stop_studio)
        transport.addWidget(self.stop_all_btn)
        self.next_btn = QPushButton("Next ▶")
        self.next_btn.setObjectName("secondary")
        self.next_btn.clicked.connect(self.play_next)
        transport.addWidget(self.next_btn)
        transport.addStretch()
        self.studio_position = QLabel("00:00 / 00:00")
        self.studio_position.setObjectName("muted")
        transport.addWidget(self.studio_position)
        layout.addLayout(transport)

        self.track_scroll = QScrollArea()
        self.track_scroll.setWidgetResizable(True)
        self.track_scroll.setFrameShape(QFrame.NoFrame)
        self.track_container = QWidget()
        self.track_layout = QVBoxLayout(self.track_container)
        self.track_layout.setContentsMargins(0, 3, 0, 3)
        self.track_layout.setSpacing(9)
        self.track_layout.addStretch()
        self.track_scroll.setWidget(self.track_container)
        layout.addWidget(self.track_scroll, 1)

        self.empty_label = QLabel("No audio tracks yet.\nClick  + Add Audio  to start.")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setObjectName("muted")
        self.track_layout.insertWidget(0, self.empty_label)
        return page

    def add_audio_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Audio Files", "",
            "Audio/Media Files (*);;Audio Files (*.mp3 *.wav *.flac *.aac *.m4a *.ogg *.opus *.wma *.aiff)"
        )
        if paths:
            for path in paths:
                self.add_track(path)

    def add_audio_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Audio Folder")
        if not folder:
            return
        exts = {".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".opus", ".wma", ".aiff", ".aif", ".alac", ".amr"}
        for path in sorted(Path(folder).iterdir()):
            if path.is_file() and path.suffix.lower() in exts:
                self.add_track(str(path))

    def add_track(self, path, preset_data=None):
        try:
            info = probe(str(path))
            if not info["audio"]:
                return
        except Exception:
            QMessageBox.warning(self, "Skipped File", f"Could not read audio from:\n{path}")
            return

        data = {
            "path": str(Path(path).resolve()),
            "duration": info["duration"],
            "volume": 100,
            "fade_in": 0,
            "fade_out": 0,
            "start": 0,
            "end": info["duration"],
            "mute": False,
            "solo": False,
        }
        if preset_data:
            data.update(preset_data)
            data["path"] = str(Path(path).resolve())
            data["duration"] = info["duration"]
            data["end"] = min(float(data.get("end", info["duration"])), info["duration"])

        self.tracks.append(data)
        self.rebuild_tracks()

    def rebuild_tracks(self):
        while self.track_layout.count():
            item = self.track_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.tracks:
            self.empty_label = QLabel("No audio tracks yet.\nClick  + Add Audio  to start.")
            self.empty_label.setAlignment(Qt.AlignCenter)
            self.empty_label.setObjectName("muted")
            self.track_layout.addWidget(self.empty_label)
            self.track_layout.addStretch()
            self.update_studio_summary()
            return

        self.track_widgets = []
        for i, data in enumerate(self.tracks):
            w = AudioTrackWidget(data, i)
            w.play_requested.connect(self.play_track)
            w.remove_requested.connect(self.remove_track)
            w.duplicate_requested.connect(self.duplicate_track)
            w.move_up_requested.connect(self.move_up)
            w.move_down_requested.connect(self.move_down)
            w.changed.connect(self.track_changed)
            w.seek_requested.connect(self.seek_track)
            self.track_layout.addWidget(w)
            self.track_widgets.append(w)
        self.track_layout.addStretch()
        self.update_studio_summary()

    def track_changed(self):
        self.tracks = [w.to_dict() for w in getattr(self, "track_widgets", [])]
        self.update_studio_summary()

    def update_studio_summary(self):
        total = sum(max(0, float(t.get("end", 0)) - float(t.get("start", 0))) for t in self.tracks)
        self.total_label.setText(f"{len(self.tracks)} tracks • {fmt_time(total)}")

    def remove_track(self, widget):
        idx = self.track_widgets.index(widget)
        if self.current_track_index == idx:
            self.stop_studio()
            self.current_track_index = -1
        self.tracks.pop(idx)
        self.rebuild_tracks()

    def duplicate_track(self, widget):
        idx = self.track_widgets.index(widget)
        data = dict(widget.to_dict())
        data["path"] = data["path"]
        self.tracks.insert(idx + 1, data)
        self.rebuild_tracks()

    def move_up(self, widget):
        idx = self.track_widgets.index(widget)
        if idx <= 0:
            return
        self.tracks[idx - 1], self.tracks[idx] = self.tracks[idx], self.tracks[idx - 1]
        self.rebuild_tracks()

    def move_down(self, widget):
        idx = self.track_widgets.index(widget)
        if idx >= len(self.tracks) - 1:
            return
        self.tracks[idx + 1], self.tracks[idx] = self.tracks[idx], self.tracks[idx + 1]
        self.rebuild_tracks()

    def clear_tracks(self):
        if not self.tracks:
            return
        if QMessageBox.question(self, "Clear Tracks", "Remove all audio tracks?") != QMessageBox.Yes:
            return
        self.stop_studio()
        self.tracks.clear()
        self.rebuild_tracks()

    def auto_play_changed(self, checked):
        if checked:
            self.repeat_play.blockSignals(True)
            self.repeat_play.setChecked(False)
            self.repeat_play.blockSignals(False)

    def repeat_changed(self, checked):
        if checked:
            self.auto_play.blockSignals(True)
            self.auto_play.setChecked(False)
            self.auto_play.blockSignals(False)

    def effective_volume(self, idx):
        track = self.tracks[idx]
        solo_exists = any(t.get("solo", False) for t in self.tracks)
        if track.get("mute", False):
            return 0.0
        if solo_exists and not track.get("solo", False):
            return 0.0
        return float(track.get("volume", 100)) / 100.0

    def play_track(self, widget):
        if widget.missing:
            QMessageBox.warning(self, "Missing File", f"Locate this file first:\n{widget.data['path']}")
            return
        idx = self.track_widgets.index(widget)

        # Clicking the currently playing track pauses it instead of restarting it.
        if idx == self.current_track_index and self.studio_playing:
            self.player.pause()
            self.studio_playing = False
            self.fade_timer.stop()
            self.play_all_btn.setText("▶ Play All")
            self.refresh_track_visuals()
            return

        # Clicking a paused current track resumes from its current position.
        if idx == self.current_track_index and self.player.playbackState() == QMediaPlayer.PausedState:
            self.studio_playing = True
            self.player.play()
            self.fade_timer.start()
            self.play_all_btn.setText("⏸ Pause All")
            self.refresh_track_visuals()
            return

        self.play_index(idx)

    def play_index(self, idx):
        if idx < 0 or idx >= len(self.tracks):
            return
        path = self.tracks[idx]["path"]
        if not Path(path).exists():
            QMessageBox.warning(self, "Missing File", f"File not found:\n{path}")
            return
        self.current_track_index = idx
        self.current_track_started_at = float(self.tracks[idx].get("start", 0))
        self.studio_playing = True
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.setPosition(int(self.current_track_started_at * 1000))
        self.audio_output.setVolume(0)
        self.player.play()
        self.play_all_btn.setText("⏸ Pause All")
        self.studio_position.setText(
            f"{fmt_time(self.current_track_started_at)} / "
            f"{fmt_time(float(self.tracks[idx].get('end', self.tracks[idx].get('duration', 0))))}"
        )
        self.fade_mode = "in" if self.tracks[idx].get("fade_in", 0) > 0 else "steady"
        if self.fade_mode == "steady":
            self.audio_output.setVolume(self.effective_volume(idx))
        self.fade_timer.start()
        self.refresh_track_visuals()

    def seek_track(self, widget, slider_value):
        if widget not in getattr(self, "track_widgets", []):
            return
        idx = self.track_widgets.index(widget)
        if idx != self.current_track_index:
            return

        track = self.tracks[idx]
        start = float(track.get("start", 0))
        end = float(track.get("end", track.get("duration", 0)))
        position = start + (max(0, min(1000, slider_value)) / 1000.0) * max(0.0, end - start)
        self.player.setPosition(int(position * 1000))
        if self.studio_playing:
            self.player.play()

    def toggle_play_all(self):
        if not self.tracks:
            return
        if self.studio_playing:
            self.player.pause()
            self.studio_playing = False
            self.play_all_btn.setText("▶ Play All")
        else:
            idx = self.current_track_index if self.current_track_index >= 0 else 0
            self.play_index(idx)

    def stop_studio(self):
        self.player.stop()
        self.fade_timer.stop()
        self.fade_mode = None
        self.studio_playing = False
        self.current_track_index = -1
        self.play_all_btn.setText("▶ Play All")
        self.studio_position.setText("00:00 / 00:00")
        self.audio_output.setVolume(self.master_volume.value() / 100)
        for w in getattr(self, "track_widgets", []):
            w.set_playback_position(float(w.data.get("start", 0)), float(w.data.get("end", w.duration)))
        self.refresh_track_visuals()

    def play_next(self):
        if not self.tracks:
            return

        # "Repeat" repeats the currently selected/playing audio.
        if self.repeat_play.isChecked() and self.current_track_index >= 0:
            self.play_index(self.current_track_index)
            return

        # "Auto Play" advances exactly one track at a time.
        if self.auto_play.isChecked():
            next_idx = self.current_track_index + 1
            if next_idx >= len(self.tracks):
                self.stop_studio()
                return
            self.play_index(next_idx)
            return

        self.stop_studio()

    def play_previous(self):
        if not self.tracks:
            return
        idx = max(0, self.current_track_index - 1)
        self.play_index(idx)

    def player_position_changed(self, position):
        idx = self.current_track_index
        if idx < 0 or idx >= len(self.tracks):
            return
        track = self.tracks[idx]
        start = float(track.get("start", 0))
        end = float(track.get("end", track.get("duration", 0)))
        now = position / 1000.0
        if now < start - 0.1:
            self.player.setPosition(int(start * 1000))
            return
        duration = max(0, end - start)
        self.studio_position.setText(f"{fmt_time(now)} / {fmt_time(end)}")
        if 0 <= idx < len(getattr(self, "track_widgets", [])):
            self.track_widgets[idx].set_playback_position(now, end)

        fade_out = float(track.get("fade_out", 0))
        if fade_out > 0 and now >= end - fade_out:
            remaining = max(0, end - now)
            base = self.effective_volume(idx)
            self.audio_output.setVolume(base * min(1.0, remaining / fade_out))

        if now >= end - 0.03:
            self.finish_current_track()

    def finish_current_track(self):
        if not self.studio_playing:
            return

        # Stop the current player before scheduling the next item. This prevents
        # multiple positionChanged signals at the end from queueing duplicates.
        self.studio_playing = False
        self.fade_timer.stop()
        self.audio_output.setVolume(0)

        if self.repeat_play.isChecked() or self.auto_play.isChecked():
            QTimer.singleShot(80, self.play_next)
        else:
            self.play_all_btn.setText("▶ Play All")
            self.refresh_track_visuals()

    def player_state_changed(self, state):
        if state == QMediaPlayer.StoppedState and self.studio_playing:
            # Natural end is handled from positionChanged; this catches backend stops.
            pass

    def update_fade(self):
        idx = self.current_track_index
        if idx < 0 or idx >= len(self.tracks) or not self.studio_playing:
            return
        track = self.tracks[idx]
        base = self.effective_volume(idx)
        position = self.player.position() / 1000.0
        start = float(track.get("start", 0))
        end = float(track.get("end", track.get("duration", 0)))
        fade_in = float(track.get("fade_in", 0))
        fade_out = float(track.get("fade_out", 0))

        volume = base
        if fade_in > 0 and position < start + fade_in:
            volume = base * max(0.0, min(1.0, (position - start) / fade_in))
        if fade_out > 0 and position > end - fade_out:
            volume = min(volume, base * max(0.0, min(1.0, (end - position) / fade_out)))
        self.audio_output.setVolume(volume)

    def refresh_track_visuals(self):
        for i, w in enumerate(getattr(self, "track_widgets", [])):
            playing = i == self.current_track_index and self.studio_playing
            w.play_btn.setProperty("playing", playing)
            w.play_btn.setText("⏸" if playing else "▶")
            w.setObjectName("trackPlaying" if playing else "track")
            w.style().unpolish(w)
            w.style().polish(w)

    # ---------- Presets ----------
    def preset_payload(self):
        return {
            "version": 1,
            "application": "MP3 Studio",
            "autoplay": self.auto_play.isChecked(),
            "repeat": self.repeat_play.isChecked(),
            "master_volume": self.master_volume.value(),
            "tracks": [dict(t) for t in self.tracks],
        }

    def save_preset(self):
        if not self.tracks:
            QMessageBox.information(self, "No Tracks", "Add at least one audio track before saving a preset.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Preset", str(PRESET_DIR / "my_preset.json"), "MP3 Studio Preset (*.json)"
        )
        if not path:
            return
        try:
            Path(path).write_text(json.dumps(self.preset_payload(), indent=2), encoding="utf-8")
            QMessageBox.information(self, "Preset Saved", f"Preset saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", str(e))

    def load_preset(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Preset", str(PRESET_DIR), "MP3 Studio Preset (*.json)"
        )
        if not path:
            return
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or "tracks" not in payload:
                raise ValueError("This is not a valid MP3 Studio preset.")
        except Exception as e:
            QMessageBox.critical(self, "Invalid Preset", str(e))
            return

        self.stop_studio()
        self.tracks = []
        missing = []
        for item in payload.get("tracks", []):
            audio_path = str(item.get("path", ""))
            if not audio_path:
                continue
            if Path(audio_path).exists():
                try:
                    info = probe(audio_path)
                    if not info["audio"]:
                        raise RuntimeError()
                    data = dict(item)
                    data["duration"] = info["duration"]
                    data["end"] = min(float(data.get("end", info["duration"])), info["duration"])
                    self.tracks.append(data)
                except Exception:
                    missing.append(audio_path)
            else:
                # Keep missing tracks visible so the user can use Locate.
                data = dict(item)
                data["duration"] = float(data.get("duration", 0))
                self.tracks.append(data)
                missing.append(audio_path)

        self.auto_play.setChecked(bool(payload.get("autoplay", True)))
        self.repeat_play.setChecked(bool(payload.get("repeat", False)))
        self.master_volume.setValue(int(payload.get("master_volume", 100)))
        self.rebuild_tracks()

        if missing:
            QMessageBox.warning(
                self, "Missing Audio Files",
                f"{len(missing)} file(s) from the preset could not be found.\n"
                "Use Locate on each missing track to repair the preset."
            )

    def closeEvent(self, event):
        self.stop_studio()
        if self.process and self.process.state() != QProcess.NotRunning:
            self.process.kill()
        if getattr(self, "editor_process", None) and self.editor_process.state() != QProcess.NotRunning:
            self.editor_process.kill()
        if getattr(self, "mixer_process", None) and self.mixer_process.state() != QProcess.NotRunning:
            self.mixer_process.kill()
        self.mixer_stop()
        if getattr(self, "mixer_preview_player", None):
            self.mixer_preview_player.stop()
        if getattr(self, "mixer_final_player", None):
            self.mixer_final_player.stop()
        if getattr(self, "mixer_preview_process", None) and self.mixer_preview_process.state() != QProcess.NotRunning:
            self.mixer_preview_process.kill()
        event.accept()
