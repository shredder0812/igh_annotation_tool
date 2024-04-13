import argparse
import logging
from pathlib import Path
import yaml
import cv2
import numpy as np
import pandas as pd
import logging
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
import logging
from PyQt5.QtCore import Qt, QTimer, pyqtSlot, QRect, QThread, pyqtSignal, QEvent
from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QImage, QPixmap, QCursor
from PyQt5.QtWidgets import (QMenuBar, QFileDialog, QAbstractItemView, QDesktopWidget, QGridLayout,
                             QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QSlider, QStyle, QTableWidget, QCheckBox,
                             QTableWidgetItem, QVBoxLayout, QWidget, QScrollArea,
                             QMessageBox, QWidget, QApplication, QMenu, QAction, QDesktopWidget, QTextEdit)
import logging
import sys
from functools import wraps
from tkinter import filedialog
import tkinter as tk


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

class AutoSaveThread(QThread):
    save_completed = pyqtSignal()
    def __init__(self, parent=None):
        """Initialize the AutoSaveThread."""
        super(AutoSaveThread, self).__init__(parent)
        self.auto_save_enabled = True

    def run(self):
        while self.auto_save_enabled:
            # Perform saving
            self.save_completed.emit()
            self.sleep(3)  # Wait for 3 seconds before saving again

    def stop(self):
        self.auto_save_enabled = False


