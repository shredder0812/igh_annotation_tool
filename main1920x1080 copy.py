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
from PyQt5.QtCore import Qt, QTimer, pyqtSlot, QRect, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QImage, QPixmap, QCursor
from PyQt5.QtWidgets import (QMenuBar, QFileDialog, QAbstractItemView, QDesktopWidget, QGridLayout,
                             QGroupBox, QHBoxLayout, QLabel,
                             QPushButton, QSlider, QStyle, QTableWidget, QCheckBox,
                             QTableWidgetItem, QVBoxLayout, QWidget,
                             QMessageBox, QWidget, QApplication, QMenu, QAction, QDesktopWidget, QTextEdit)

"""some utility function"""
import logging
import sys
from functools import wraps
from tkinter import filedialog
import tkinter as tk


# Open video

def get_video_file():
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    file_path = filedialog.askopenfilename(title="Select Video File", filetypes=[("Video files", "*.mp4")])
    return file_path

video_file = get_video_file()

if not video_file:
    print("No file selected. Exiting.")
    exit()

# Utils

LOGGER = logging.getLogger(__name__)

def log_handler(*loggers, logname: str = ''):
    """[summary]

    Keyword Arguments:
        logname {str} -- [description] (default: {''})
    """

    formatter = logging.Formatter(
        '%(asctime)s %(filename)12s:L%(lineno)3s [%(levelname)8s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S')

    # stream handler
    shell_handler = logging.StreamHandler(sys.stdout)
    shell_handler.setLevel(logging.INFO)
    shell_handler.setFormatter(formatter)

    # file handler
    if logname:
        file_handler = logging.FileHandler(logname)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)

    for logger in loggers:
        if logname:
            logger.addHandler(file_handler)
        logger.addHandler(shell_handler)
        logger.setLevel(logging.DEBUG)

def func_profile(func):
    """record the function processing time"""
    @wraps(func)
    def wrapped(*args, **kwargs):
        start_time = datetime.now()
        result = func(*args, **kwargs)
        cost_time = datetime.now() - start_time
        fullname = '{}.{}'.format(func.__module__, func.__name__)
        LOGGER.info('%s[kwargs=%s] completed in %s', fullname, kwargs, str(cost_time))
        return result
    return wrapped


