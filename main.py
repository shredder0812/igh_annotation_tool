import logging
from pathlib import Path
import yaml
import cv2
import numpy as np
import pandas as pd
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timedelta
from PyQt5.QtCore import Qt, QTimer, pyqtSlot, QRect, QEvent
from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QImage, QPixmap
from PyQt5.QtWidgets import (QMenuBar, QFileDialog, QAbstractItemView, QDesktopWidget, QGridLayout,
                             QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSlider, QStyle,
                             QTableWidget, QCheckBox, QTabWidget, QTableWidgetItem, QVBoxLayout, QWidget,
                             QScrollArea, QMessageBox, QApplication, QMenu, QAction, QHeaderView,
                             QComboBox, QSpinBox)
import sys
from tkinter import filedialog
import tkinter as tk

from autosave_thread import AutoSaveThread
from frame_viewer import VideoFrameViewer
from io_utils import parse_point_text, records_checksum, save_records_to_csv
from prediction_bars import QBar_PointerObject, QPredictionBar, QPredictionBar_MOT
from ui_style import APP_STYLESHEET


global file_path_open
# Utils
LOGGER = logging.getLogger(__name__)

def log_handler(*loggers, logname: str = '') -> None:
    # Set the log format
    formatter = logging.Formatter(
        '%(asctime)s %(filename)12s:L%(lineno)3s [%(levelname)8s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S')

    # Set up the stream handler (console output)
    shell_handler = logging.StreamHandler(sys.stdout)
    shell_handler.setLevel(logging.INFO)  # Set the log level to INFO
    shell_handler.setFormatter(formatter)  # Use the log formatter

    # Set up the file handler (log file)
    if logname:
        file_handler = logging.FileHandler(logname)
        file_handler.setLevel(logging.DEBUG)  # Set the log level to DEBUG
        file_handler.setFormatter(formatter)  # Use the log formatter

    # Add the handlers to the given loggers
    for logger in loggers:
        if logname:
            logger.addHandler(file_handler)  # Add the file handler if logname is provided
        logger.addHandler(shell_handler)  # Add the stream handler
        logger.setLevel(logging.DEBUG)  # Set the log level to DEBUG

