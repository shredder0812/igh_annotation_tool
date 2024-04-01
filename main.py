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
from time import sleep
import logging
from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QImage, QPixmap
from PyQt5.QtWidgets import (QAbstractItemView, QDesktopWidget, QGridLayout,
                             QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                             QPushButton, QSlider, QStyle, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget, 
                             QMessageBox, QWidget, QApplication, QFileDialog)

"""some utility function"""
import logging
import sys
from datetime import datetime
from functools import wraps
import os
from tkinter import filedialog
import tkinter as tk


# open video
def get_video_file():
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    file_path = filedialog.askopenfilename(title="Select Video File", filetypes=[("Video files", "*.mp4")])
    return file_path

video_file = get_video_file()

# Check if a file is selected
if not video_file:
    print("No file selected. Exiting.")
    exit()

#utlis


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


#view

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
        """init

        Arguments:
            QWidget {[type]} -- default qt widget

        Keyword Arguments:
            title {str} -- window title (default: {'IGH Annotation Tool'})
        """

        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.title = title
        self.desktop = QDesktopWidget()
        self.screen = self.desktop.availableGeometry()
        self.font_header = QFont()
        self.font_header.setBold(True)

        # init window - init and set default config about window
        self.setWindowTitle(self.title)

        # grid: root layout
        self.grid_root = QGridLayout()
        self.setLayout(self.grid_root)
        vbox_panels = QVBoxLayout()
        vbox_option = QVBoxLayout()
        self.grid_root.addLayout(vbox_panels, 0, 0)
        self.grid_root.addLayout(vbox_option, 0, 1)

        # vbox_panel/label_frame: show frame image
        self.label_frame = VideoFrameViewer(self)
        self.label_frame.setAlignment(Qt.AlignCenter)
        self.label_frame.setMouseTracking(True)
        vbox_panels.addWidget(self.label_frame)

        # vbox_panel/hbox_video: show process about video
        hbox_video_slider = QHBoxLayout()
        self.btn_play_video = QPushButton()
        self.btn_play_video.setEnabled(True)
        self.btn_play_video.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.slider_video = QSlider(Qt.Horizontal)
        self.slider_video.setRange(0, 0)
        hbox_video_slider.addWidget(self.btn_play_video)
        hbox_video_slider.addWidget(self.slider_video)
        vbox_panels.addLayout(hbox_video_slider)

        # vbox_panel/label_video_status: show frame index or exception msg
        self.label_video_status = QLabel()
        self.label_video_status.setAlignment(Qt.AlignCenter)
        vbox_panels.addWidget(self.label_video_status)

        # vbox_option/group_video_info: show video static info
        self.group_video_info = QGroupBox('Video Information')
        sub_grid = QGridLayout()
        label_path = self._get_header_label('Path')
        label_shape = self._get_header_label('Shape')
        label_fps = self._get_header_label('FPS')
        label_objid = self._get_header_label('Object ID')
        label_objcls = self._get_header_label('Object Class')
        label_bbox = self._get_header_label('Boxes')
        
        
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
        sub_grid.addWidget(label_bbox, 5, 0)
        sub_grid.addWidget(self.label_video_bbox, 5, 1)
        
        
        self.group_video_info.setLayout(sub_grid)
        self.group_video_info.contentsMargins()
        self.group_video_info.setAlignment(Qt.AlignTop)
        vbox_option.addWidget(self.group_video_info)

        # vbox_option/table_preview_record: preview the summary of records
        self.table_preview_records = self._get_preview_table(self)
        vbox_option.addWidget(self.table_preview_records)

        # self.tree_preview_records = QTreeView()
        # self.tree_preview_records.setRootIsDecorated(False)
        # self.tree_preview_records.setAlternatingRowColors(True)
        # self.model_preview_records = self._get_preview_model(self)
        # self.tree_preview_records.setModel(self.model_preview_records)
        # self.tree_preview_records.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # vbox_option.addWidget(self.tree_preview_records)

        # vbox_option/hbox_jump_records: jump to next or previous record
        hbox_jump_records = QHBoxLayout()
        self.btn_previous_record = QPushButton('<< Previous Record')
        self.btn_next_record = QPushButton('Next Record >>')
        hbox_jump_records.addWidget(self.btn_previous_record)
        hbox_jump_records.addWidget(self.btn_next_record)
        vbox_option.addLayout(hbox_jump_records)

        # vbox_option/btn_export: export records
        self.btn_export_records = QPushButton('Export')
        vbox_option.addWidget(self.btn_export_records)

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
        self.table_preview_records.sortByColumn(0, Qt.AscendingOrder)
    
    def remove_record_from_preview(self, row_idx: int):
        self.table_preview_records.removeRow(row_idx)


global click_list
global positions
positions, click_list = [], []