# View
class VideoFrameViewer(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.logger = logging.getLogger(__name__)
        self.is_drawing = False
        self.is_selecting = False
        self.pt1 = self.pt2 = None
        self.select_pt1 = self.select_pt2 = None
        
        # case: draw config
        self.draw_color = QColor(0, 0, 0)
        self.draw_thickness = 1
        self.draw_style = Qt.SolidLine

        # case: select config
        self.select_color = QColor(0, 0, 0)
        self.select_thickness = 2
        self.select_style = Qt.SolidLine
        
        # cursor
        cursor_image = QPixmap(3000, 3000)
        cursor_image.fill(Qt.transparent)  
        painter = QPainter(cursor_image)
        painter.setPen(Qt.red)  
        painter.drawLine(1500, 0, 1500, 3000) 
        painter.drawLine(0, 1500, 3000, 1500) 
        painter.end()
        cursor = QCursor(cursor_image, 1500, 1500)  
        self.setCursor(cursor)

    def revise_coor(self, pt1: tuple, pt2: tuple):
        revise_pt1 = (min(pt1[0], pt2[0]), min(pt1[1], pt2[1]))
        revise_pt2 = (max(pt1[0], pt2[0]), max(pt1[1], pt2[1]))
        return (revise_pt1, revise_pt2)

    def _draw_rect(self, pt1: tuple, pt2: tuple, pen: QPen):
        painter = QPainter()
        painter.begin(self)
        painter.setPen(pen)
        pt1_x, pt1_y, pt2_x, pt2_y = pt1[0], pt1[1], pt2[0], pt2[1]
        width, height = (pt2_x - pt1_x), (pt2_y - pt1_y)
        painter.drawRect(pt1_x, pt1_y, width, height)
        painter.end()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.is_drawing and self.pt1 and self.pt2:
            pen = QPen(self.draw_color, self.draw_thickness, self.draw_style)
            pt1, pt2 = self.revise_coor(self.pt1, self.pt2)
            self._draw_rect(pt1, pt2, pen)

        elif not self.is_drawing and self.select_pt1 and self.select_pt2:
            pen = QPen(self.select_color, self.select_thickness, self.select_style)
            pt1, pt2 = self.revise_coor(self.select_pt1, self.select_pt2)
            self._draw_rect(pt1, pt2, pen)

class VideoAppViewer(QWidget):
    def __init__(self, title='IGH Annotation Tool'):
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
                
        # auto save thread
        self.auto_save_enabled = False
        self.auto_save_thread = AutoSaveThread()
        self.auto_save_thread.save_completed.connect(self.auto_save)
        self.auto_save_thread.start()
        
        
        # init window - init and set default config about window
        self.setWindowTitle(self.title)
                
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
        self.label_video_objid = QLabel()
        self.label_video_objid.setAlignment(Qt.AlignLeft)
        self.label_video_objid.setText(str(self.object_id))        
        self.label_video_objcls = QLabel()
        self.label_video_objcls.setAlignment(Qt.AlignLeft)
        self.label_video_objcls.setText(self.classes_list[self.current_class_index])        
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
        sub_grid.addWidget(self.label_video_objid, 4, 1)
        sub_grid.addWidget(label_objcls, 5, 0)
        sub_grid.addWidget(self.label_video_objcls, 5, 1)
        
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
        self.btn_jump_to_frame.clicked.connect(self.jump_to_frame)
        hbox_video_controls.addWidget(self.btn_jump_to_frame)
        vbox_option.addLayout(hbox_video_controls)
        
        # vbox_panel/hbox_video: show process about video
        self.btn_play_video_info = QGroupBox('Play/Pause Video (P)')
        self.btn_play_video_info.setFont(self.font_size_header)
        hbox_video_slider = QHBoxLayout()
        self.btn_play_video = QPushButton()
        self.btn_play_video_back_frame = QPushButton()
        self.btn_play_video.setEnabled(True)
        self.btn_play_video_back_frame.setEnabled(True)
        self.btn_play_video.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.slider_video = QSlider(Qt.Horizontal)
        self.slider_video.setRange(0, 0)
        hbox_video_slider.addWidget(self.btn_play_video)
        hbox_video_slider.addWidget(self.slider_video)
        self.btn_play_video_info.setLayout(hbox_video_slider)
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
        self.btn_to_back_frame.setFont(self.font_size)
        next_and_back_button.addWidget(self.btn_to_back_frame)
        self.btn_to_next_frame = QPushButton('Next Frame (N)')
        self.btn_to_next_frame.setFont(self.font_size)
        next_and_back_button.addWidget(self.btn_to_next_frame)
        vbox_option.addLayout(next_and_back_button)
        self.btn_to_change_class = QPushButton('Change Class (C)')
        self.btn_to_change_class.setFont(self.font_size)
        object_id_push_button.addWidget(self.btn_to_change_class)
        self.btn_to_decrease_id = QPushButton('Decrease Object ID (D)')
        self.btn_to_decrease_id.setFont(self.font_size)
        object_id_push_button.addWidget(self.btn_to_decrease_id)
        self.btn_to_increase_id = QPushButton('Increase Object ID (F)')
        self.btn_to_increase_id.setFont(self.font_size)
        object_id_push_button.addWidget(self.btn_to_increase_id)
        vbox_option.addLayout(object_id_push_button)
        vbox_option.addLayout(hbox_jump_records)
        
        self.btn_remove_last_box = QPushButton('Remove Last Box (R)')
        self.btn_remove_last_box.setFont(self.font_size)
        remove_box.addWidget(self.btn_remove_last_box)
        self.btn_remove_target_box = QPushButton('Remove Target Box (Delete)')
        self.btn_remove_target_box.setFont(self.font_size)
        remove_box.addWidget(self.btn_remove_target_box)
        vbox_option.addLayout(remove_box)
        
        self.checkbox_auto_save = QCheckBox("Auto Save")
        self.checkbox_auto_save.setFont(self.font_size)
        vbox_option.addWidget(self.checkbox_auto_save)
        self.btn_export_records = QPushButton('Export')
        self.btn_export_records.setFont(self.font_size)
        vbox_option.addWidget(self.btn_export_records)

        # vbox_option/table_preview_record: preview the summary of records
        self.table_preview_records = self._get_preview_table(self)
        vbox_option.addWidget(self.table_preview_records)

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
    
    def _get_header_label(self, text: str = ''):
        label = QLabel(text)
        label.setFont(self.font_header)
        #label.setFont(self.font_size)
        label.setAlignment(Qt.AlignLeft)
        return label
    
    def _get_preview_table(self, parent):
        table = QTableWidget(parent=parent)
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels(['Timestamp', 'Frame', 'Class' , 'Object ID', 'Notes' , 'Pt1', 'Pt2'])
        table.setSortingEnabled(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.resizeColumnsToContents()
        table.setColumnWidth(2, table.columnWidth(2) + 80)  # Cột 3
        table.setColumnWidth(4, table.columnWidth(4) + 80)  # Cột 5
        table.setColumnWidth(5, table.columnWidth(5) + 40)  # Cột 6
        table.setColumnWidth(6, table.columnWidth(6) + 40)  # Cột 7
        # Đặt kích thước chữ là 10
        font = table.font()
        font.setPointSize(10)
        table.setFont(font)

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
    
    def remove_record_from_preview(self, num_rows: int = 1):
            self.table_preview_records.removeRow(0)
            
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
    
    
# App
class VideoApp(VideoAppViewer):
    def __init__(self, videopath: str, outpath: str, **config):
        # self.videopath = videopath
        self.outpath = outpath
        self.videopath = video_file
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
        super().__init__(title=self.title)
        
        self.show_message_box = True
        self.show_message_box_target = True
        
        self.is_new_video_opened = False
              
        # draw config
        if self.config.get('draw') and isinstance(self.config['draw'], dict):
            draw_config = self.config['draw']
            self.label_frame.draw_color = draw_config.get('color', QColor(0, 0, 0))
            self.label_frame.draw_thickness = draw_config.get('thickness', 2)
            self.label_frame.draw_style = draw_config.get('style', Qt.SolidLine)
        if self.config.get('select') and isinstance(self.config['select'], dict):
            select_config = self.config['select']
            self.label_frame.select_color = select_config.get('color', QColor(0, 0, 0))
            self.label_frame.select_thickness = select_config.get('thickness', 3)
            self.label_frame.select_style = select_config.get('style', Qt.SolidLine)

        # record config
        check_label = self.config.get('label')
        label_color = self.config['label'].get('color', (0, 0, 0)) if check_label else None
        label_thickness = self.config['label'].get('thickness', 2) if check_label else None
        self.label_color = label_color
        self.label_thickness = label_thickness
        self.limit_nlabel = self.config.get('limit_nlabel', None)
        self.records = []

        # read video
        self.cap = cv2.VideoCapture(self.videopath)
        self.target_frame_idx = 0       # ready to update
        self.render_frame_idx = None    # redneded
        self.scale_height = self.scale_width = None
        self.is_playing_video = False
        self.is_force_update = False
        self._update_video_info()
        self._update_frame()
        
        # widget binding
        self.slider_video.setRange(0, self.frame_count-1)
        self.slider_video.sliderMoved.connect(self.on_slider_moved)
        self.slider_video.sliderReleased.connect(self.on_slider_released)
        self.btn_play_video.clicked.connect(self.on_play_video_clicked)
        self.btn_to_back_frame.clicked.connect(self.to_back_frame)
        self.btn_to_next_frame.clicked.connect(self.to_next_frame)        
        self.btn_to_change_class.clicked.connect(self.to_change_class_name)
        self.btn_to_decrease_id.clicked.connect(self.to_decrease_object_id)
        self.btn_to_increase_id.clicked.connect(self.to_increase_object_id)      
        #self.btn_continue.clicked.connect(self.continue_function)
        self.label_frame.mousePressEvent = self.event_frame_mouse_press
        self.label_frame.mouseMoveEvent = self.event_frame_mouse_move
        self.label_frame.mouseReleaseEvent = self.event_frame_mouse_release
        self.btn_export_records.clicked.connect(self.save_file)
        self.btn_remove_last_box.clicked.connect(self.remove_last_box)
        self.btn_remove_target_box.clicked.connect(self.remove_target_record)
        self.table_preview_records.doubleClicked.connect(self.event_preview_double_clicked)
        self.checkbox_auto_save.stateChanged.connect(self.toggle_auto_save)
        self.showMaximized()
    
    def init_menu_bar(self):
        # Tạo menu bar
        menubar = QMenuBar(self)
        menubar.setGeometry(0, 0, 34, 20)
        # Tạo menu "File"
        file_menu = menubar.addMenu('File')
        # Tạo action "Open File" và gán sự kiện
        open_action = QAction('&Open File (MP4)', self)
        open_action.setShortcut('Ctrl+O')
        open_action.triggered.connect(self.open_video_file)
        file_menu.addAction(open_action)
        # Tạo action "Import File" và gán sự kiện
        import_action = QAction('&Import File (CSV)', self)
        import_action.triggered.connect(self.import_csv_file)
        file_menu.addAction(import_action)
        # Tạo action "Reload" và gán sự kiện
        reload_action = QAction('&Reload', self)
        reload_action.triggered.connect(self.reload_app)
        file_menu.addAction(reload_action)
        
        # # Tạo menu "Settings"
        # file_menu = menubar.addMenu('Setting')
        # setting_action = QAction('&Change Classes', self)
        # setting_action.triggered.connect(self.change_class)
        # file_menu.addAction(setting_action)
    
    def change_class(self):
        dialog = QWidget()
        layout = QVBoxLayout()
        text_edit = QTextEdit()
        layout.addWidget(text_edit)
        # Tạo nút OK
        ok_button = QPushButton("OK")
        #ok_button.clicked.connect(lambda: self.update_classes(text_edit.toPlainText()))
        layout.addWidget(ok_button)
        dialog.setLayout(layout)
        dialog.setWindowTitle("Change Classes")
        dialog.exec_()

    def update_classes(self, new_classes):
        try:
            # Đọc tệp config.yaml
            with open(CONFIG_FILE, 'r') as file:
                config_data = yaml.safe_load(file)

            # Cập nhật danh sách lớp
            config_data['classes'] = [class_name.strip() for class_name in new_classes.split('\n')]

            # Ghi lại vào tệp config.yaml
            with open(CONFIG_FILE, 'w') as file:
                yaml.dump(config_data, file)

            # Yêu cầu restart app
            QMessageBox.information(self, "Success", "Classes updated successfully. Please restart the app.")

        except Exception as e:
            QMessageBox.warning(self, "Error", f"An error occurred: {str(e)}")
            
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
                    self.records = []
                    self.is_force_update = True
                    
                # Đặt lại các thông số liên quan đến video
                #self.videopath = file_path_open
                video_path_open = Path(self.videopath)
                output_path_open = Path('outputs')
                if not output_path_open.exists():
                    output_path_open.mkdir(parents=True)
                label_output_path_open = output_path_open / '{}_label.csv'.format(video_path_open.stem)
                self.outpath = label_output_path_open
                self.cap = cv2.VideoCapture(self.videopath)
                self.target_frame_idx = 0       # sẵn sàng cập nhật
                self.render_frame_idx = None    # đã render
                self.scale_height = self.scale_width = None
                self.is_playing_video = False
                self.is_force_update = False
                self._update_video_info()
                self._update_frame()
            
            #self._update_video_info()
        return self.videopath
        #pass
    
    def import_csv_file(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(self, "Import CSV File", "", "CSV Files (*.csv)", options=options)
        if file_path:
            self.read_csv_file(file_path)
            
    def read_csv_file(self, file_path):
        self.remove_all_records_from_preview()
        try:
            df = pd.read_csv(file_path)
            # Xử lý dữ liệu đọc được từ file CSV và cập nhật vào danh sách self.records
            self.records = []  # Đảm bảo rằng danh sách self.records trống trước khi cập nhật dữ liệu mới
            new_records = []
            for index, row in df.iterrows():
                notes_value = row['notes'] if pd.notna(row['notes']) else ''
                record = OrderedDict([
                        ('timestamp_hms', row['timestamp_hms']),
                        ('timestamp_hmsf', row['timestamp_hmsf']),
                        ('frame_idx', row['frame_idx']), ('fps', row['fps']),
                        ('object_cls', row['object_cls']), ('object_cls', row['object_cls']),
                        ('object_idx', row['object_idx']), ('object_id', row['object_id']),
                        ('notes', notes_value),
                        ('frame_height', row['frame_height']), ('frame_width', row['frame_width']),
                        ('scale_height', row['scale_height']), ('scale_width', row['scale_width']),
                        ('x1', row['x1']), ('y1', row['y1']), ('x2', row['x2']), ('y2', row['y2']),
                        ('center_x', row['center_x']), ('center_y', row['center_y'])
                        ])#('pt1', row['pt1']), ('pt2', row['pt2']),
                if not self._is_duplicate(record):
                    new_records.append(record)
                self.records.extend(new_records)  # Thêm các bản ghi mới vào danh sách tồn tại
                self._update_records()
                if not record['notes']:
                    record['notes'] = ''
                self.add_record_to_preview(record['timestamp_hms'], \
                                                record['frame_idx'], \
                                                record['object_cls'], \
                                                record['object_id'], \
                                                (record['notes']), \
                                                (record['x1'], record['y1']), \
                                                (record['x2'], record['y2'])) \
                                                #(record['pt1']), \
                                                #(record['pt2']))
                self.is_force_update = True
                self.update()  # Cập nhật giao diện để hiển thị box cuối cùng
                
            # Hiển thị thông tin về số lượng bản ghi đã được import
            QMessageBox.about(self, 'Info', 'Imported {} records from CSV file.'.format(len(self.records)))
            self.redraw_boxes_on_frame()
            self.render_frame_idx = max(record['frame_idx'] for record in self.records)
        except Exception as e:
            QMessageBox.critical(self, 'Error', 'Error occurred while importing CSV file: {}'.format(str(e)))

    
    def _is_duplicate(self, new_record):
        for record in self.records:
            if record == new_record:
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

    def _play_video(self):
        """play video when button clicked"""
        if self.is_playing_video and self.video_fps:
            frame_idx = min(self.render_frame_idx+1, self.frame_count)
            if frame_idx == self.frame_count:
                self.on_play_video_clicked()
            else:
                self.target_frame_idx = frame_idx
        QTimer.singleShot(int(1/self.video_fps), self._play_video)


    def _check_coor_in_frame(self, coor_x: int, coor_y: int):
        """check the coordinate in mouse event"""
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
        if self.target_frame_idx != self.render_frame_idx or self.is_force_update:
            self.is_force_update = False
            
            frame = self._read_frame(self.target_frame_idx)
            if frame is not None:
                # draw, convert, resize pixmap
                frame = self.draw_rects(self.target_frame_idx, frame)
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
        wait_time = int(1000/self.video_fps)
        QTimer.singleShot(wait_time, self._update_frame)
        
    def _update_frame_status(self, frame_idx: int, err: str = ''):
        msg = '             #Frame ({}/{})             '.format(frame_idx, self.frame_count-1)
        if err:
            msg += '\n{}'.format(err)
        self.label_video_status.setFont(self.font_size_header)
        self.label_video_status.setText(msg)

    def _get_records_by_frame_idx(self, frame_idx=None):
        """return specfic records by frame index (default: current frame)"""
        frame_idx = frame_idx or self.render_frame_idx
        return list(filter(lambda x: x['frame_idx'] == frame_idx, self.records))

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
            target_row_idx = self.records.index(target_record)
            self.records.remove(target_record)
            self.remove_record_from_preview(target_row_idx)
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
                    self.remove_record_from_preview(last_record['frame_idx'])
                    self.is_force_update = True
                    self._update_frame()
                    self.update()
                    
                if dont_ask_again_checkbox.isChecked():
                    # Lưu trạng thái không nhắc lại lần sau vào tệp hoặc cơ sở dữ liệu
                    self.show_message_box = False
            else:
                # Nếu không hiển thị hộp thoại, thực hiện hành động mà không cần xác nhận từ người dùng
                last_record = self.records.pop()
                self.remove_record_from_preview(last_record['frame_idx'])
                self.is_force_update = True
                self._update_frame()
                self.update()
                
    # Frame event
    @pyqtSlot()
    def event_frame_mouse_press(self, event):
        if self._check_coor_in_frame(event.x(), event.y()) and not self.is_playing_video:
            try:
                if event.button() == Qt.LeftButton:
                    self.label_frame.pt1 = (event.x(), event.y())
                    self.input_frame_number.setReadOnly(True)
                
            except Exception as e:
                QMessageBox.warning(self, "Error", f"An error occurred")

    @pyqtSlot()
    def event_frame_mouse_move(self, event):
        if self.label_frame.pt1:  # Nếu đã có điểm bắt đầu, tức là đang trong quá trình vẽ box
            frame = self._read_frame(self.target_frame_idx)  # Đọc frame từ video
            if frame is not None:
                pixmap = QPixmap(self._ndarray_to_qimage(frame))  # Chuyển đổi frame thành pixmap
                painter = QPainter(pixmap)
                painter.setPen(QPen(Qt.red, 3))  # Màu và độ dày của box tạm thời
                painter.drawRect(QRect(self.label_frame.pt1[0], self.label_frame.pt1[1], event.x() - self.label_frame.pt1[0], event.y() - self.label_frame.pt1[1]))
                self.label_frame.setPixmap(pixmap)
                painter.end()
                self.update()  # Cập nhật lại label_frame

    @pyqtSlot()
    def event_frame_mouse_release(self, event):
        # Lấy text từ ô Line Edit
        self.notes_text = self.line_edit_notes.text()
        if self.label_frame.pt1:  # Nếu đã có điểm bắt đầu, tức là đang trong quá trình vẽ box
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
                ('object_cls', self.classes_list[self.current_class_index]), ('object_cls', self.classes_list[self.current_class_index]),
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
    def remove_target_record(self):
        selected_row = self.table_preview_records.currentRow()
        if selected_row >= 0:
            frame_idx = int(self.table_preview_records.item(selected_row, 1).text())
            #target_record_idx = (record for record in self.records if record['frame_idx'] == frame_idx)
            pt1_coord = self.table_preview_records.item(selected_row, 5).text()
            pt2_coord = self.table_preview_records.item(selected_row, 6).text()
            target_record = None
            
            if self.records:
                if self.show_message_box_target:
                    for record in self.records:
                        if record['frame_idx'] == frame_idx and (record['x1'], record['y1']) == eval(pt1_coord) and (record['x2'], record['y2']) == eval(pt2_coord):
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
                            self._update_frame()
                            self.update()
                            
                        if dont_ask_again_checkbox.isChecked():
                            self.show_message_box_target = False
                    else:
                        QMessageBox.warning(self, "Error", "Target record not found!")
                else:
                    for record in self.records:
                        if record['frame_idx'] == frame_idx and (record['x1'], record['y1']) == eval(pt1_coord) and (record['x2'], record['y2']) == eval(pt2_coord):
                            target_record = record
                            break
                    if target_record:
                        self.records.remove(target_record)
                        self.table_preview_records.removeRow(selected_row)
                        #target_record = None
                        self.is_force_update = True
                        self._update_frame()
                        self.update()                    
                    
                
    @pyqtSlot()  
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        remove_action = QAction("Remove", self)
        remove_action.triggered.connect(self.event_remove_record)
        menu.addAction(remove_action)
        menu.exec_(event.globalPos())
    
   
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
    
    def toggle_auto_save(self, state):
        # Xử lý sự kiện khi trạng thái của QCheckBox thay đổi
        if state == Qt.Checked:
            self.logger.info("Auto save is enabled")
            self.auto_save_enabled = True
            self.auto_save()
        else:
            self.logger.info("Auto save is disabled")
            self.auto_save_enabled = False
            
    # def disable_auto_save(self, state):
    #     if state == Qt.Checked:
    #         self.logger.info("Auto save is disabled")
    #         self.auto_save_enabled = False
    #         state = Qt.Unchecked

    def auto_save(self):
        if self.checkbox_auto_save.isChecked():
            df_labels = pd.DataFrame().from_records(self.records)
            df_labels.to_csv(self.outpath, index=False)
        
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
            df_labels = pd.DataFrame().from_records(self.records)
            df_labels.to_csv(self.outpath, index=False)

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
            df_labels = pd.DataFrame().from_records(self.records)
            df_labels.to_csv(self.outpath, index=False)

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
        self.label_video_objcls.setText(self.classes_list[self.current_class_index])

    @pyqtSlot()
    def to_increase_object_id(self):
        self.object_id += 1
        self.label_video_objid.setText(str(self.object_id))
        
    def to_decrease_object_id(self):
        if self.object_id > 1:
            self.object_id -= 1
            self.label_video_objid.setText(str(self.object_id))
        
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
                self.records = []
                self.is_force_update = True
                
            # Đặt lại các thông số liên quan đến video
            self.cap = cv2.VideoCapture(self.videopath)
            self.target_frame_idx = 0       # sẵn sàng cập nhật
            self.render_frame_idx = None    # đã render
            self.scale_height = self.scale_width = None
            self.is_playing_video = False
            self.is_force_update = False
            self._update_video_info()
            # if self.auto_save_enabled:
            #     self.disable_auto_save()
            #self._update_frame()

        
    def remove_all_records_from_preview(self):
        """Xoá hết các hàng trong bảng xem trước"""
        while self.table_preview_records.rowCount() > 0:
            self.table_preview_records.removeRow(0)
            
        self._update_frame()
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
            elif event.button() == Qt.RightButton:
                pass
            elif event.key() == Qt.Esc:
                self.close()
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred")
            #print(e)
        # else:
            
        #     super().keyPressEvent(event)
        #     event.ignore()
            # self.logger.debug('clicked %s but no related binding event', str(event.key()))

CONFIG_FILE = str(Path(__file__).resolve().parents[0] / 'config.yaml')
    
# Open video
def get_video_file():
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    file_path = filedialog.askopenfilename(title="Select Video File", filetypes=[("Video files", "*.mp4")])
    return file_path

video_file = get_video_file()
    
def main():
    """an interface to activate pyqt5 app"""
    logger = logging.getLogger(__name__)
    log_handler(logger)
    
    
    with open(CONFIG_FILE, 'r') as config_file:
        config = yaml.safe_load(config_file)
    

       
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