class VideoAppViewer(QWidget):
    def __init__(self, videopath: str, title='IGH Annotation Tool'):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.title = title
        self.desktop = QDesktopWidget()
        self.screen = self.desktop.availableGeometry()
        self.font_header = QFont()
        self.font_header.setBold(True)
        self.font_size = QFont()
        self.font_size.setPointSize(12)
        self.font_size_header = QFont()
        self.font_size_header.setPointSize(14)
        self.videopath = videopath
        self.cap = cv2.VideoCapture(self.videopath)
        self.enter_pressed = False
        self._last_saved_checksum = None
        self._autosave_in_progress = False
                
        # auto save thread
        self.auto_save_enabled = False
        self.auto_save_thread = AutoSaveThread(interval_sec=10)
        self.auto_save_thread.save_completed.connect(self.auto_save)
        self.auto_save_thread.start()
        
        # init window - init and set default config about window
        self.setWindowTitle(self.title)
        self.setStyleSheet(APP_STYLESHEET)
                
        # grid: root layout
        self.grid_root = QGridLayout()
        self.setLayout(self.grid_root)
        vbox_panels = QVBoxLayout()
        vbox_option = QVBoxLayout()
        self.grid_root.addLayout(vbox_panels, 0, 0)
        #vbox_option.setFixedSize(600, 0)
        self.grid_root.addLayout(vbox_option, 0, 1)
        
        # menu bar
        self.menu_bar_no = QWidget(self)
        self.menu_bar_no.setFixedHeight(3)
        vbox_panels.addWidget(self.menu_bar_no)
        self.init_menu_bar()
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFixedWidth(1300) 
        vbox_panels.addWidget(self.scroll_area)
        # vbox_panel/label_frame: show frame image        
        self.label_frame = VideoFrameViewer(self)
        self.label_frame.setAlignment(Qt.AlignTop)
        self.label_frame.setMouseTracking(True)
        self.scroll_area.setWidget(self.label_frame)
        # vbox_option/group_video_info: show video static info
        
        self.menu_bar_noa = QMenuBar(self)
        vbox_option.addWidget(self.menu_bar_noa)
        
        self.group_video_info = QGroupBox('Video Information')
        self.group_video_info.setFont(self.font_size_header)
        sub_grid = QGridLayout()
        label_path = self._get_header_label('Input Video Path')
        label_output = self._get_header_label('Output Path')
        label_shape = self._get_header_label('Shape')
        label_fps = self._get_header_label('FPS')
        label_objid = self._get_header_label('Object ID')
        label_objcls = self._get_header_label('Object Class')
        
        self.label_video_path = QLabel()
        self.label_video_path.setAlignment(Qt.AlignLeft)
        self.label_video_path.setWordWrap(True)
        self.label_output_path = QLabel()
        self.label_output_path.setAlignment(Qt.AlignLeft)
        self.label_output_path.setWordWrap(True)       
        self.label_video_shape = QLabel()
        self.label_video_shape.setAlignment(Qt.AlignLeft)        
        self.label_video_fps = QLabel()
        self.label_video_fps.setAlignment(Qt.AlignLeft)        
        self.spin_object_id = QSpinBox()
        self.spin_object_id.setMinimum(1)
        self.spin_object_id.setMaximum(999999)
        self.spin_object_id.setValue(int(self.object_id))
        self.combo_object_class = QComboBox()
        self.combo_object_class.addItems([str(c) for c in self.classes_list])
        self.combo_object_class.setCurrentIndex(self.current_class_index)
        self.label_video_bbox = QLabel()
        self.label_video_bbox.setAlignment(Qt.AlignLeft)      

        sub_grid.addWidget(label_path, 0, 0)
        sub_grid.addWidget(self.label_video_path, 0, 1)
        sub_grid.addWidget(label_output, 1, 0)
        sub_grid.addWidget(self.label_output_path, 1, 1)
        sub_grid.addWidget(label_shape, 2, 0)
        sub_grid.addWidget(self.label_video_shape, 2, 1)
        sub_grid.addWidget(label_fps, 3, 0)
        sub_grid.addWidget(self.label_video_fps, 3, 1)
        sub_grid.addWidget(label_objid, 4, 0)
        sub_grid.addWidget(self.spin_object_id, 4, 1)
        sub_grid.addWidget(label_objcls, 5, 0)
        sub_grid.addWidget(self.combo_object_class, 5, 1)
        
        self.group_video_info.setLayout(sub_grid)
        self.group_video_info.contentsMargins()
        self.group_video_info.setAlignment(Qt.AlignTop)
        vbox_option.addWidget(self.group_video_info)
        
        # vbox_panel/label_video_status: show frame index or exception msg
        hbox_video_controls = QHBoxLayout() 
        self.label_video_status = QLabel()
        self.label_video_status.setAlignment(Qt.AlignCenter)
        hbox_video_controls.addWidget(self.label_video_status)
        self.input_frame_number = QLineEdit()
        self.input_frame_number.setPlaceholderText("Enter frame number")
        self.input_frame_number.setFont(self.font_size)
        
        self.input_frame_number.setReadOnly(True)
        self.input_frame_number.installEventFilter(self)
        hbox_video_controls.addWidget(self.input_frame_number)
        self.btn_jump_to_frame = QPushButton('Jump to Frame (Enter)')
        self.btn_jump_to_frame.setFont(self.font_size)
        #self.btn_jump_to_frame.setStyleSheet("background-color: rgb(60, 60, 60); color: rgb(200, 200, 200);")
        self.btn_jump_to_frame.clicked.connect(self.jump_to_frame)
        hbox_video_controls.addWidget(self.btn_jump_to_frame)
        vbox_option.addLayout(hbox_video_controls)
        
        # vbox_panel/hbox_video: show process about video
        self.btn_play_video_info = QGroupBox('Play/Pause Video (P)')
        self.btn_play_video_info.setFont(self.font_size_header)
        
        hbox_video_controler = QHBoxLayout()
        hbox_video_slider = QHBoxLayout()
        
        self.btn_play_video = QPushButton()
        #self.btn_play_video.setStyleSheet("background-color: rgb(60, 60, 60); color: rgb(200, 200, 200);")
        self.btn_play_video.setEnabled(True)
        self.btn_play_video.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.btn_button_a = QPushButton()
        self.btn_button_b = QPushButton()
        self.btn_button_c = QPushButton()
        self.btn_button_d = QPushButton()
        self.btn_button_a.setIcon(self.style().standardIcon(QStyle.SP_MediaSeekForward))
        self.btn_button_b.setIcon(self.style().standardIcon(QStyle.SP_MediaSeekBackward))
        self.btn_button_c.setIcon(self.style().standardIcon(QStyle.SP_MediaSkipForward))
        self.btn_button_d.setIcon(self.style().standardIcon(QStyle.SP_MediaSkipBackward))

        self.slider_video = QSlider(Qt.Horizontal)
        self.slider_video.setRange(0, 0)
        hbox_video_controler.addWidget(self.btn_button_d)
        hbox_video_controler.addWidget(self.btn_button_b)
        hbox_video_controler.addWidget(self.btn_play_video)
        hbox_video_controler.addWidget(self.btn_button_a)
        hbox_video_controler.addWidget(self.btn_button_c)
        
        #hbox_video_controler.addWidget(self.btn_button_e)
        hbox_video_slider.addWidget(self.slider_video)
        
        
        
        
        
        hbox_presence_bar = QHBoxLayout()
        self.enable_presence_bar = QPushButton()
        self.enable_presence_bar.setStyleSheet("background-color: rgb(60, 60, 60); color: rgb(200, 200, 200);")
        self.btn_play_video.setEnabled(True)
        #self.enable_presence_bar.setIcon(self.style().standardIcon(QStyle.SP_DialogOkButton))
        self.enable_presence_bar.setGeometry(20,20,20,20)
        self.presence_bar = QPredictionBar(self)
        self.presence_bar.setFixedHeight(20)
        self.presence_bar.setRange(0, 0)
        hbox_presence_bar.addWidget(self.presence_bar)

        hbox_mot_presence_bar = QHBoxLayout()
        self.mot_presence_bar = QPredictionBar_MOT(self)
        self.mot_presence_bar.setFixedHeight(20)
        self.mot_presence_bar.setRange(0, 0)
        hbox_mot_presence_bar.addWidget(self.mot_presence_bar)

        hbox_pointer_object = QHBoxLayout()
        self.pointer_object = QBar_PointerObject(self)
        self.pointer_object.setFixedHeight(10)
        self.pointer_object.setRange(0, 0)
        hbox_pointer_object.addWidget(self.pointer_object)

        vbox_group_playvideo = QVBoxLayout()
        vbox_group_playvideo.addLayout(hbox_video_controler)
        vbox_group_playvideo.addLayout(hbox_video_slider)
        vbox_group_playvideo.addLayout(hbox_presence_bar)
        vbox_group_playvideo.addLayout(hbox_mot_presence_bar)
        vbox_group_playvideo.addLayout(hbox_pointer_object)
        self.btn_play_video_info.setLayout(vbox_group_playvideo)
        vbox_option.addWidget(self.btn_play_video_info) 
        

        # Notes
        self.btn_add_notes_info = QGroupBox('Notes')
        self.btn_add_notes_info.setFont(self.font_size_header)
        add_notes_box = QHBoxLayout()
        self.line_edit_notes = QLineEdit(self)
        self.line_edit_notes.setFont(self.font_size)
        self.line_edit_notes.setPlaceholderText("Enter notes here")
        self.line_edit_notes.setReadOnly(False)
        self.line_edit_notes.installEventFilter(self)
        add_notes_box.addWidget(self.line_edit_notes)
        self.enter_pressed_notes = False
        self.save_notes_button = QPushButton('Save Notes (Enter)')
        #self.save_notes_button.setStyleSheet("background-color: rgb(60, 60, 60); color: rgb(200, 200, 200);")
        self.save_notes_button.setFont(self.font_size)
        self.save_notes_button.clicked.connect(self.save_notes)
        add_notes_box.addWidget(self.save_notes_button)
        self.btn_add_notes_info.setLayout(add_notes_box)
        vbox_option.addWidget(self.btn_add_notes_info) 
        
        # function
        self.group_function_info = QGroupBox('Functions')
        self.group_function_info.setFont(self.font_size_header)
        next_and_back_button = QHBoxLayout()
        object_id_push_button = QHBoxLayout()
        hbox_jump_records = QHBoxLayout()
        remove_box = QHBoxLayout()
        self.btn_to_back_frame = QPushButton('Previous Frame (B)')
        #self.btn_to_back_frame.setStyleSheet("background-color: rgb(60, 60, 60); color: rgb(200, 200, 200);")
        self.btn_to_back_frame.setFont(self.font_size)
        next_and_back_button.addWidget(self.btn_to_back_frame)
        self.btn_to_next_frame = QPushButton('Next Frame (N)')
        #self.btn_to_next_frame.setStyleSheet("background-color: rgb(60, 60, 60); color: rgb(200, 200, 200);")
        self.btn_to_next_frame.setFont(self.font_size)
        next_and_back_button.addWidget(self.btn_to_next_frame)
        vbox_option.addLayout(next_and_back_button)
        self.btn_to_change_class = QPushButton('Change Class (C)')
        #self.btn_to_change_class.setStyleSheet("background-color: rgb(60, 60, 60); color: rgb(200, 200, 200);")
        self.btn_to_change_class.setFont(self.font_size)
        object_id_push_button.addWidget(self.btn_to_change_class)
        self.btn_to_decrease_id = QPushButton('Decrease Object ID (D)')
        #self.btn_to_decrease_id.setStyleSheet("background-color: rgb(60, 60, 60); color: rgb(200, 200, 200);")
        self.btn_to_decrease_id.setFont(self.font_size)
        object_id_push_button.addWidget(self.btn_to_decrease_id)
        self.btn_to_increase_id = QPushButton('Increase Object ID (F)')
        #self.btn_to_increase_id.setStyleSheet("background-color: rgb(60, 60, 60); color: rgb(200, 200, 200);")
        self.btn_to_increase_id.setFont(self.font_size)
        object_id_push_button.addWidget(self.btn_to_increase_id)
        vbox_option.addLayout(object_id_push_button)
        vbox_option.addLayout(hbox_jump_records)
        
        self.btn_remove_last_box = QPushButton('Remove Last Box (R)')
        #self.btn_remove_last_box.setStyleSheet("background-color: rgb(60, 60, 60); color: rgb(200, 200, 200);")
        self.btn_remove_last_box.setFont(self.font_size)
        remove_box.addWidget(self.btn_remove_last_box)
        self.btn_remove_target_box = QPushButton('Remove Target Box (Delete)')
        #self.btn_remove_target_box.setStyleSheet("background-color: rgb(60, 60, 60); color: rgb(200, 200, 200);")
        self.btn_remove_target_box.setFont(self.font_size)
        remove_box.addWidget(self.btn_remove_target_box)
        vbox_option.addLayout(remove_box)
        
        self.checkbox_auto_save = QCheckBox("Auto Save")
        self.checkbox_auto_save.setFont(self.font_size)
        vbox_option.addWidget(self.checkbox_auto_save)
        self.btn_export_records = QPushButton('Export')
        #self.btn_export_records.setStyleSheet("background-color: rgb(60, 60, 60); color: rgb(200, 200, 200);")
        self.btn_export_records.setFont(self.font_size)
        vbox_option.addWidget(self.btn_export_records)

        # Add Zoom Buttons
        # Thêm nút cho zoom in và zoom out
        # self.btn_zoom_in = QPushButton("Zoom In")
        # self.btn_zoom_out = QPushButton("Zoom Out")
        # vbox_option.addWidget(self.btn_zoom_in)
        # vbox_option.addWidget(self.btn_zoom_out)
        
        # self.zoom_in_button = QPushButton("zoom-in")
        # self.zoom_in_button.clicked.connect(self.zoom_in)
        # vbox_option.addWidget(self.zoom_in_button)
        
        # self.zoom_out_button = QPushButton("zoom-reset")
        # self.zoom_out_button.clicked.connect(self.zoom_reset)
        # vbox_option.addWidget(self.zoom_out_button)

        # self.zoom_out_button = QPushButton("zoom-out")
        # self.zoom_out_button.clicked.connect(self.zoom_out)
        # vbox_option.addWidget(self.zoom_out_button)

        # vbox_option/table_preview_record: preview the summary of records
        
        # Add QTableWidget to display label and tracking result
        self.tab_widget = QTabWidget(self)
        #self.tab_widget.setStyleSheet("QTabWidget::pane { border: 1px solid rgb(250, 250, 250); } QTabBar::tab { width: 100px; height: 20px; background: rgb(60, 60, 60); font-size: 14px; color: rgb(250, 250, 250); border: 0.5px solid rgb(250, 250, 250); }QTabBar::tab:selected {font-weight: bold;}")
        self.label_tab = QWidget()
        self.tracking_tab = QWidget()
        self.tab_widget.addTab(self.label_tab, "Label")
        self.tab_widget.addTab(self.tracking_tab, "Tracking")
        # Set layouts for the tabs
        self.label_layout = QVBoxLayout(self.label_tab)
        self.tracking_layout = QVBoxLayout(self.tracking_tab)

        self.label_tab.setLayout(self.label_layout)
        self.tracking_tab.setLayout(self.tracking_layout)
        vbox_option.addWidget(self.tab_widget)
        
        self.table_preview_records = self._get_preview_table(self)
        self.table_preview_tracking_records = self._get_preview_table(self)
        self.label_layout.addWidget(self.table_preview_records)
        self.tracking_layout.addWidget(self.table_preview_tracking_records)
        
        self.cursor_position_label = QLabel(self)
        self.cursor_position_label.setStyleSheet("background-color: white; color: black; border: 0.5px solid black")
        self.cursor_position_label.resize(170, 20)
        self.cursor_position_label.move(1140, 0)
        self.cursor_position_label.setFont(self.font_size)
        self.setMouseTracking(True)

    def save_notes(self):
        notes_text = self.line_edit_notes.text()
        selected_row = self.table_preview_records.currentRow()
        if selected_row >= 0:
            frame_idx = int(self.table_preview_records.item(selected_row, 1).text())
            target_record = next((record for record in self.records if record['frame_idx'] == frame_idx), None)
            if target_record:
                target_record['notes'] = notes_text
                self.update_record_preview(selected_row, target_record)
                
    def update_record_preview(self, row, record):
        # Cập nhật ô Notes trong bảng record
        notes_item = QTableWidgetItem(record['notes'])
        self.table_preview_records.setItem(row, 4, notes_item)
        
    def update_tracking_record_preview(self, row, record):
        # Cập nhật ô Notes trong bảng record
        notes_item = QTableWidgetItem(record['notes'])
        self.table_preview_tracking_records.setItem(row, 4, notes_item)
    
    def _get_header_label(self, text: str = ''):
        label = QLabel(text)
        label.setFont(self.font_header)
        #label.setFont(self.font_size)
        label.setAlignment(Qt.AlignLeft)
        return label
    
    def _get_preview_table(self, parent):
        table = QTableWidget(parent=parent)
        #table.setStyleSheet("QScrollBar:vertical { background: rgb(80, 80, 80);width: 15px;} QScrollBar::handle:vertical {background: rgb(110, 110, 110);} QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {background: rgb(110, 110, 110); height: 15px;} QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: rgb(80, 80, 80); }")
        #table.horizontalHeader().setStyleSheet("QHeaderView::section { background-color: rgb(200, 200, 200); color: rgb(60, 60, 60); }")
        #table.verticalHeader().setStyleSheet("QHeaderView::section { background-color: rgb(200, 200, 200); color: rgb(60, 60, 60); }")
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels(['Timestamp', 'Frame', 'Class' , 'Object ID', 'Notes' , 'Pt1', 'Pt2'])
        table.setSortingEnabled(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.resizeColumnsToContents()
        table.setColumnWidth(2, table.columnWidth(2) + 80)  # Cột 3
        table.setColumnWidth(4, table.columnWidth(4) + 40)  # Cột 5
        table.setColumnWidth(5, table.columnWidth(5) + 40)  # Cột 6
        table.setColumnWidth(6, table.columnWidth(6) + 40)  # Cột 7
        # Đặt kích thước chữ là 10
        font = table.font()
        font.setPointSize(10)
        table.setFont(font)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)

        return table
    
    def add_record_to_preview(self, timestamp: str, frame_idx: int, object_class: str, object_id: int, notes_text: str, pt1: tuple, pt2: tuple):
        self.table_preview_records.insertRow(0)
        self.table_preview_records.setItem(0, 0, QTableWidgetItem(timestamp))
        self.table_preview_records.setItem(0, 1, QTableWidgetItem(str(frame_idx)))
        self.table_preview_records.setItem(0, 2, QTableWidgetItem(str(object_class)))
        self.table_preview_records.setItem(0, 3, QTableWidgetItem(str(object_id)))
        self.table_preview_records.setItem(0, 4, QTableWidgetItem(str(notes_text)))
        self.table_preview_records.setItem(0, 5, QTableWidgetItem(str(pt1)))
        self.table_preview_records.setItem(0, 6, QTableWidgetItem(str(pt2)))
        self.table_preview_records.sortByColumn(0, Qt.DescendingOrder)
    
    def add_record_to_tracking_preview(self, timestamp: str, frame_idx: int, object_class: str, object_id: int, notes_text: str, pt1: tuple, pt2: tuple):
        self.table_preview_tracking_records.insertRow(0)
        self.table_preview_tracking_records.setItem(0, 0, QTableWidgetItem(timestamp))
        self.table_preview_tracking_records.setItem(0, 1, QTableWidgetItem(str(frame_idx)))
        self.table_preview_tracking_records.setItem(0, 2, QTableWidgetItem(str(object_class)))
        self.table_preview_tracking_records.setItem(0, 3, QTableWidgetItem(str(object_id)))
        self.table_preview_tracking_records.setItem(0, 4, QTableWidgetItem(str(notes_text)))
        self.table_preview_tracking_records.setItem(0, 5, QTableWidgetItem(str(pt1)))
        self.table_preview_tracking_records.setItem(0, 6, QTableWidgetItem(str(pt2)))
        self.table_preview_tracking_records.sortByColumn(0, Qt.DescendingOrder)
    
    
    def remove_record_from_preview(self, frame_idx: int = None, pt1: tuple = None, pt2: tuple = None):
        if self.table_preview_records.rowCount() == 0:
            return

        if frame_idx is None:
            self.table_preview_records.removeRow(0)
            return

        for row in range(self.table_preview_records.rowCount()):
            row_frame = int(self.table_preview_records.item(row, 1).text())
            row_pt1 = parse_point_text(self.table_preview_records.item(row, 5).text())
            row_pt2 = parse_point_text(self.table_preview_records.item(row, 6).text())
            if row_frame == frame_idx and (pt1 is None or row_pt1 == pt1) and (pt2 is None or row_pt2 == pt2):
                self.table_preview_records.removeRow(row)
                return

    def remove_tracking_record_from_preview(self, frame_idx: int = None, pt1: tuple = None, pt2: tuple = None):
        if self.table_preview_tracking_records.rowCount() == 0:
            return

        if frame_idx is None:
            self.table_preview_tracking_records.removeRow(0)
            return

        for row in range(self.table_preview_tracking_records.rowCount()):
            row_frame = int(self.table_preview_tracking_records.item(row, 1).text())
            row_pt1 = parse_point_text(self.table_preview_tracking_records.item(row, 5).text())
            row_pt2 = parse_point_text(self.table_preview_tracking_records.item(row, 6).text())
            if row_frame == frame_idx and (pt1 is None or row_pt1 == pt1) and (pt2 is None or row_pt2 == pt2):
                self.table_preview_tracking_records.removeRow(row)
                return
            
    def jump_to_frame(self):
        if not self.enter_pressed:  # Kiểm tra cờ để đảm bảo không nhảy frame nếu đã nhấn Enter
            frame_number_text = self.input_frame_number.text()
            try:
                frame_number = int(frame_number_text)
                # Tự đảm bảo rằng frame_number nằm trong phạm vi hợp lệ
                if 0 <= frame_number < self.frame_count:
                    self.target_frame_idx = frame_number
                    # self.input_frame_number.clear()
                else:
                    QMessageBox.warning(self, "Invalid Frame Number", "Please enter a valid frame number.")
            except ValueError:
                QMessageBox.warning(self, "Invalid Input", "Please enter a valid frame number.")
            self.input_frame_number.setReadOnly(True)
                   

    def eventFilter(self, obj, event):
        if obj == self.input_frame_number:
            if event.type() == QEvent.MouseButtonPress:
                self.input_frame_number.setReadOnly(False)  # Kích hoạt QLineEdit khi nhấp chuột vào
                self.enter_pressed = False  # Đặt lại cờ khi nhấp chuột vào
            elif event.type() == QEvent.KeyPress:
                if event.key() == Qt.Key_Return:
                    self.jump_to_frame()
                    self.input_frame_number.setReadOnly(True)  # Deactivate QLineEdit sau khi nhấn Enter
                    self.enter_pressed = True  # Đặt cờ khi nhấn Enter
                    return True  # Ngăn không cho sự kiện KeyPress tiếp tục lan ra
                elif event.key() == Qt.Key_Escape:
                    self.input_frame_number.setReadOnly(True)
            elif event.type() == QEvent.FocusOut:
                if not self.enter_pressed:
                    self.input_frame_number.setReadOnly(True)
        else:
            if event.type() == QEvent.MouseButtonPress:
                obj.setReadOnly(False)
            elif event.type() == QEvent.KeyPress:
                if event.key() == Qt.Key_Return:
                    if obj == self.line_edit_notes:
                        self.save_notes()
                    elif obj == self.input_frame_number:
                        self.jump_to_frame()
                    obj.setReadOnly(True)
                    return True
                elif event.key() == Qt.Key_Escape:
                    obj.setReadOnly(True)
            elif event.type() == QEvent.FocusOut:
                obj.setReadOnly(True)
        return super().eventFilter(obj, event)
    
    # def zoom_in(self):
    #     self.label_frame.zoom_in()

    # def zoom_out(self):
    #     self.label_frame.zoom_out()
        
    # def zoom_reset(self):
    #     self.label_frame.zoom_reset()
        
    @property
    def frame_count(self):
        return int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)) if self.cap else None
       