class VideoApp(VideoAppViewer):
    def __init__(self, videopath: str, outpath: str, **config):
        self.videopath = videopath
        self.outpath = outpath
        self.config = config
        self.title = self.config.get('title', 'IGH Annotation Tool')
        self.object_id = 1
        self.current_class_index = 0
        #self.classes_list = ['A', 'B', 'C', 'D', 'E']
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

        # widget binding
        self.slider_video.setRange(0, self.frame_count-1)
        self.slider_video.sliderMoved.connect(self.on_slider_moved)
        self.slider_video.sliderReleased.connect(self.on_slider_released)
        self.btn_play_video.clicked.connect(self.on_play_video_clicked)
        self.label_frame.mousePressEvent = self.event_frame_mouse_press
        self.label_frame.mouseMoveEvent = self.event_frame_mouse_move
        self.label_frame.mouseReleaseEvent = self.event_frame_mouse_release
        self.btn_previous_record.clicked.connect(self._goto_previous_record)
        self.btn_next_record.clicked.connect(self._goto_next_record)
        self.btn_export_records.clicked.connect(self.save_file)
        self.table_preview_records.doubleClicked.connect(self.event_preview_double_clicked)
        self.show()

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
                # draw, convert, resize pixmap
                frame = self.draw_rects(self.target_frame_idx, frame)
                pixmap = QPixmap(self._ndarray_to_qimage(frame))
                self.scale_width = int(min(pixmap.width(), self.screen.width()*0.8))
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
    def event_frame_mouse_press(self, event):
        """label frame press mouse event
        - Qt.LeftButton: drawing
        - Qt.RightButton: select to delete
        Arguments:
            event {PyQt5.QtGui.QMouseEvent} -- event object
        """
        if self._check_coor_in_frame(event.x(), event.y()) and not self.is_playing_video:
            if event.button() == Qt.LeftButton:
                nrecords = self._get_nrecord_in_current_frame()
                if self.limit_nlabel is not None and nrecords and int(self.limit_nlabel) <= nrecords:

                    self.logger.warning('not available to add a new record (exist=%d, limit=%d)', \
                                        nrecords, self.limit_nlabel)
                else:
                    self.label_frame.is_drawing = True
                    self.label_frame.is_selecting = False
                    self.logger.debug('press mouse at (%d, %d)', event.x(), event.y())
                    self.label_frame.pt1 = (event.x(), event.y())
            elif event.button() == Qt.RightButton:
                closest_record = self._get_closest_record_in_current_frame(event.x(), event.y())
                if closest_record:
                    pt1 = (closest_record['x1'], closest_record['y1'])
                    pt2 = (closest_record['x2'], closest_record['y2'])
                    message = '<b>Do you want to delete the record ?</b><br/><br/> \
                    frame index -\t{} <br/> position -\t{} {}'.format(
                        closest_record['frame_idx'], str(pt1), str(pt2))
                    reply = QMessageBox.question(self, 'Delete Record', message, \
                                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                    if reply == QMessageBox.Yes:
                        self._remove_record(closest_record['frame_idx'], pt1, pt2)
                        self.is_force_update = True
                        self.update()

    @pyqtSlot()
    def event_frame_mouse_move(self, event):
        if self.label_frame.is_drawing and self._check_coor_in_frame(event.x(), event.y()):
            self.logger.debug('move mouse at (%d, %d)', event.x(), event.y())
            self.label_frame.pt2 = (event.x(), event.y())
            self.update()
        elif not self.label_frame.is_drawing and not self.is_playing_video:
            closest_record = self._get_closest_record_in_current_frame(event.x(), event.y())
            if closest_record:
                self.label_frame.is_selecting = True
                self.label_frame.select_pt1 = (closest_record['x1'], closest_record['y1'])
                self.label_frame.select_pt2 = (closest_record['x2'], closest_record['y2'])
            else:
                self.label_frame.is_selecting = False
                self.label_frame.select_pt1 = self.label_frame.select_pt2 = None
            self.update()

    @pyqtSlot()
    def event_frame_mouse_release(self, event):
        if self.label_frame.is_drawing:
            self.label_frame.is_drawing = False
            self.logger.debug('release mouse at (%d, %d)', event.x(), event.y())
            if self._check_coor_in_frame(event.x(), event.y()):
                self.label_frame.pt2 = (event.x(), event.y())
            pt1, pt2 = self.label_frame.revise_coor(self.label_frame.pt1, self.label_frame.pt2)
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
            self.update()
    
    

    @pyqtSlot()
    def event_preview_double_clicked(self):
        row = self.table_preview_records.currentRow()
        frame_idx = int(self.table_preview_records.item(row, 1).text())
        self.target_frame_idx = frame_idx

    def draw_rects(self, frame_idx: int, frame: np.ndarray):
        rest_records = list(filter(lambda x: x['frame_idx'] == frame_idx, self.records))
        if not rest_records:
            return frame
        for record in rest_records:
            pt1, pt2 = (record['x1'], record['y1']), (record['x2'], record['y2'])
            cv2.rectangle(frame, pt1, pt2, self.label_color, self.label_thickness)
        return frame

    

    def save_file(self):
        """export records to default paths
        - click ok only close message box
        - click close to close PyQt program
        """
        exist_msg = 'File <b>{}</b> exist.<br/><br/>\
                         Do you want to replace?'.format(self.outpath)
        info_msg = 'Save at <b>{}</b><br/>\
                    total records: {}'.format(self.outpath, len(self.records))

        # check the file existense
        exist_reply = QMessageBox.No
        if Path(self.outpath).exists():
            exist_reply = QMessageBox.question(self, 'File Exist', exist_msg, \
                                               QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if not Path(self.outpath).exists() or exist_reply == QMessageBox.Yes:
            df_labels = pd.DataFrame().from_records(self.records)
            df_labels.to_csv(self.outpath, index=False)

        # check if the application is going to close
        reply = QMessageBox.about(self, 'Info', info_msg)
        self.close()
    
    def keyPressEvent(self, event):
        """global keyboard event"""
        if event.key() in [Qt.Key_Space, Qt.Key_P]:
            self.on_play_video_clicked()
        elif event.key() in [Qt.Key_Right, Qt.Key_N]:
            self.target_frame_idx = min(self.target_frame_idx+1, self.frame_count-1)
        elif event.key() in [Qt.Key_Left, Qt.Key_B]:
            self.target_frame_idx = max(0, self.target_frame_idx-1)
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
        else:
            self.logger.debug('clicked %s but no related binding event', str(event.key()))



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
    try:
        log_handler(video_app.logger)
        app.exec()
    except Exception as e:
        logger.exception(e)
    
    

if __name__ == '__main__':
    main(argparser().parse_args())