class AutoSaveThread(QThread):
    save_completed = pyqtSignal()

    def __init__(self, parent=None):
        super(AutoSaveThread, self).__init__(parent)
        self.auto_save_enabled = True

    def run(self):
        while self.auto_save_enabled:
            # Thực hiện lưu dữ liệu
            self.save_completed.emit()
            self.sleep(1)  # Đợi 5 giây trước khi lưu tiếp

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
                
        # Khởi tạo luồng auto save
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
        self.grid_root.addLayout(vbox_option, 0, 1)
        
        # menu bar
        
                
        self.menu_bar_no = QWidget(self)
        vbox_panels.addWidget(self.menu_bar_no)
        
        self.init_menu_bar()
        # vbox_panel/label_frame: show frame image        
        self.label_frame = VideoFrameViewer(self)
        # self.label_frame.move(0, 22)
        self.label_frame.setAlignment(Qt.AlignTop)
        self.label_frame.setMouseTracking(True)
        vbox_panels.addWidget(self.label_frame)

        # vbox_option/group_video_info: show video static info
        self.menu_bar_noa = QMenuBar(self)
        vbox_option.addWidget(self.menu_bar_noa)
        self.group_video_info = QGroupBox('Video Information')
        sub_grid = QGridLayout()
        label_path = self._get_header_label('Path')
        label_shape = self._get_header_label('Shape')
        label_fps = self._get_header_label('FPS')
        label_objid = self._get_header_label('Object ID (F to increase, D to decrease)')
        label_objcls = self._get_header_label('Object Class (C to switch)')
        
        self.label_video_path = QLabel()
        self.label_video_path.setAlignment(Qt.AlignLeft)
        self.label_video_path.setWordWrap(True)        
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
        sub_grid.addWidget(label_shape, 1, 0)
        sub_grid.addWidget(self.label_video_shape, 1, 1)
        sub_grid.addWidget(label_fps, 2, 0)
        sub_grid.addWidget(self.label_video_fps, 2, 1)
        sub_grid.addWidget(label_objid, 3, 0)
        sub_grid.addWidget(self.label_video_objid, 3, 1)
        sub_grid.addWidget(label_objcls, 4, 0)
        sub_grid.addWidget(self.label_video_objcls, 4, 1)
        
        self.group_video_info.setLayout(sub_grid)
        self.group_video_info.contentsMargins()
        self.group_video_info.setAlignment(Qt.AlignTop)
        vbox_option.addWidget(self.group_video_info)
        
        # self.tree_preview_records = QTreeView()
        # self.tree_preview_records.setRootIsDecorated(False)
        # self.tree_preview_records.setAlternatingRowColors(True)
        # self.model_preview_records = self._get_preview_model(self)
        # self.tree_preview_records.setModel(self.model_preview_records)
        # self.tree_preview_records.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # vbox_option.addWidget(self.tree_preview_records)
       
        # vbox_panel/hbox_video: show process about video
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
        vbox_option.addLayout(hbox_video_slider)

        # vbox_panel/label_video_status: show frame index or exception msg
        self.label_video_status = QLabel()
        self.label_video_status.setAlignment(Qt.AlignCenter)
        vbox_option.addWidget(self.label_video_status)
        
        next_and_back_button = QHBoxLayout()
        hbox_jump_records = QHBoxLayout()
        
        self.btn_to_back_frame = QPushButton('Previous Frame (B)')
        next_and_back_button.addWidget(self.btn_to_back_frame)
        
        self.btn_to_next_frame = QPushButton('Next Frame (N)')
        next_and_back_button.addWidget(self.btn_to_next_frame)
         
        vbox_option.addLayout(next_and_back_button)
        
        self.btn_continue = QPushButton('Continue')
        # self.btn_previous_record = QPushButton('<< Previous Record')
        # self.btn_next_record = QPushButton('Next Record >>')
        hbox_jump_records.addWidget(self.btn_continue)
        # hbox_jump_records.addWidget(self.btn_previous_record)
        # hbox_jump_records.addWidget(self.btn_next_record)
        vbox_option.addLayout(hbox_jump_records)
        self.btn_remove_last_box = QPushButton('Remove Last Box (R)')
        vbox_option.addWidget(self.btn_remove_last_box)
        # Thêm QT Switch Control để bật/tắt auto save
        self.checkbox_auto_save = QCheckBox("Auto Save")
        vbox_option.addWidget(self.checkbox_auto_save)
        # vbox_option/btn_export: export records
        self.btn_export_records = QPushButton('Export')
        vbox_option.addWidget(self.btn_export_records)
        # vbox_option/table_preview_record: preview the summary of records
        self.table_preview_records = self._get_preview_table(self)
        vbox_option.addWidget(self.table_preview_records)

    def _get_header_label(self, text: str = ''):
        label = QLabel(text)
        label.setFont(self.font_header)
        label.setAlignment(Qt.AlignLeft)
        return label
    
    def _get_preview_table(self, parent):
        table = QTableWidget(parent=parent)
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(['Timestamp', 'Frame', 'Class' , 'Object ID' , 'Pt1', 'Pt2'])
        table.setSortingEnabled(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        return table
    
    def add_record_to_preview(self, timestamp: str, frame_idx: int, object_class: str, object_id: int, pt1: tuple, pt2: tuple):
        self.table_preview_records.insertRow(0)
        self.table_preview_records.setItem(0, 0, QTableWidgetItem(timestamp))
        self.table_preview_records.setItem(0, 1, QTableWidgetItem(str(frame_idx)))
        self.table_preview_records.setItem(0, 2, QTableWidgetItem(str(object_class)))
        self.table_preview_records.setItem(0, 3, QTableWidgetItem(str(object_id)))
        self.table_preview_records.setItem(0, 4, QTableWidgetItem(str(pt1)))
        self.table_preview_records.setItem(0, 5, QTableWidgetItem(str(pt2)))
        self.table_preview_records.sortByColumn(0, Qt.DescendingOrder)
    
    def remove_record_from_preview(self, num_rows: int = 1):
            self.table_preview_records.removeRow(0)

# App
class VideoApp(VideoAppViewer):
    def __init__(self, videopath: str, outpath: str, **config):
        self.videopath = videopath
        self.outpath = outpath
        self.config = config
        self.title = self.config.get('title', 'IGH Annotation Tool')
        self.object_id = 1
        self.current_class_index = 0
        self.classes_list = config.get('classes', ['A', 'B', 'C', 'D', 'E'])
        self.object_class = self.classes_list[self.current_class_index]
        super().__init__(title=self.title)
        
        
        
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

        # menubar
        # self.menu_bar.clicked.connect(self.init_menu_bar)
        
        # widget binding
        self.slider_video.setRange(0, self.frame_count-1)
        self.slider_video.sliderMoved.connect(self.on_slider_moved)
        self.slider_video.sliderReleased.connect(self.on_slider_released)
        self.btn_play_video.clicked.connect(self.on_play_video_clicked)
        self.btn_to_back_frame.clicked.connect(self.to_back_frame)
        self.btn_to_next_frame.clicked.connect(self.to_next_frame)
        self.btn_continue.clicked.connect(self.continue_function)

        self.label_frame.mousePressEvent = self.event_frame_mouse_press
        self.label_frame.mouseMoveEvent = self.event_frame_mouse_move
        self.label_frame.mouseReleaseEvent = self.event_frame_mouse_release
        # self.btn_previous_record.clicked.connect(self._goto_previous_record)
        # self.btn_next_record.clicked.connect(self._goto_next_record)
        self.btn_export_records.clicked.connect(self.save_file)
        self.btn_remove_last_box.clicked.connect(self.remove_last_box)
        self.table_preview_records.doubleClicked.connect(self.event_preview_double_clicked)
        self.checkbox_auto_save.stateChanged.connect(self.toggle_auto_save)
        # self.table_preview_records.doubleClicked.connect(self.event_preview_double_clicked)
        # self.table_preview_records.itemDoubleClicked.clicked.connect(self.event_remove_record)
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
        ok_button.clicked.connect(lambda: self.update_classes(text_edit.toPlainText()))
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
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Video File", "", "Video Files (*.mp4)", options=options)
        if file_path:
            
            # Xử lý tệp video được chọn
            self.videopath = file_path
            self._update_video_info()
            self.cap = cv2.VideoCapture(self.videopath)
            self.target_frame_idx = 0
            self.render_frame_idx = None
            self.scale_height = self.scale_width = None
            self.is_playing_video = False
            self.is_force_update = False
            self._update_frame()

    def import_csv_file(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(self, "Import CSV File", "", "CSV Files (*.csv)", options=options)
        if file_path:
            self.read_csv_file(file_path)
            
    def read_csv_file(self, file_path):
        try:
            df = pd.read_csv(file_path)
            # Xử lý dữ liệu đọc được từ file CSV và cập nhật vào danh sách self.records
            self.records = []  # Đảm bảo rằng danh sách self.records trống trước khi cập nhật dữ liệu mới
            #self.csv_records_set = set()  # Set lưu trữ các bản ghi từ file CSV
            new_records = []
            for index, row in df.iterrows():
                record = OrderedDict([
                        ('timestamp_hms', row['timestamp_hms']),
                        ('timestamp_hmsf', row['timestamp_hmsf']),
                        ('frame_idx', row['frame_idx']), ('fps', row['fps']),
                        ('object_cls', row['object_cls']), ('object_cls', row['object_cls']),
                        ('object_idx', row['object_idx']), ('object_id', row['object_id']),
                        ('frame_height', row['frame_height']), ('frame_width', row['frame_width']),
                        ('scale_height', row['scale_height']), ('scale_width', row['scale_width']),
                        ('x1', row['x1']), ('y1', row['y1']), ('x2', row['x2']), ('y2', row['y2']),
                        ('center_x', row['center_x']), ('center_y', row['center_y'])])
                if not self._is_duplicate(record):
                    new_records.append(record)
                self.records.extend(new_records)  # Thêm các bản ghi mới vào danh sách tồn tại
                self._update_records() 
                #self.records.append(record)
                    #self.records = new_records
                    #self.records = sorted(self.records, key=lambda x: x['frame_idx'])
                self.add_record_to_preview(record['timestamp_hms'], \
                                                record['frame_idx'], \
                                                record['object_cls'], \
                                                record['object_id'], \
                                                (record['x1'], record['y1']), \
                                                (record['x2'], record['y2']))
                self.is_force_update = True
                self.update()  # Cập nhật giao diện để hiển thị box cuối cùng
                
            
            # Hiển thị thông tin về số lượng bản ghi đã được import
            QMessageBox.about(self, 'Info', 'Imported {} records from CSV file.'.format(len(self.records)))
            self.redraw_boxes_on_frame()
            self.render_frame_idx = max(record['frame_idx'] for record in self.records)
        except Exception as e:
            QMessageBox.critical(self, 'Error', 'Error occurred while importing CSV file: {}'.format(str(e)))

    
    def _is_duplicate(self, new_record):
        # Kiểm tra xem bản ghi mới có trùng lặp với các bản ghi đã tồn tại không
        for record in self.records:
            if record == new_record:
                return True
        return False

    def _update_records(self):
        # Tạo một set để theo dõi các bản ghi đã xuất hiện
        seen = set()
        unique_records = []
        for record in self.records:
            # Chuyển đổi dictionary record thành một tuple để có thể kiểm tra xem nó đã tồn tại trong set chưa
            record_tuple = tuple(record.items())
            if record_tuple not in seen:
                # Nếu bản ghi không trùng lặp, thêm nó vào danh sách unique_records và set seen
                unique_records.append(record)
                seen.add(record_tuple)
        self.records = unique_records
    
    def redraw_boxes_on_frame(self):
    # Lấy frame hiện tại
        frame = self._read_frame(self.render_frame_idx)
        if frame is not None:
            # Xóa các box cũ trên frame
            #frame = self._clear_old_boxes()
            # Lọc các bản ghi từ self.records để chỉ lấy các bản ghi có frame_idx tương ứng với render_frame_idx
            filtered_records = [record for record in self.records if record['frame_idx'] == self.render_frame_idx]
            # Vẽ lại các box từ danh sách filtered_records lên frame
            for record in filtered_records:
                pt1 = (record['x1'], record['y1'])
                pt2 = (record['x2'], record['y2'])
                class_label = record['object_cls']
                # Vẽ box lên frame
                cv2.rectangle(frame, pt1, pt2, self.label_color, self.label_thickness)
                # Hiển thị thông tin về box lên frame
                text = f"{class_label} | ID: {record['object_id']} | {pt1}, {pt2}"
                cv2.putText(frame, text, (pt1[0], pt1[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 1, cv2.LINE_AA)
            
            # Hiển thị frame đã vẽ box lên label_frame
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
        self.label_video_shape.setText(shape)
        self.label_video_fps.setText(str(self.video_fps))

    def _update_frame(self):
        """read and update image to label"""
        if self.target_frame_idx != self.render_frame_idx or self.is_force_update:
            self.is_force_update = False
            
            frame = self._read_frame(self.target_frame_idx)
            if frame is not None:
                
                #  # draw, convert, resize pixmap
                # frame = self.draw_rects(self.target_frame_idx, frame)
                # pixmap = QPixmap(self._ndarray_to_qimage(frame))
                # # Scale the pixmap to fit the screen while maintaining aspect ratio
                # self.scale_width=1280
                # self.scale_height = int(pixmap.height() * (self.scale_width / pixmap.width()))
                
                # pixmap = pixmap.scaledToWidth(self.scale_width)
                
                # self.label_frame.setPixmap(pixmap)
                # self.label_frame.resize(self.scale_width, self.scale_height)

                

                
                
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
        """update frame status
        Arguments:
            frame_idx {int} -- frame index

        Keyword Arguments:
            err {str} -- show status when exception (default: '')
        """
        msg = '#frame ({}/{})'.format(frame_idx, self.frame_count-1)
        if err:
            msg += '\n{}'.format(err)
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
        """get the closest record by given coor in current frame
        Arguments:
            coor_x {int} -- cooridinate x
            coor_y {int} -- cooridinate

        Returns:
            {OrderedDict} -- the closest record
        """
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
        """remove record by given value
        Arguments:
            frame_idx {int} -- record frame index
            pt1 {tuple} -- record (x1, y1)
            pt2 {tuple} -- record (x2, y2)
        """
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
    def continue_function(self):
        """control to play or pause the video"""
        # self.is_playing_video = not self.is_playing_video
        if self.is_playing_video:
            #self.btn_continue.setIcon(self.style().standardIcon(QStyle.SP_ArrowRight))
            self.target_frame_idx = min(self.target_frame_idx+1, self.frame_count-1)
        #else:
            #self.btn_continue.setIcon(self.style().standardIcon(QStyle.SP_DialogYesButton))

    @pyqtSlot()
    def remove_last_box(self):
        if self.records:
            last_record = self.records.pop()  # Xoá box mới nhất từ danh sách các box
            self.remove_record_from_preview(last_record['frame_idx'])
            self.is_force_update = True
            self._update_frame()
            self.update()
            
    # @pyqtSlot()
    # def _clear_old_boxes(self):
    #     if self.records:
    #         all_record = self.records.clear()
    #         self.remove_record_from_preview(all_record['frame_idx'])
    #         self.is_force_update = True
    #         self._update_frame()
    #         self.update()
            
            
        
    # Frame event
    @pyqtSlot()
    def event_frame_mouse_press(self, event):
        """label frame press mouse event
        - Qt.LeftButton: drawing
        - Qt.RightButton: select to delete
        Arguments:
            event {PyQt5.QtGui.QMouseEvent} -- event object
        """
        frame = self._read_frame(self.target_frame_idx)  # Đọc frame từ video
        if frame is not None:
            pixmap = QPixmap(self._ndarray_to_qimage(frame)) 
            self.label_frame.setPixmap(pixmap)
            
            if self._check_coor_in_frame(event.x(), event.y()) and not self.is_playing_video:
                if event.button() == Qt.LeftButton:
                    self.label_frame.pt1 = (event.x(), event.y())
            #if event.button() == Qt.RightButton:
                # Handle right button press
                
                # frame = self._read_frame(self.target_frame_idx)  # Đọc frame từ video
                # if frame is not None:
                #     pixmap = QPixmap(self._ndarray_to_qimage(frame)) 
                #     self.label_frame.setPixmap(pixmap)
                    
                #     if event.button() == Qt.LeftButton:
                #         self.label_frame.pt1 = (event.x(), event.y())
           

    @pyqtSlot()
    def event_frame_mouse_move(self, event):
        if self.label_frame.pt1:  # Nếu đã có điểm bắt đầu, tức là đang trong quá trình vẽ box
            frame = self._read_frame(self.target_frame_idx)  # Đọc frame từ video
            if frame is not None:
                pixmap = QPixmap(self._ndarray_to_qimage(frame))  # Chuyển đổi frame thành pixmap
                # # Scale the pixmap to fit the screen while maintaining aspect ratio
                # scale_width = 1280
                # scale_height = 720
                # pixmap = pixmap.scaled(scale_width, scale_height, Qt.KeepAspectRatio)
                painter = QPainter(pixmap)
                painter.setPen(QPen(Qt.red, 3))  # Màu và độ dày của box tạm thời
                painter.drawRect(QRect(self.label_frame.pt1[0], self.label_frame.pt1[1], event.x() - self.label_frame.pt1[0], event.y() - self.label_frame.pt1[1]))
                self.label_frame.setPixmap(pixmap)
                painter.end()
                self.update()  # Cập nhật lại label_frame

    @pyqtSlot()
    def event_frame_mouse_release(self, event):
        if self.label_frame.pt1:  # Nếu đã có điểm bắt đầu, tức là đang trong quá trình vẽ box
            pt1 = self.label_frame.pt1
            pt2 = (event.x(), event.y())  # Sử dụng vị trí thứ hai khi thả chuột làm điểm kết thúc của box
            # Kiểm tra xem có phải là click đơn (pt1 và pt2 giống nhau) không
            if pt1 == pt2:
                self.label_frame.pt1 = None  # Xóa điểm bắt đầu
                # frame = self._read_frame(self.target_frame_idx)  # Đọc frame từ video
                # if frame is not None:
                #     pixmap = QPixmap(self._ndarray_to_qimage(frame)) 
                #     self.label_frame.setPixmap(pixmap)
                return
            # Tạo record từ hai điểm này
            record = OrderedDict([
                ('timestamp_hms', self._frame_idx_to_hms(self.render_frame_idx)),
                ('timestamp_hmsf', self._frame_idx_to_hmsf(self.render_frame_idx)),
                ('frame_idx', self.render_frame_idx), ('fps', self.video_fps),
                ('object_cls', self.classes_list[self.current_class_index]), ('object_cls', self.classes_list[self.current_class_index]),
                ('object_idx', self.object_id), ('object_id', self.object_id),
                ('frame_height', self.frame_height), ('frame_width', self.frame_width),
                ('scale_height', self.scale_height), ('scale_width', self.scale_width),
                ('x1', pt1[0]), ('y1', pt1[1]), ('x2', pt2[0]), ('y2', pt2[1]),
                ('center_x', (pt1[0]+pt2[0])//2), ('center_y', (pt1[1]+pt2[1])//2)
            ])
            self.records.append(record)
            self.records = sorted(self.records, key=lambda x: x['frame_idx'])
            self.add_record_to_preview(record['timestamp_hms'], \
                                        record['frame_idx'], \
                                        record['object_cls'], \
                                        record['object_id'], \
                                        (record['x1'], record['y1']), \
                                        (record['x2'], record['y2']))
            self.label_frame.pt1 = self.label_frame.pt2 = None
            self.is_force_update = True
            self.update()  # Cập nhật giao diện để hiển thị box cuối cùng

        # Làm sạch điểm bắt đầu khi thả chuột
        self.label_frame.pt1 = None



    @pyqtSlot()
    def event_preview_double_clicked(self):
        row = self.table_preview_records.currentRow()
        frame_idx = int(self.table_preview_records.item(row, 1).text())
        # pt1 pt2, tra điểm có toạ độ pt1 
        self.target_frame_idx = frame_idx
    
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

    

    # def save_file(self):
    #     """export records to default paths
    #     - click ok only close message box
    #     - click close to close PyQt program
    #     """
    #     exist_msg = 'File <b>{}</b> exist.<br/><br/>\
    #                      Do you want to replace?'.format(self.outpath)
    #     info_msg = 'Save at <b>{}</b><br/>\
    #                 Total records: {}'.format(self.outpath, len(self.records))

    #     # check the file existense
    #     exist_reply = QMessageBox.No
    #     if Path(self.outpath).exists():
    #         exist_reply = QMessageBox.question(self, 'File Exist', exist_msg, \
    #                                            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
    #     if not Path(self.outpath).exists() or exist_reply == QMessageBox.Yes:
    #         df_labels = pd.DataFrame().from_records(self.records)
    #         df_labels.to_csv(self.outpath, index=False)

    #     # check if the application is going to close
    #     reply = QMessageBox.about(self, 'Info', info_msg)
    #     # self.close()     
    
    def toggle_auto_save(self, state):
        # Xử lý sự kiện khi trạng thái của QCheckBox thay đổi
        if state == Qt.Checked:
            self.logger.info("Auto save is enabled")
            self.auto_save()
        else:
            self.logger.info("Auto save is disabled")

    def auto_save(self):
        """Auto save records to default paths after each record is drawn"""
        
        
        if self.checkbox_auto_save.isChecked():
            df_labels = pd.DataFrame().from_records(self.records)
            df_labels.to_csv(self.outpath, index=False)
    
        #reply = QMessageBox.about(self, 'Info', info_msg)
        
    def closeEvent(self, event):
        """Xử lý sự kiện khi cửa sổ đóng"""
        self.auto_save_thread.stop()
        self.auto_save_thread.wait()  # Chờ luồng auto save kết thúc trước khi đóng cửa sổ
        event.accept()
     
    def save_file(self):
        """export records to default paths
        - click ok only close message box
        - click close to close PyQt program
        """
        exist_msg = 'File <b>{}</b> exist.<br/><br/>\
                         Do you want to replace?'.format(self.outpath)
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
        
        
    
    def keyPressEvent(self, event):
        """global keyboard event"""
        if event.key() in [Qt.Key_Space, Qt.Key_P]:
            self.on_play_video_clicked()
        elif event.key() in [Qt.Key_Right, Qt.Key_N]:
            # self.target_frame_idx = min(self.target_frame_idx+1, self.frame_count-1)
            self.to_next_frame()
        elif event.key() in [Qt.Key_Left, Qt.Key_B]:
            # self.target_frame_idx = max(0, self.target_frame_idx-1)
            self.to_back_frame()
        elif event.key() == Qt.Key_F:
            self.object_id += 1
            self.label_video_objid.setText(str(self.object_id))
        elif event.key() == Qt.Key_D:
            if self.object_id > 1:
                self.object_id -= 1
                self.label_video_objid.setText(str(self.object_id))
        elif event.key() == Qt.Key_C:
            self.current_class_index = (self.current_class_index + 1) % len(self.classes_list)
            self.label_video_objcls.setText(self.classes_list[self.current_class_index])
        elif event.key() == Qt.Esc:
            self.close()
        elif event.key() == Qt.Key_R:
            self.remove_last_box()
        else:
            event.ignore()
            # self.logger.debug('clicked %s but no related binding event', str(event.key()))



CONFIG_FILE = str(Path(__file__).resolve().parents[0] / 'config.yaml')

def argparser():
    """parse arguments from terminal"""
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--video', dest='video', default=video_file, type=str)
    parser.add_argument('-c', '--config', dest='config', default=CONFIG_FILE)
    parser.add_argument('-o', '--output', dest='output')
    return parser

@func_profile
def main(args: argparse.Namespace):
    """an interface to activate pyqt5 app"""
    logger = logging.getLogger(__name__)
    log_handler(logger)
    logger.info(args)
    with open(args.config, 'r') as config_file:
        config = yaml.safe_load(config_file)

    video_path = Path(args.video)
    output_path = Path('outputs')
    if not output_path.exists():
        output_path.mkdir(parents=True)
    label_path = output_path / '{}_label.csv'.format(video_path.stem)
    label_path = output_path / str(Path(args.output)) if args.output else label_path
    if not label_path.parent.exists():
        label_path.parent.mkdir(parents=True)

    app = QApplication(sys.argv)
    video_app = VideoApp(args.video, str(label_path), **config)
    # try:
    #     log_handler(video_app.logger)
    #     app.exec()
    # except Exception as e:
    #     logger.exception(e)
    
    log_handler(video_app.logger)
    app.exec()
    
        
    

if __name__ == '__main__':
    main(argparser().parse_args())