# App
class VideoApp(VideoAppViewer):
    def __init__(self, videopath: str, outpath: str, **config):
        # self.videopath = videopath
        self.outpath = outpath
        self.videopath = videopath
        video_path_open = Path(self.videopath)
        output_path_open = Path('outputs')
        if not output_path_open.exists():
            output_path_open.mkdir(parents=True)
        label_output_path_open = output_path_open / '{}_label.csv'.format(video_path_open.stem)
        self.outpath = label_output_path_open
                
        self.config = config
        self.title = self.config.get('title', 'IGH Annotation Tool')
        self.object_id = 1
        self.current_class_index = 0
        self.classes_list = config.get('classes', ['A', 'B', 'C', 'D', 'E'])
        self.object_class = self.classes_list[self.current_class_index]
        super().__init__(videopath=self.videopath, title=self.title)
        
        self.show_message_box = True
        self.show_message_box_target = True
        
        self.is_new_video_opened = False
              
        # draw config
        if self.config.get('draw') and isinstance(self.config['draw'], dict):
            draw_config = self.config['draw']
            self.label_frame.apply_draw_config(
                color=draw_config.get('color', QColor(0, 0, 0)),
                thickness=draw_config.get('thickness', 2),
                style=draw_config.get('style', Qt.SolidLine),
            )
        if self.config.get('select') and isinstance(self.config['select'], dict):
            select_config = self.config['select']
            self.label_frame.apply_select_config(
                color=select_config.get('color', QColor(0, 0, 0)),
                thickness=select_config.get('thickness', 3),
                style=select_config.get('style', Qt.SolidLine),
            )

        # record config
        check_label = self.config.get('label')
        label_color = self.config['label'].get('color', (0, 0, 0)) if check_label else None
        label_thickness = self.config['label'].get('thickness', 2) if check_label else None
        self.label_color = label_color
        self.label_thickness = label_thickness
        self.limit_nlabel = self.config.get('limit_nlabel', None)
        self.records = []
        self.tracking_records = []
        self.pointer_tracking_records = []

        # read video
        self.cap = cv2.VideoCapture(self.videopath)
        self.target_frame_idx = 0       # ready to update
        self.render_frame_idx = None    # redneded
        self.scale_height = self.scale_width = None
        self.is_playing_video = False
        self.is_force_update = False
        self._update_video_info()
        self._update_frame()
        
        
        
        # self.btn_zoom_in.clicked.connect(self.zoom_in)
        # self.btn_zoom_out.clicked.connect(self.zoom_out)

        # Thêm phím tắt cho zoom in và zoom out
        # self.shortcut_zoom_in = QShortcut(QKeySequence("+"), self)
        # self.shortcut_zoom_in.activated.connect(self.zoom_in)
        # self.shortcut_zoom_out = QShortcut(QKeySequence("-"), self)
        # self.shortcut_zoom_out.activated.connect(self.zoom_out)
        
        # widget binding
        self.slider_video.setRange(0, self.frame_count-1)
        self.slider_video.sliderMoved.connect(self.on_slider_moved)
        self.slider_video.sliderReleased.connect(self.on_slider_released)
        self.presence_bar.setRange(0, self.frame_count-1)   
        self.mot_presence_bar.setRange(0, self.frame_count-1)     
        self.pointer_object.setRange(0, self.frame_count-1) 
        self.btn_play_video.clicked.connect(self.on_play_video_clicked)
        self.btn_to_back_frame.clicked.connect(self.to_back_frame)
        self.btn_to_next_frame.clicked.connect(self.to_next_frame)        
        self.btn_to_change_class.clicked.connect(self.to_change_class_name)
        self.btn_to_decrease_id.clicked.connect(self.to_decrease_object_id)
        self.btn_to_increase_id.clicked.connect(self.to_increase_object_id)      
        self.spin_object_id.valueChanged.connect(self.on_object_id_selected)
        self.combo_object_class.currentIndexChanged.connect(self.on_class_selected)
        #self.btn_continue.clicked.connect(self.continue_function)
        self.label_frame.mousePressEvent = self.event_frame_mouse_press
        self.label_frame.mouseMoveEvent = self.event_frame_mouse_move_while_pressed
        self.label_frame.mouseReleaseEvent = self.event_frame_mouse_release
        self.btn_export_records.clicked.connect(self.save_file)
        self.btn_remove_last_box.clicked.connect(self.remove_last_box)
        self.btn_remove_target_box.clicked.connect(self.remove_target_record)
        self.table_preview_records.doubleClicked.connect(self.event_preview_double_clicked)
        self.table_preview_tracking_records.doubleClicked.connect(self.event_preview_tracking_double_clicked)
        self.checkbox_auto_save.stateChanged.connect(self.toggle_auto_save)
        self.presence_bar.mousePressEvent = self.jump_to_frame_by_presence_bar
        self.mot_presence_bar.mousePressEvent = self.jump_to_frame_by_mot_presence_bar
        self.pointer_object.mousePressEvent = self.jump_to_frame_by_pointer_object
        
        self.btn_button_d.clicked.connect(self.button_d)
        self.btn_button_b.clicked.connect(self.button_b)
        self.btn_button_a.clicked.connect(self.button_a)
        self.btn_button_c.clicked.connect(self.button_c)
        self._apply_ux_defaults()
        self.showMaximized()
        # self.setStyleSheet('''
        #     background-color: rgb(27,27,27);
        #     color: rgb(204,204,204);
        # ''')

    def _apply_ux_defaults(self):
        self.input_frame_number.setToolTip("Nhap so frame va nhan Enter de nhay")
        self.line_edit_notes.setToolTip("Ghi chu cho box dang chon")
        self.spin_object_id.setToolTip("Chon Object ID")
        self.combo_object_class.setToolTip("Chon Object Class")
        self.btn_to_next_frame.setToolTip("Phim tat: N")
        self.btn_to_back_frame.setToolTip("Phim tat: B")
        self.btn_to_change_class.setToolTip("Phim tat: C (su dung dropdown de chon truc tiep)")
        self.btn_to_increase_id.setToolTip("Phim tat: F (su dung spinbox de chon truc tiep)")
        self.btn_to_decrease_id.setToolTip("Phim tat: D (su dung spinbox de chon truc tiep)")
        self.btn_remove_last_box.setToolTip("Phim tat: R")
        self.btn_remove_target_box.setToolTip("Phim tat: Delete")
        self.table_preview_records.setFocusPolicy(Qt.StrongFocus)
        self.table_preview_tracking_records.setFocusPolicy(Qt.StrongFocus)
        self.btn_to_change_class.hide()
        self.btn_to_increase_id.hide()
        self.btn_to_decrease_id.hide()

    def copy_selected_row(self, source_table, dest_table):
        selected_rows = source_table.selectionModel().selectedRows()
        for row in selected_rows:
            dest_table.insertRow(dest_table.rowCount())
            for column in range(source_table.columnCount()):
                dest_table.setItem(dest_table.rowCount() - 1, column, QTableWidgetItem(source_table.item(row.row(), column).text()))

    def copy_all_rows(self, source_table, dest_table):
        dest_table.setRowCount(source_table.rowCount())
        dest_table.setColumnCount(source_table.columnCount())
        for row in range(source_table.rowCount()):
            for column in range(source_table.columnCount()):
                item = source_table.item(row, column)
                if item is not None:
                    dest_table.setItem(row, column, QTableWidgetItem(item.text()))
    @pyqtSlot() 
    def button_c(self):
        self.target_frame_idx = min(self.target_frame_idx+50, self.frame_count-1)
        
    @pyqtSlot() 
    def button_a(self):
        self.target_frame_idx = min(self.target_frame_idx+10, self.frame_count-1)
    @pyqtSlot() 
    def button_b(self):
        self.target_frame_idx = max(0, self.target_frame_idx-10)
    @pyqtSlot() 
    def button_d(self):
        self.target_frame_idx = max(0, self.target_frame_idx-50) 


    def jump_to_frame_by_presence_bar(self, event):        
        if event.button() == Qt.LeftButton:
            pos = event.pos()
            adjusted_x = pos.x()
            #self.clicked.emit(pos)
            target_frame = self.presence_bar._pixelPosToFrame(adjusted_x)
            #print(target_frame)
            try:
                frame_number = target_frame
                    # Tự đảm bảo rằng frame_number nằm trong phạm vi hợp lệ
                if 0 <= frame_number < self.frame_count:
                    self.target_frame_idx = frame_number
                        # self.input_frame_number.clear()
                else:
                    QMessageBox.warning(self, "Invalid Frame Number", "Please enter a valid frame number.")
            except ValueError:
                    QMessageBox.warning(self, "Invalid Input", "Please enter a valid frame number.")

    def jump_to_frame_by_mot_presence_bar(self, event):        
        if event.button() == Qt.LeftButton:
            pos = event.pos()
            adjusted_x = pos.x()
            #self.clicked.emit(pos)
            target_frame = self.mot_presence_bar._pixelPosToFrame(adjusted_x)
            #print(target_frame)
            try:
                frame_number = target_frame
                    # Tự đảm bảo rằng frame_number nằm trong phạm vi hợp lệ
                if 0 <= frame_number < self.frame_count:
                    self.target_frame_idx = frame_number
                        # self.input_frame_number.clear()
                else:
                    QMessageBox.warning(self, "Invalid Frame Number", "Please enter a valid frame number.")
            except ValueError:
                    QMessageBox.warning(self, "Invalid Input", "Please enter a valid frame number.")
                    
    def jump_to_frame_by_pointer_object(self, event):        
        if event.button() == Qt.LeftButton:
            pos = event.pos()
            adjusted_x = pos.x()
            #self.clicked.emit(pos)
            target_frame = self.pointer_object._pixelPosToFrame(adjusted_x)
            #print(target_frame)
            try:
                frame_number = target_frame
                    # Tự đảm bảo rằng frame_number nằm trong phạm vi hợp lệ
                if 0 <= frame_number < self.frame_count:
                    self.target_frame_idx = frame_number
                        # self.input_frame_number.clear()
                else:
                    QMessageBox.warning(self, "Invalid Frame Number", "Please enter a valid frame number.")
            except ValueError:
                    QMessageBox.warning(self, "Invalid Input", "Please enter a valid frame number.")
    
    def init_menu_bar(self):
        # Tạo menu bar
        menubar = QMenuBar(self)
        menubar.setGeometry(0, 0, 92, 20)
        # Tạo menu "File"
        file_menu = menubar.addMenu('File')
        # Tạo action "Open File" và gán sự kiện
        open_action = QAction('&Open File (MP4)', self)
        #open_action.setShortcut('Ctrl+O')
        open_action.triggered.connect(self.open_video_file)
        file_menu.addAction(open_action)
        # Tạo action "Import File" và gán sự kiện
        import_action = QAction('&Import Label File (CSV)', self)
        import_action.triggered.connect(self.import_csv_file)
        file_menu.addAction(import_action)
        # Tạo action "Import File" và gán sự kiện
        import_action = QAction('&Import Tracking Result File (CSV)', self)
        import_action.triggered.connect(self.import_tracking_csv_file)
        file_menu.addAction(import_action)
        
        
        # Tạo menu "Settings"
        file_menu = menubar.addMenu('System')
        setting_action = QAction('&Change Classes', self)
        setting_action.triggered.connect(self.change_class)
        file_menu.addAction(setting_action)
        # Tạo action "Reload" và gán sự kiện
        reload_action = QAction('&Reload', self)
        reload_action.triggered.connect(self.reload_app)
        file_menu.addAction(reload_action)

            
    def open_video_file(self):
        file_path_open = get_video_file()
        
        if file_path_open:
            self.videopath = file_path_open
            self.is_new_video_opened = True
            message_box = QMessageBox()
            message_box.setWindowTitle("Open New Video Confirmation")
            message_box.setText("Do you want to open new video?")
            message_box.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ok)
            message_box.setDefaultButton(QMessageBox.Cancel)

            # Hiển thị hộp thoại thông báo và chờ người dùng chọn
            choice = message_box.exec_()
            
            if choice == QMessageBox.Ok:  # Nếu người dùng chọn "OK"
                # Xoá dữ liệu trong records
                if self.records:
                    self.remove_all_records_from_preview()
                    self.remove_all_tracking_records_from_preview()
                    self.records = []
                    self.is_force_update = True
                if self.tracking_records:
                    self.remove_all_tracking_records_from_preview()
                    self.tracking_records = []
                    self.pointer_tracking_records = []
                    self.is_force_update = True   
                # Đặt lại các thông số liên quan đến video
                #self.videopath = file_path_open
                video_path_open = Path(self.videopath)
                output_path_open = Path('outputs')
                if not output_path_open.exists():
                    output_path_open.mkdir(parents=True)
                label_output_path_open = output_path_open / '{}_label.csv'.format(video_path_open.stem)
                self.outpath = label_output_path_open
                if self.cap:
                    self.cap.release()
                self.cap = cv2.VideoCapture(self.videopath)
                self.target_frame_idx = 0       # sẵn sàng cập nhật
                self.render_frame_idx = None    # đã render
                self.scale_height = self.scale_width = None
                self.is_playing_video = False
                self.is_force_update = False
                self.slider_video.setRange(0, self.frame_count-1)
                self.presence_bar.setRange(0, self.frame_count-1)
                self.mot_presence_bar.setRange(0, self.frame_count-1)
                self.pointer_object.setRange(0, self.frame_count-1)
                self._update_video_info()
                self.update_presence_bar()
                self.update_mot_presence_bar()
                self.update_pointer_object()
                self._update_frame()
        return self.videopath
        #pass
    
    def import_csv_file(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(self, "Import Label CSV File", "", "Label CSV Files (*.csv)", options=options)
        if file_path:
            self.read_csv_file(file_path)
            
    def import_tracking_csv_file(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(self, "Import Tracking Result CSV File", "", "Tracking Result CSV Files (*.csv)", options=options)
        if file_path:
            self.read_tracking_csv_file(file_path)
            #self.read_pointer_csv_file(file_path)

    def change_class(self):
        # Keep behavior intuitive: menu action cycles class selection.
        self.to_change_class_name()
    
    def read_csv_file(self, file_path):
        self.remove_all_records_from_preview()
        try:
            df = pd.read_csv(file_path)
            self.records = []
            dedup = set()

            for _, row in df.iterrows():
                notes_value = row['notes'] if pd.notna(row['notes']) else ''
                record = OrderedDict([
                        ('timestamp_hms', row['timestamp_hms']),
                        ('timestamp_hmsf', row['timestamp_hmsf']),
                        ('frame_idx', int(row['frame_idx'])), ('fps', row['fps']),
                        ('object_cls', row['object_cls']),
                        ('object_idx', int(row['object_idx'])), ('object_id', int(row['object_id'])),
                        ('notes', notes_value),
                        ('frame_height', int(row['frame_height'])), ('frame_width', int(row['frame_width'])),
                        ('scale_height', int(row['scale_height'])), ('scale_width', int(row['scale_width'])),
                        ('x1', int(row['x1'])), ('y1', int(row['y1'])), ('x2', int(row['x2'])), ('y2', int(row['y2'])),
                        ('center_x', int(row['center_x'])), ('center_y', int(row['center_y']))
                        ])
                record_key = tuple(record.items())
                if record_key in dedup:
                    continue
                dedup.add(record_key)
                self.records.append(record)

            self.records = sorted(self.records, key=lambda x: x['frame_idx'])
            for record in self.records:
                self.add_record_to_preview(
                    record['timestamp_hms'],
                    record['frame_idx'],
                    record['object_cls'],
                    record['object_id'],
                    record['notes'],
                    (record['x1'], record['y1']),
                    (record['x2'], record['y2']),
                )
                
            # Hiển thị thông tin về số lượng bản ghi đã được import
            QMessageBox.about(self, 'Info', 'Imported {} records from CSV file.'.format(len(self.records)))
            self.update_presence_bar()
            if self.records:
                self.render_frame_idx = max(record['frame_idx'] for record in self.records)
            self.is_force_update = True
            self.update()
        except Exception as e:
            QMessageBox.critical(self, 'Error', 'Error occurred while importing CSV file: {}'.format(str(e)))


    # def read_tracking_csv_file(self, file_path):
    #     self.remove_all_tracking_records_from_preview()
    #     try:
    #         df = pd.read_csv(file_path)
    #         # Xử lý dữ liệu đọc được từ file CSV và cập nhật vào danh sách self.records
    #         self.tracking_records = []  # Đảm bảo rằng danh sách self.tracking_records trống trước khi cập nhật dữ liệu mới
    #         new_tracking_records = []
    #         for index, row in df.iterrows():
    #             notes_value = row['notes'] if pd.notna(row['notes']) else ''
    #             record = OrderedDict([
    #                     ('timestamp_hms', row['timestamp_hms']),
    #                     ('timestamp_hmsf', row['timestamp_hmsf']),
    #                     ('frame_idx', row['frame_idx']), ('fps', row['fps']),
    #                     ('object_cls', row['object_cls']), ('object_cls', row['object_cls']),
    #                     ('object_idx', row['object_idx']), ('object_id', row['object_id']),
    #                     ('notes', notes_value),
    #                     ('frame_height', row['frame_height']), ('frame_width', row['frame_width']),
    #                     ('scale_height', row['scale_height']), ('scale_width', row['scale_width']),
    #                     ('x1', row['x1']), ('y1', row['y1']), ('x2', row['x2']), ('y2', row['y2']),
    #                     ('center_x', row['center_x']), ('center_y', row['center_y'])
    #                     ])#('pt1', row['pt1']), ('pt2', row['pt2']),
    #             if not self._is_duplicate_track(record):
    #                 new_tracking_records.append(record)
    #             self.tracking_records.extend(new_tracking_records)  # Thêm các bản ghi mới vào danh sách tồn tại
    #             self._update_tracking_records()
    #             if not record['notes']:
    #                 record['notes'] = ''
    #             self.add_record_to_tracking_preview(record['timestamp_hms'], \
    #                                             record['frame_idx'], \
    #                                             record['object_cls'], \
    #                                             record['object_id'], \
    #                                             (record['notes']), \
    #                                             (record['x1'], record['y1']), \
    #                                             (record['x2'], record['y2'])) \
    #                                             #(record['pt1']), \
    #                                             #(record['pt2']))
    #             self.is_force_update = True
    #             self.update()  # Cập nhật giao diện để hiển thị box cuối cùng
                
    #         # Hiển thị thông tin về số lượng bản ghi đã được import
    #         QMessageBox.about(self, 'Info', 'Imported {} records from Traking result CSV file.'.format(len(self.tracking_records)))
    #         #self.redraw_tracking_boxes_on_frame()
    #         self.redraw_combined_boxes_on_frame()
    #         self.update_mot_presence_bar()
    #         self.render_frame_idx = max(record['frame_idx'] for record in self.tracking_records)
    #     except Exception as e:
    #         QMessageBox.critical(self, 'Error', 'Error occurred while importing Tracking result CSV file: {}'.format(str(e)))
              
    def read_tracking_csv_file(self, file_path):
        self.remove_all_tracking_records_from_preview()
        try:
            df = pd.read_csv(file_path)
            self.tracking_records = []
            self.pointer_tracking_records = []

            dedup_tracking = set()
            dedup_pointer = set()
            seen_object_cls_ids = {}

            for _, row in df.iterrows():
                notes_value = row['notes'] if pd.notna(row['notes']) else ''
                record = OrderedDict([
                        ('timestamp_hms', row['timestamp_hms']),
                        ('timestamp_hmsf', row['timestamp_hmsf']),
                        ('frame_idx', int(row['frame_idx'])), ('fps', row['fps']),
                        ('object_cls', row['object_cls']),
                        ('object_idx', int(row['object_idx'])), ('object_id', int(row['object_id'])),
                        ('notes', notes_value),
                        ('frame_height', int(row['frame_height'])), ('frame_width', int(row['frame_width'])),
                        ('scale_height', int(row['scale_height'])), ('scale_width', int(row['scale_width'])),
                        ('x1', int(row['x1'])), ('y1', int(row['y1'])), ('x2', int(row['x2'])), ('y2', int(row['y2'])),
                        ('center_x', int(row['center_x'])), ('center_y', int(row['center_y']))
                        ])

                record_key = tuple(record.items())
                if record_key not in dedup_tracking:
                    dedup_tracking.add(record_key)
                    self.tracking_records.append(record)

                object_cls = row['object_cls']
                object_id = int(row['object_id'])

                # Kiểm tra nếu object_cls đã có trong seen_object_cls_ids
                if object_cls not in seen_object_cls_ids:
                    seen_object_cls_ids[object_cls] = set()

                # Kiểm tra nếu object_id đã có trong seen_object_cls_ids[object_cls]
                if object_id not in seen_object_cls_ids[object_cls]:
                    if record_key not in dedup_pointer:
                        dedup_pointer.add(record_key)
                        self.pointer_tracking_records.append(record)
                    seen_object_cls_ids[object_cls].add(object_id)

            self.tracking_records = sorted(self.tracking_records, key=lambda x: x['frame_idx'])
            for record in self.tracking_records:
                self.add_record_to_tracking_preview(
                    record['timestamp_hms'],
                    record['frame_idx'],
                    record['object_cls'],
                    record['object_id'],
                    record['notes'],
                    (record['x1'], record['y1']),
                    (record['x2'], record['y2']),
                )
                
            # Hiển thị thông tin về số lượng bản ghi đã được import
            QMessageBox.about(self, 'Info', 'Imported {} records from Traking result CSV file.'.format(len(self.tracking_records)))
            self.update_mot_presence_bar()
            self.update_pointer_object()
            if self.tracking_records:
                self.render_frame_idx = max(record['frame_idx'] for record in self.tracking_records)
            self.is_force_update = True
            self.update()
        except Exception as e:
            QMessageBox.critical(self, 'Error', 'Error occurred while importing Tracking result CSV file: {}'.format(str(e)))
      
    # def read_pointer_csv_file(self, file_path):
    #     try:
    #         df = pd.read_csv(file_path)
    #         self.pointer_tracking_records = []  # Đảm bảo danh sách self.tracking_records trống trước khi cập nhật dữ liệu mới
    #         new_pointer_tracking_records = []
    #         seen_object_cls_ids = {}

    #         for index, row in df.iterrows():
    #             notes_value = row['notes'] if pd.notna(row['notes']) else ''
    #             record = OrderedDict([
    #                 ('timestamp_hms', row['timestamp_hms']),
    #                 ('timestamp_hmsf', row['timestamp_hmsf']),
    #                 ('frame_idx', row['frame_idx']), 
    #                 ('fps', row['fps']),
    #                 ('object_cls', row['object_cls']), 
    #                 ('object_idx', row['object_idx']),
    #                 ('object_id', row['object_id']),
    #                 ('notes', notes_value),
    #                 ('frame_height', row['frame_height']), 
    #                 ('frame_width', row['frame_width']),
    #                 ('scale_height', row['scale_height']), 
    #                 ('scale_width', row['scale_width']),
    #                 ('x1', row['x1']), 
    #                 ('y1', row['y1']), 
    #                 ('x2', row['x2']), 
    #                 ('y2', row['y2']),
    #                 ('center_x', row['center_x']), 
    #                 ('center_y', row['center_y'])
    #             ])
                
    #             object_cls = row['object_cls']
    #             object_id = row['object_id']

    #             # Kiểm tra nếu object_cls đã có trong seen_object_cls_ids
    #             if object_cls not in seen_object_cls_ids:
    #                 seen_object_cls_ids[object_cls] = set()

    #             # Kiểm tra nếu object_id đã có trong seen_object_cls_ids[object_cls]
    #             if object_id not in seen_object_cls_ids[object_cls]:
    #                 if not self._is_duplicate_track(record):
    #                     new_pointer_tracking_records.append(record)
    #                 seen_object_cls_ids[object_cls].add(object_id)

    #         self.pointer_tracking_records.extend(new_pointer_tracking_records)  # Thêm các bản ghi mới vào danh sách tồn tại
    #         self._update_pointer_tracking_records()
            
    #         # Hiển thị thông tin về số lượng bản ghi đã được import
    #         QMessageBox.about(self, 'Info', 'Imported {} records from Tracking result CSV file.'.format(len(self.pointer_tracking_records)))
    #         self.update_pointer_object()
    #         self.render_frame_idx = max(record['frame_idx'] for record in self.pointer_tracking_records)
            
    #     except Exception as e:
    #         QMessageBox.critical(self, 'Error', 'Error occurred while importing Pointer Tracking result CSV file: {}'.format(str(e)))


                
    def _is_duplicate(self, new_record):
        for record in self.records:
            if record == new_record:
                return True
        return False
    
    def _is_duplicate_track(self, new_tracking_record):
        for record in self.tracking_records:
            if record == new_tracking_record:
                return True
        return False

    def _update_records(self):
        seen = set()
        unique_records = []
        for record in self.records:
            record_tuple = tuple(record.items())
            if record_tuple not in seen:
                unique_records.append(record)
                seen.add(record_tuple)
        self.records = unique_records
    
    def _update_tracking_records(self):
        seen = set()
        unique_records = []
        for record in self.tracking_records:
            record_tuple = tuple(record.items())
            if record_tuple not in seen:
                unique_records.append(record)
                seen.add(record_tuple)
        self.tracking_records = unique_records
        
    def _update_pointer_tracking_records(self):
        seen = set()
        unique_records = []
        for record in self.pointer_tracking_records:
            record_tuple = tuple(record.items())
            if record_tuple not in seen:
                unique_records.append(record)
                seen.add(record_tuple)
        self.pointer_tracking_records = unique_records
        
    def redraw_combined_boxes_on_frame(self):
        frame = self._read_frame(self.render_frame_idx)
        if frame is not None:
            # Vẽ box từ file CSV bình thường
            filtered_records = [record for record in self.records if record['frame_idx'] == self.render_frame_idx]
            for record in filtered_records:
                pt1 = (record['x1'], record['y1'])
                pt2 = (record['x2'], record['y2'])
                class_label = record['object_cls']
                cv2.rectangle(frame, pt1, pt2, (0, 0, 255), 2)  # Red color with thicker line
                text = f"{class_label} | ID: {record['object_id']} | {pt1}, {pt2}"
                cv2.putText(frame, text, (pt1[0], pt1[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
            
            # Vẽ box từ file CSV tracking
            filtered_tracking_records = [record for record in self.tracking_records if record['frame_idx'] == self.render_frame_idx]
            for record in filtered_tracking_records:
                pt1 = (record['x1'], record['y1'])
                pt2 = (record['x2'], record['y2'])
                class_label = record['object_cls']
                cv2.rectangle(frame, pt1, pt2, (255, 0, 0), 2)  # Blue color with thicker line
                text = f"{class_label} | ID: {record['object_id']} | {pt1}, {pt2}"
                cv2.putText(frame, text, (pt1[0], pt1[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 208, 23), 2, cv2.LINE_AA)
            
            pixmap = QPixmap(self._ndarray_to_qimage(frame))
            self.label_frame.setPixmap(pixmap)
        
    def redraw_boxes_on_frame(self):
        frame = self._read_frame(self.render_frame_idx)
        if frame is not None:
            filtered_records = [record for record in self.records if record['frame_idx'] == self.render_frame_idx]
            for record in filtered_records:
                pt1 =(record['x1'], record['y1'])
                pt2 = (record['x2'], record['y2'])
                class_label = record['object_cls']
                cv2.rectangle(frame, pt1, pt2, self.label_color, self.label_thickness)
                text = f"{class_label} | ID: {record['object_id']} | {pt1}, {pt2}"
                cv2.putText(frame, text, (pt1[0], pt1[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 1, cv2.LINE_AA)
            pixmap = QPixmap(self._ndarray_to_qimage(frame))
            self.label_frame.setPixmap(pixmap)
            
    def redraw_tracking_boxes_on_frame(self):
        frame = self._read_tracking_frame(self.render_frame_idx)
        if frame is not None:
            filtered_records = [record for record in self.tracking_records if record['frame_idx'] == self.render_frame_idx]
            for record in filtered_records:
                pt1 =(record['x1'], record['y1'])
                pt2 = (record['x2'], record['y2'])
                class_label = record['object_cls']
                cv2.rectangle(frame, pt1, pt2, (255, 0, 0), self.label_thickness)
                text = f"{class_label} | ID: {record['object_id']} | {pt1}, {pt2}"
                cv2.putText(frame, text, (pt1[0], pt1[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 1, cv2.LINE_AA)
                print(self.label_color)
            pixmap = QPixmap(self._ndarray_to_qimage(frame))
            self.label_frame.setPixmap(pixmap)
    
    @property
    def frame_count(self):
        return int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)) if self.cap else None

    @property
    def frame_height(self):
        return int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) if self.cap else None

    @property
    def frame_width(self):
        return int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)) if self.cap else None

    @property
    def video_fps(self):
        return int(self.cap.get(cv2.CAP_PROP_FPS)) if self.cap else None

    def _ndarray_to_qimage(self, image: np.ndarray):
        """convert cv2 image to pyqt5 image
        Arguments:
            image {np.ndarray} -- original RGB image

        Returns:
            {QImage} -- pyqt5 image format
        """
        return QImage(image, image.shape[1], image.shape[0], QImage.Format_RGB888)

    def _frame_idx_to_hmsf(self, frame_idx: int):
        """convert to hmsf timestamp by given frame idx and fps"""
        assert self.video_fps
        base = datetime.strptime('00:00:00.000000', '%H:%M:%S.%f')
        delta = timedelta(seconds=frame_idx/self.video_fps)
        return (base + delta).strftime('%H:%M:%S.%f')

    def _frame_idx_to_hms(self, frame_idx: int):
        """convert to hms timestamp by given frame idx and fps"""
        assert self.video_fps
        base = datetime.strptime('00:00:00', '%H:%M:%S')
        delta = timedelta(seconds=frame_idx//self.video_fps)
        return (base + delta).strftime('%H:%M:%S')

    def _read_frame(self, frame_idx: int):
        """check frame idx and read frame status than return frame
        Arguments:
            frame_idx {int} -- frame index

        Returns:
            {np.ndarray} -- RGB image in (h, w, c)
        """
        if frame_idx >= self.frame_count:
            self.logger.exception('frame index %d should be less than %d', frame_idx, self.frame_count)
        else:
            self.target_frame_idx = frame_idx
            self.cap.set(1, frame_idx)
            read_success, frame = self.cap.read()
            if read_success:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                return frame
            self.logger.exception('read #%d frame failed', frame_idx)
            
    def _read_tracking_frame(self, frame_idx: int):
        """check frame idx and read frame status than return frame
        Arguments:
            frame_idx {int} -- frame index

        Returns:
            {np.ndarray} -- RGB image in (h, w, c)
        """
        if frame_idx >= self.frame_count:
            self.logger.exception('frame index %d should be less than %d', frame_idx, self.frame_count)
        else:
            self.target_frame_idx = frame_idx
            self.cap.set(1, frame_idx)
            read_success, frame = self.cap.read()
            if read_success:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                return frame
            self.logger.exception('read #%d frame failed', frame_idx)

    def _play_video(self):
        """play video when button clicked"""
        if self.is_playing_video and self.video_fps:
            current_idx = self.render_frame_idx if self.render_frame_idx is not None else 0
            frame_idx = min(current_idx + 1, self.frame_count - 1)
            if frame_idx >= self.frame_count - 1:
                self.on_play_video_clicked()
            else:
                self.target_frame_idx = frame_idx
        wait_time_ms = max(1, int(1000 / max(1, self.video_fps or 1)))
        QTimer.singleShot(wait_time_ms, self._play_video)


    def _check_coor_in_frame(self, coor_x: int, coor_y: int):
        """check the coordinate in mouse event"""
        if self.scale_width is None or self.scale_height is None:
            return False
        return 0 < coor_x < self.scale_width and 0 < coor_y < self.scale_height

    def _update_video_info(self):
        shape = str((self.frame_width, self.frame_height))
        self.label_video_path.setText(self.videopath)
        self.label_output_path.setText(str(self.outpath))
        self.label_video_shape.setText(shape)
        self.label_video_fps.setText(str(self.video_fps))
        
    def _update_autosave_info(self):
        self.label_output_path.setText(str(self.outpath))

    def _update_frame(self):
        """read and update image to label"""
        wait_time = max(1, int(1000 / max(1, self.video_fps or 1)))
        if self.target_frame_idx != self.render_frame_idx or self.is_force_update:
            self.is_force_update = False
            
            frame = self._read_frame(self.target_frame_idx)
            if frame is not None:
                # draw, convert, resize pixmap
                #frame = self.draw_rects(self.target_frame_idx, frame)
                frame = self.draw_combined_rects(self.target_frame_idx, frame)
                pixmap = QPixmap(self._ndarray_to_qimage(frame))
                self.scale_width = int(min(pixmap.width(), self.screen.width()*1))
                self.scale_height = int(pixmap.height() * (self.scale_width / pixmap.width()))
                pixmap = pixmap.scaled(self.scale_width, self.scale_height, Qt.KeepAspectRatio)
                self.label_frame.setPixmap(pixmap)
                self.label_frame.resize(self.scale_width, self.scale_height)

                # sync, update related information
                self._update_frame_status(self.target_frame_idx)
                self.render_frame_idx = self.target_frame_idx
                self.slider_video.setValue(self.render_frame_idx)
                #self.presence_bar.setValue(self.render_frame_idx)
        QTimer.singleShot(wait_time, self._update_frame)
        #print('update frame')
        #self.update_box_presence_bar()
        
    def _update_tracking_frame(self):
        """Compatibility method kept for older call sites.

        Tracking overlays are already rendered in _update_frame via draw_combined_rects.
        """
        return
        
    def _update_frame_status(self, frame_idx: int, err: str = ''):
        msg = '#Frame ({}/{})'.format(frame_idx, self.frame_count-1)
        if err:
            msg += '\n{}'.format(err)
        self.label_video_status.setFont(self.font_size_header)
        self.label_video_status.setText(msg)
        
    def _update_tracking_frame_status(self, frame_idx: int, err: str = ''):
        msg = '#Frame ({}/{})'.format(frame_idx, self.frame_count-1)
        if err:
            msg += '\n{}'.format(err)
        self.label_video_status.setFont(self.font_size_header)
        self.label_video_status.setText(msg)

    def _get_records_by_frame_idx(self, frame_idx=None):
        """return specfic records by frame index (default: current frame)"""
        frame_idx = frame_idx or self.render_frame_idx
        return list(filter(lambda x: x['frame_idx'] == frame_idx, self.records))
    
    def _get_tracking_records_by_frame_idx(self, frame_idx=None):
        """return specfic records by frame index (default: current frame)"""
        frame_idx = frame_idx or self.render_frame_idx
        return list(filter(lambda x: x['frame_idx'] == frame_idx, self.tracking_records))

    def _get_nrecord_in_current_frame(self):
        """get the number of records in current frame"""
        current_records = self._get_records_by_frame_idx()
        return len(current_records) if current_records else None
    
    def _get_closest_record_in_current_frame(self, coor_x: int, coor_y: int):
        current_records = deepcopy(self._get_records_by_frame_idx())
        for rid, record in enumerate(current_records):
            pt1, pt2 = (record['x1'], record['y1']), (record['x2'], record['y2'])
            if pt1[0] < coor_x < pt2[0] and pt1[1] < coor_y < pt2[1]:
                center = np.array(((pt2[0]+pt1[0])/2, (pt2[1]+pt1[1])/2))
                dist = np.linalg.norm(center - np.array((coor_x, coor_y)))
                current_records[rid]['dist'] = dist
        current_records = list(filter(lambda x: 'dist' in x, current_records))
        if current_records:
            return sorted(current_records, key=lambda x: x['dist'])[0]
    
    def _remove_record(self, frame_idx: int, pt1: tuple, pt2: tuple):
        current_records = self._get_records_by_frame_idx(frame_idx)
        target_record = None
        for record in current_records:
            src_pt1, src_pt2 = (record['x1'], record['y1']), (record['x2'], record['y2'])
            if src_pt1 == pt1 and src_pt2 == pt2:
                target_record = record
        if target_record:
            self.records.remove(target_record)
            self.remove_record_from_preview(
                frame_idx=target_record['frame_idx'],
                pt1=(target_record['x1'], target_record['y1']),
                pt2=(target_record['x2'], target_record['y2']),
            )
            self.update_presence_bar()
            target_record = None

    @pyqtSlot()
    def _goto_previous_record(self):
        rest_records = list(filter(lambda x: x['frame_idx'] < self.render_frame_idx, self.records))
        if not rest_records:
            QMessageBox.information(self, 'Info', 'no previous record', QMessageBox.Ok)
        else:
            self.target_frame_idx = rest_records[-1]['frame_idx']

    @pyqtSlot()
    def _goto_next_record(self):
        rest_records = list(filter(lambda x: x['frame_idx'] > self.render_frame_idx, self.records))
        if not rest_records:
            QMessageBox.information(self, 'Info', 'no next record', QMessageBox.Ok)
        else:
            self.target_frame_idx = rest_records[0]['frame_idx']

    @pyqtSlot()
    def on_slider_released(self):
        """update frame and frame status when the slider released"""
        self.target_frame_idx = self.slider_video.value()

    @pyqtSlot()
    def on_slider_moved(self):
        """update frame status only when the slider moved"""
        self._update_frame_status(frame_idx=self.slider_video.value())
        
    @pyqtSlot()
    def on_presence_released(self):
        """update frame and frame status when the slider released"""
        self.target_frame_idx = self.presence_bar.value()

    @pyqtSlot()
    def on_presence_moved(self):
        """update frame status only when the slider moved"""
        self._update_frame_status(frame_idx=self.presence_bar.value())  
        
    @pyqtSlot()
    def on_play_video_clicked(self):
        """control to play or pause the video"""
        self.is_playing_video = not self.is_playing_video
        if self.is_playing_video:
            self.btn_play_video.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
            self._play_video()
        else:
            self.btn_play_video.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))

    @pyqtSlot()
    def remove_last_box(self):
        if self.records:
            if self.show_message_box:
                # Tạo một QMessageBox với hai lựa chọn
                message_box = QMessageBox()
                message_box.setWindowTitle("Remove Last Box Confirmation")
                message_box.setText("Do you want to remove the last box?")
                message_box.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ok)
                message_box.setDefaultButton(QMessageBox.Cancel)
                
                # Thêm ô không nhắc lại lần sau
                dont_ask_again_checkbox = QCheckBox("Don't ask again")
                message_box.setCheckBox(dont_ask_again_checkbox)

                # Hiển thị hộp thoại thông báo và chờ người dùng chọn
                choice = message_box.exec_()
                
                if choice == QMessageBox.Ok:  # Nếu người dùng chọn "OK"
                    last_record = self.records.pop()  # Xoá box mới nhất từ danh sách các box
                    self.remove_record_from_preview(
                        frame_idx=last_record['frame_idx'],
                        pt1=(last_record['x1'], last_record['y1']),
                        pt2=(last_record['x2'], last_record['y2']),
                    )
                    self.is_force_update = True
                    self.update_presence_bar()
                    self._update_frame()
                    self.update()
                    
                if dont_ask_again_checkbox.isChecked():
                    # Lưu trạng thái không nhắc lại lần sau vào tệp hoặc cơ sở dữ liệu
                    self.show_message_box = False
            else:
                # Nếu không hiển thị hộp thoại, thực hiện hành động mà không cần xác nhận từ người dùng
                last_record = self.records.pop()
                self.remove_record_from_preview(
                    frame_idx=last_record['frame_idx'],
                    pt1=(last_record['x1'], last_record['y1']),
                    pt2=(last_record['x2'], last_record['y2']),
                )
                self.is_force_update = True                
                self.update_presence_bar()
                #self.update_mot_presence_bar()
                self._update_frame()
                self.update()
                
    # Frame event
    @pyqtSlot()
    def event_frame_mouse_press(self, event):
        if self.render_frame_idx is None or self.scale_width is None or self.scale_height is None:
            return
        if self._check_coor_in_frame(event.x(), event.y()) and not self.is_playing_video:
            try:
                if event.button() == Qt.LeftButton:
                    self.label_frame.pt1 = (event.x(), event.y())
                    self.input_frame_number.setReadOnly(True)
                
            except Exception as e:
                QMessageBox.warning(self, "Error", f"An error occurred")

    @pyqtSlot()
    def event_frame_mouse_move_while_pressed(self, event):
        cursor_pos = event.pos()
        #Cập nhật vị trí hiển thị của label toạ độ
        self.cursor_position_label.setStyleSheet("background-color: rgb(255, 255, 255); color: rgb(0, 0, 0); border: 1px solid rgb(0, 0, 0);")
        self.cursor_position_label.setText(f'  x: {cursor_pos.x()}, y: {cursor_pos.y()}')
        if self.label_frame.pt1:
            self.label_frame.is_drawing = True
            self.label_frame.pt2 = (event.x(), event.y())
            self.label_frame.update()

    @pyqtSlot()
    def event_frame_mouse_release(self, event):
        # Lấy text từ ô Line Edit
        self.notes_text = self.line_edit_notes.text()
        if self.label_frame.pt1:  # Nếu đã có điểm bắt đầu, tức là đang trong quá trình vẽ box
            self.label_frame.is_drawing = False
            pt1 = self.label_frame.pt1
            pt2 = (event.x(), event.y())  # Sử dụng vị trí thứ hai khi thả chuột làm điểm kết thúc của box
            # Kiểm tra xem có phải là click đơn (pt1 và pt2 giống nhau) không
            if pt1 == pt2:
                self.label_frame.pt1 = None  # Xóa điểm bắt đầu
                return
            # Tạo record từ hai điểm này
            record = OrderedDict([
                ('timestamp_hms', self._frame_idx_to_hms(self.render_frame_idx)),
                ('timestamp_hmsf', self._frame_idx_to_hmsf(self.render_frame_idx)),
                ('frame_idx', self.render_frame_idx), ('fps', self.video_fps),
                ('object_cls', self.classes_list[self.current_class_index]),
                ('object_idx', self.object_id), ('object_id', self.object_id),
                ('notes', self.notes_text),
                ('frame_height', self.frame_height), ('frame_width', self.frame_width),
                ('scale_height', self.scale_height), ('scale_width', self.scale_width),
                ('x1', pt1[0]), ('y1', pt1[1]), ('x2', pt2[0]), ('y2', pt2[1]),
                ('center_x', (pt1[0]+pt2[0])//2), ('center_y', (pt1[1]+pt2[1])//2)                
            ])#('pt1', eval(pt1[0], pt1[1])), ('pt2', eval(pt2[0], pt2[1])),
            self.records.append(record)
            self.records = sorted(self.records, key=lambda x: x['frame_idx'])
            self.add_record_to_preview(record['timestamp_hms'], \
                                        record['frame_idx'], \
                                        record['object_cls'], \
                                        record['object_id'], \
                                        (record['notes']), \
                                        (record['x1'], record['y1']), \
                                        (record['x2'], record['y2']))  #(record['pt1']), \
                                        #(record['pt2']))
            self.label_frame.pt1 = self.label_frame.pt2 = None
            self.is_force_update = True
            self.update_presence_bar()
            self.update()  # Cập nhật giao diện để hiển thị box cuối cùng

        # Làm sạch điểm bắt đầu khi thả chuột
        self.label_frame.pt1 = None
        
    @pyqtSlot()
    def event_preview_double_clicked(self):
        row = self.table_preview_records.currentRow()
        if row >= 0:
            frame_idx = int(self.table_preview_records.item(row, 1).text())
            self.target_frame_idx = frame_idx
            
    @pyqtSlot()
    def event_preview_tracking_double_clicked(self):
        row = self.table_preview_tracking_records.currentRow()
        if row >= 0:
            frame_idx = int(self.table_preview_tracking_records.item(row, 1).text())
            self.target_frame_idx = frame_idx
        
    @pyqtSlot()    
    def remove_target_record(self):
        selected_row = self.table_preview_records.currentRow()
        if selected_row >= 0:
            frame_idx = int(self.table_preview_records.item(selected_row, 1).text())
            #target_record_idx = (record for record in self.records if record['frame_idx'] == frame_idx)
            pt1_coord = self.table_preview_records.item(selected_row, 5).text()
            pt2_coord = self.table_preview_records.item(selected_row, 6).text()
            pt1_parsed = parse_point_text(pt1_coord)
            pt2_parsed = parse_point_text(pt2_coord)
            target_record = None

            if pt1_parsed is None or pt2_parsed is None:
                QMessageBox.warning(self, "Error", "Invalid coordinate format in selected row")
                return
            
            if self.records:
                if self.show_message_box_target:
                    for record in self.records:
                        if record['frame_idx'] == frame_idx and (record['x1'], record['y1']) == pt1_parsed and (record['x2'], record['y2']) == pt2_parsed:
                            #print((record['pt1']))
                            target_record = record
                            break
                    if target_record:
                        message_box = QMessageBox()
                        message_box.setWindowTitle("Remove Target Box Confirmation")
                        message_box.setText("Do you want to remove the target box at {}, {}?".format(pt1_coord,pt2_coord))
                        message_box.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ok)
                        message_box.setDefaultButton(QMessageBox.Cancel)
                        dont_ask_again_checkbox = QCheckBox("Don't ask again")
                        message_box.setCheckBox(dont_ask_again_checkbox)
                        choice = message_box.exec_()
                        if choice == QMessageBox.Ok:
                            self.records.remove(target_record)
                            self.table_preview_records.removeRow(selected_row)
                            #target_record = None
                            self.is_force_update = True
                            self.update_presence_bar()
                            self._update_frame()
                            self.update()
                            
                        if dont_ask_again_checkbox.isChecked():
                            self.show_message_box_target = False
                    else:
                        QMessageBox.warning(self, "Error", "Target record not found!")
                else:
                    for record in self.records:
                        if record['frame_idx'] == frame_idx and (record['x1'], record['y1']) == pt1_parsed and (record['x2'], record['y2']) == pt2_parsed:
                            target_record = record
                            break
                    if target_record:
                        self.records.remove(target_record)
                        self.table_preview_records.removeRow(selected_row)
                        #target_record = None
                        self.is_force_update = True
                        self.update_presence_bar()
                        #self.update_mot_presence_bar()
                        self._update_frame()
                        self.update()                    
                    
    @pyqtSlot()    
    def remove_target_tracking_record(self):
        selected_row = self.table_preview_tracking_records.currentRow()
        if selected_row >= 0:
            frame_idx = int(self.table_preview_tracking_records.item(selected_row, 1).text())
            #target_record_idx = (record for record in self.records if record['frame_idx'] == frame_idx)
            pt1_coord = self.table_preview_tracking_records.item(selected_row, 5).text()
            pt2_coord = self.table_preview_tracking_records.item(selected_row, 6).text()
            pt1_parsed = parse_point_text(pt1_coord)
            pt2_parsed = parse_point_text(pt2_coord)
            target_record = None

            if pt1_parsed is None or pt2_parsed is None:
                QMessageBox.warning(self, "Error", "Invalid coordinate format in selected row")
                return
            
            if self.tracking_records:
                if self.show_message_box_target:
                    for record in self.tracking_records:
                        if record['frame_idx'] == frame_idx and (record['x1'], record['y1']) == pt1_parsed and (record['x2'], record['y2']) == pt2_parsed:
                            #print((record['pt1']))
                            target_record = record
                            break
                    if target_record:
                        message_box = QMessageBox()
                        message_box.setWindowTitle("Remove Target Box Confirmation")
                        message_box.setText("Do you want to remove the target box at {}, {}?".format(pt1_coord,pt2_coord))
                        message_box.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ok)
                        message_box.setDefaultButton(QMessageBox.Cancel)
                        dont_ask_again_checkbox = QCheckBox("Don't ask again")
                        message_box.setCheckBox(dont_ask_again_checkbox)
                        choice = message_box.exec_()
                        if choice == QMessageBox.Ok:
                            self.tracking_records.remove(target_record)
                            self.table_preview_tracking_records.removeRow(selected_row)
                            #target_record = None
                            self.is_force_update = True
                            self.update_mot_presence_bar()
                            self.update_pointer_object()
                            self._update_frame()
                            self.update()
                            
                        if dont_ask_again_checkbox.isChecked():
                            self.show_message_box_target = False
                    else:
                        QMessageBox.warning(self, "Error", "Target record not found!")
                else:
                    for record in self.tracking_records:
                        if record['frame_idx'] == frame_idx and (record['x1'], record['y1']) == pt1_parsed and (record['x2'], record['y2']) == pt2_parsed:
                            target_record = record
                            break
                    if target_record:
                        self.tracking_records.remove(target_record)
                        self.table_preview_tracking_records.removeRow(selected_row)
                        #target_record = None
                        self.is_force_update = True
                        #self.update_presence_bar()
                        self.update_mot_presence_bar()
                        self.update_pointer_object()
                        self._update_frame()
                        self.update()
                                    
    @pyqtSlot()  
    def contextMenuEvent(self, event):
        frame_local_pos = self.label_frame.mapFromGlobal(event.globalPos())
        if not self._check_coor_in_frame(frame_local_pos.x(), frame_local_pos.y()):
            return
        self._context_click_pos = (frame_local_pos.x(), frame_local_pos.y())

        menu = QMenu(self)
        remove_action = QAction("Remove", self)
        remove_action.triggered.connect(self.event_remove_record)
        menu.addAction(remove_action)
        menu.exec_(event.globalPos())

    @pyqtSlot()
    def event_remove_record(self):
        if not hasattr(self, '_context_click_pos') or self.render_frame_idx is None:
            return

        coor_x, coor_y = self._context_click_pos
        target_record = self._get_closest_record_in_current_frame(coor_x, coor_y)
        if not target_record:
            return

        self._remove_record(
            frame_idx=target_record['frame_idx'],
            pt1=(target_record['x1'], target_record['y1']),
            pt2=(target_record['x2'], target_record['y2']),
        )
        self.is_force_update = True
        self._update_frame()
        self.update()
    
   
    def draw_rects(self, frame_idx: int, frame: np.ndarray):
        rest_records = list(filter(lambda x: x['frame_idx'] == frame_idx, self.records))
        if not rest_records:
            return frame
        for record in rest_records:
            pt1, pt2 = (record['x1'], record['y1']), (record['x2'], record['y2'])
            cv2.rectangle(frame, pt1, pt2, self.label_color, self.label_thickness)
            text = f"{record['object_cls']} | ID: {record['object_id']} | {pt1}, {pt2}"
            cv2.putText(frame, text, (pt1[0], pt1[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 1, cv2.LINE_AA)
        return frame 
    
    def draw_tracking_rects(self, frame_idx: int, frame: np.ndarray):
        rest_records = list(filter(lambda x: x['frame_idx'] == frame_idx, self.tracking_records))
        if not rest_records:
            return frame
        for record in rest_records:
            pt1, pt2 = (record['x1'], record['y1']), (record['x2'], record['y2'])
            cv2.rectangle(frame, pt1, pt2, (255, 208, 23), self.label_thickness)
            text = f"{record['object_cls']} | ID: {record['object_id']} | {pt1}, {pt2}"
            cv2.putText(frame, text, (pt1[0], pt1[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 208, 23), 1, cv2.LINE_AA)
        return frame 
    

    def draw_combined_rects(self, frame_idx, frame):
        filtered_records = [record for record in self.records if record['frame_idx'] == frame_idx]
        for record in filtered_records:
            pt1 = (record['x1'], record['y1'])
            pt2 = (record['x2'], record['y2'])
            class_label = record['object_cls']
            color = (0, 0, 255)  # Red color
            text = f"{class_label} | ID: {record['object_id']} | {pt1}, {pt2}"
            text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0]

            # Determine the position for the text background
            text_x = min(pt1[0], pt2[0])
            text_y = min(pt1[1], pt2[1]) - 5
            if text_y < 20:
                text_y = min(pt1[1], pt2[1]) + text_size[1] + 5
            
            # Draw the rectangle (background for text)
            cv2.rectangle(frame, (text_x-2, text_y - text_size[1] - 5), (text_x + text_size[0], text_y + 5), color, cv2.FILLED)
            # Draw the rectangle around the object
            cv2.rectangle(frame, pt1, pt2, color, self.label_thickness)
            # Draw the text
            cv2.putText(frame, text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)

        filtered_tracking_records = [record for record in self.tracking_records if record['frame_idx'] == frame_idx]
        for record in filtered_tracking_records:
            pt1 = (record['x1'], record['y1'])
            pt2 = (record['x2'], record['y2'])
            class_label = record['object_cls']
            color = (255, 208, 23)  # Blue color
            text = f"{class_label} | ID: {record['object_id']} | {pt1}, {pt2} | Tracking"
            text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 1)[0]

            # Determine the position for the text background
            text_x = min(pt1[0], pt2[0])
            text_y = min(pt1[1], pt2[1]) - 5
            if text_y < 20:
                text_y = min(pt1[1], pt2[1]) + text_size[1] + 5
            
            # Draw the rectangle (background for text)
            cv2.rectangle(frame, (text_x-2, text_y - text_size[1] - 5), (text_x + text_size[0], text_y + 5), color, cv2.FILLED)
            # Draw the rectangle around the object
            cv2.rectangle(frame, pt1, pt2, color, self.label_thickness)
            # Draw the text
            cv2.putText(frame, text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)

        return frame

    def update_presence_bar(self):
        """Update the presence bar to reflect frames with annotations."""
        annotations = {record['frame_idx']: [2] for record in self.records}
        self.presence_bar.setAnnotations(annotations)
        self.presence_bar.redraw()
        #print('update_presence_bar')
    
        
    def update_mot_presence_bar(self):
        """Update the presence bar to reflect frames with annotations."""
        annotations = {record['frame_idx']: [1] for record in self.tracking_records}
        self.mot_presence_bar.setAnnotations(annotations)
        self.mot_presence_bar.redraw()
        #print('update_mot_presence_bar')
        
    def update_pointer_object(self):
        """Update the presence bar to reflect frames with annotations."""
        annotations = {record['frame_idx']: [1] for record in self.pointer_tracking_records}
        self.pointer_object.setAnnotations(annotations)
        self.pointer_object.redraw()
    
    def toggle_auto_save(self, state):
        # Xử lý sự kiện khi trạng thái của QCheckBox thay đổi
        if state == Qt.Checked:
            self.logger.info("Auto save is enabled")
            self.auto_save_enabled = True
            self.auto_save_thread.set_enabled(True)
            self.auto_save()
        else:
            self.logger.info("Auto save is disabled")
            self.auto_save_enabled = False
            self.auto_save_thread.set_enabled(False)

    def _save_records_if_needed(self, force: bool = False):
        current_checksum = records_checksum(self.records)
        if not force and current_checksum == self._last_saved_checksum:
            return False

        save_records_to_csv(self.records, Path(self.outpath))
        self._last_saved_checksum = current_checksum
        return True
            
    # def disable_auto_save(self, state):
    #     if state == Qt.Checked:
    #         self.logger.info("Auto save is disabled")
    #         self.auto_save_enabled = False
    #         state = Qt.Unchecked

    def auto_save(self):
        if not self.checkbox_auto_save.isChecked() or self._autosave_in_progress:
            return

        self._autosave_in_progress = True
        try:
            self._save_records_if_needed(force=False)
        except Exception as e:
            self.logger.exception("Auto save failed: %s", e)
        finally:
            self._autosave_in_progress = False
        
    def closeEvent(self, event):
        """Xử lý sự kiện khi cửa sổ đóng"""
        self.auto_save_thread.stop()
        self.auto_save_thread.wait()  # Chờ luồng auto save kết thúc trước khi đóng cửa sổ
        event.accept()
     
    def save_file(self):
        if self.is_new_video_opened:  # Nếu đã mở video mới
            self.checkbox_auto_save.setChecked(False)
            self.is_new_video_opened = False
            self.auto_save_enabled = False
            exist_msg = 'File <b>{}</b> exist.<br/><br/>\
                            Do you want to replace?'.format(self.outpath) # self.outpath -> self.videopath
            info_msg = 'Save at <b>{}</b><br/>\
                        Total records: {}'.format(self.outpath, len(self.records))

            # check the file existense
            exist_reply = QMessageBox.No
            # if Path(self.outpath).exists():
            #     exist_reply = QMessageBox.question(self, 'File Exist', exist_msg, \
            #                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            # if not Path(self.outpath).exists() or exist_reply == QMessageBox.Yes:
            self._save_records_if_needed(force=True)

            # check if the application is going to close
            reply = QMessageBox.about(self, 'Info', info_msg)
            
        else:
            exist_msg = 'File <b>{}</b> exist.<br/><br/>\
                            Do you want to replace?'.format(self.outpath) # self.outpath -> self.videopath
            info_msg = 'Save at <b>{}</b><br/>\
                        Total records: {}'.format(self.outpath, len(self.records))

            # check the file existense
            exist_reply = QMessageBox.No
            # if Path(self.outpath).exists():
            #     exist_reply = QMessageBox.question(self, 'File Exist', exist_msg, \
            #                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            # if not Path(self.outpath).exists() or exist_reply == QMessageBox.Yes:
            self._save_records_if_needed(force=True)

            # check if the application is going to close
            reply = QMessageBox.about(self, 'Info', info_msg)
            # self.close()      
        
    @pyqtSlot()  
    def to_next_frame(self):
        self.target_frame_idx = min(self.target_frame_idx+1, self.frame_count-1)
        
    @pyqtSlot()  
    def to_back_frame(self):
        self.target_frame_idx = max(0, self.target_frame_idx-1)
        
    @pyqtSlot()
    def to_change_class_name(self):
        self.current_class_index = (self.current_class_index + 1) % len(self.classes_list)
        if self.combo_object_class.currentIndex() != self.current_class_index:
            self.combo_object_class.setCurrentIndex(self.current_class_index)

    @pyqtSlot()
    def to_increase_object_id(self):
        self.object_id += 1
        if self.spin_object_id.value() != self.object_id:
            self.spin_object_id.setValue(self.object_id)
        
    def to_decrease_object_id(self):
        if self.object_id > 1:
            self.object_id -= 1
            if self.spin_object_id.value() != self.object_id:
                self.spin_object_id.setValue(self.object_id)

    @pyqtSlot(int)
    def on_object_id_selected(self, value: int):
        self.object_id = max(1, int(value))

    @pyqtSlot(int)
    def on_class_selected(self, index: int):
        if 0 <= index < len(self.classes_list):
            self.current_class_index = index
        
    def reload_app(self):
        """Phương thức để reload lại ứng dụng"""
        
        # Tạo một QMessageBox với hai lựa chọn
        message_box = QMessageBox()
        message_box.setWindowTitle("Reload Confirmation")
        message_box.setText("Do you want to reload the application? All data will be cleared.")
        message_box.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ok)
        message_box.setDefaultButton(QMessageBox.Cancel)

        # Hiển thị hộp thoại thông báo và chờ người dùng chọn
        choice = message_box.exec_()
        
        if choice == QMessageBox.Ok:  # Nếu người dùng chọn "OK"
            # Xoá dữ liệu trong records
            if self.records:
                self.remove_all_records_from_preview()
                self.remove_all_tracking_records_from_preview()
                self.records = []
                self.is_force_update = True
            if self.tracking_records:
                self.remove_all_records_from_preview()
                self.remove_all_tracking_records_from_preview()
                self.tracking_records = []
                self.is_force_update = True
            if self.pointer_tracking_records:
                self.pointer_tracking_records = []
                self.is_force_update = True
                
            # Đặt lại các thông số liên quan đến video
            if self.cap:
                self.cap.release()
            self.cap = cv2.VideoCapture(self.videopath)
            self.target_frame_idx = 0       # sẵn sàng cập nhật
            self.render_frame_idx = None    # đã render
            self.scale_height = self.scale_width = None
            self.is_playing_video = False
            self.is_force_update = False
            self._update_video_info()
            self.update_presence_bar()
            self.update_mot_presence_bar()
            self.update_pointer_object()
            # if self.auto_save_enabled:
            #     self.disable_auto_save()
            self.remove_all_tracking_records_from_preview()
            self._update_frame()
            self._update_tracking_frame()

        
    def remove_all_records_from_preview(self):
        """Xoá hết các hàng trong bảng xem trước"""
        while self.table_preview_records.rowCount() > 0:
            self.table_preview_records.removeRow(0)
        self.update_presence_bar()    
        self._update_frame()
        
        
    def remove_all_tracking_records_from_preview(self):
        """Xoá hết các hàng trong bảng xem trước"""
        while self.table_preview_tracking_records.rowCount() > 0:
            self.table_preview_tracking_records.removeRow(0)
        self.update_mot_presence_bar()    
        self._update_tracking_frame()
        
    def keyPressEvent(self, event):
        """global keyboard event"""
        try:
            if event.key() in [Qt.Key_Space, Qt.Key_P]:
                self.on_play_video_clicked()
            elif event.key() in [Qt.Key_Right, Qt.Key_N]:
                self.to_next_frame()
            elif event.key() in [Qt.Key_Left, Qt.Key_B]:
                self.to_back_frame()
            elif event.key() == Qt.Key_F:
                self.to_increase_object_id()
            elif event.key() == Qt.Key_D:
                self.to_decrease_object_id()
            elif event.key() == Qt.Key_C:
                self.to_change_class_name()
            elif event.key() == Qt.Key_R:
                self.remove_last_box()
            elif event.key() in [Qt.Key_T, Qt.Key_Delete]:
                self.remove_target_record()   
            elif event.key() == Qt.Key_Escape:
                self.close()
            
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred")


def _resource_path(relative_path: str) -> Path:
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS) / relative_path
    return Path(__file__).resolve().parents[0] / relative_path


CONFIG_FILE = str(_resource_path('config.yaml'))
    
# Open video
def get_video_file():
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    file_path = filedialog.askopenfilename(title="Select Video File", filetypes=[("Video files", "*.mp4")])
    root.destroy()
    return file_path
    
def main():
    """an interface to activate pyqt5 app"""
    logger = logging.getLogger(__name__)
    log_handler(logger)
    
    
    with open(CONFIG_FILE, 'r') as config_file:
        config = yaml.safe_load(config_file)
    

       
    video_file = get_video_file()
    if not video_file:
        logger.error("No file selected. Exiting.")
        sys.exit(1)

    video_path = Path(video_file)
    output_path = Path('outputs')
    if not output_path.exists():
        output_path.mkdir(parents=True)
    label_path = output_path / '{}_label.csv'.format(video_path.stem)
    if not label_path.parent.exists():
        label_path.parent.mkdir(parents=True)

    app = QApplication(sys.argv)
    video_app = VideoApp(video_file, str(label_path), **config)
    
    try:
        log_handler(video_app.logger)
        app.exec()
    except Exception as e:
        logger.exception(e)
        
if __name__ == '__main__':
    main()