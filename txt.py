
    
    # Frame event
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
                self.label_frame.pt1 = (event.x(), event.y())  # Lưu điểm bắt đầu khi nhấn chuột
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
        if self.label_frame.pt1:  # Nếu đã có điểm bắt đầu, tức là đang trong quá trình vẽ box
            self.label_frame.pt2 = (event.x(), event.y())  # Lưu điểm thứ hai khi di chuyển chuột
            self.update()  # Cập nhật giao diện để hiển thị box tạm thời

    @pyqtSlot()
    def event_frame_mouse_release(self, event):
        if self.label_frame.pt1:  # Nếu đã có điểm bắt đầu, tức là đang trong quá trình vẽ box
            pt1 = self.label_frame.pt1
            pt2 = (event.x(), event.y())  # Sử dụng vị trí thứ hai khi thả chuột làm điểm kết thúc của box
            # Kiểm tra xem có phải là click đơn (pt1 và pt2 giống nhau) không
            if pt1 == pt2:
                self.label_frame.pt1 = None  # Xóa điểm bắt đầu
                return  # Không làm gì nếu là click đơn
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


   