# -*- coding: utf-8 -*-

import sys
import os
import math

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QFrame, QLabel, QPushButton, QLineEdit, QComboBox,
    QTableWidgetItem, QHeaderView, QStackedWidget, QMessageBox,
    QAbstractItemView, QButtonGroup, QDialog, QSizePolicy, QFileDialog,
    QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, QSize, QDate, QObject, QThread, QTimer, Signal
from PySide6.QtGui import QFont, QIcon, QPixmap, QColor

# Import các file module cục bộ
import database
import app_styles
import dialogs
import updater
from app_version import APP_VERSION
from dialogs import CopyableTableWidget

# Thiết lập matplotlib tương thích với PyQt/PySide
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib
matplotlib.use('QtAgg')


class UpdateWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(int)

    def __init__(self, action, payload=None):
        super().__init__()
        self.action = action
        self.payload = payload

    def run(self):
        try:
            if self.action == "check":
                result = updater.check_for_update()
            else:
                result = updater.download_update(self.payload, self.progress.emit)
            self.finished.emit(result)
        except Exception as exc:
            updater.log_exception("Update worker FAILED", exc)
            self.failed.emit(str(exc))


def resource_path(relative_path):
    """Resolve assets both from source and from a PyInstaller bundle."""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def highlight_expired_status(item):
    """Làm nổi bật ô trạng thái hết hạn theo theme."""
    if item is None:
        return
    from app_styles import ThemeManager
    theme = ThemeManager.get_active_theme()
    item.setBackground(QColor(theme.BADGE_EXPIRED))
    item.setForeground(QColor(theme.ERROR))
    font = item.font()
    font.setBold(True)
    item.setFont(font)


class ThemeOptionCard(QFrame):
    clicked = Signal(str)
    
    def __init__(self, theme_id, name, description, preview_colors, parent=None):
        super().__init__(parent)
        self.theme_id = theme_id
        self.setObjectName("ThemeOptionCard")
        self.setProperty("class", "ThemeOptionCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        
        header_layout = QHBoxLayout()
        self.lbl_name = QLabel(name)
        self.lbl_name.setStyleSheet("font-weight: bold; font-size: 15px; color: inherit; background: transparent; border: none;")
        
        self.lbl_indicator = QLabel("○")
        self.lbl_indicator.setStyleSheet("font-size: 16px; font-weight: bold; color: inherit; background: transparent; border: none;")
        
        header_layout.addWidget(self.lbl_name)
        header_layout.addStretch()
        header_layout.addWidget(self.lbl_indicator)
        layout.addLayout(header_layout)
        
        self.lbl_desc = QLabel(description)
        self.lbl_desc.setStyleSheet("font-size: 12px; color: inherit; background: transparent; border: none;")
        self.lbl_desc.setWordWrap(True)
        layout.addWidget(self.lbl_desc)
        
        # Color Preview Dots
        preview_layout = QHBoxLayout()
        preview_layout.setSpacing(6)
        for color in preview_colors:
            dot = QFrame()
            dot.setFixedSize(16, 16)
            dot.setStyleSheet(f"background-color: {color}; border-radius: 8px; border: 1px solid #7F8C8D;")
            preview_layout.addWidget(dot)
        preview_layout.addStretch()
        layout.addLayout(preview_layout)
        
        self.selected = False
        
    def set_selected(self, selected):
        self.selected = selected
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        
        if selected:
            self.lbl_indicator.setText("●")
            self.lbl_indicator.setStyleSheet("font-size: 16px; font-weight: bold; color: #2ecc71; background: transparent; border: none;")
        else:
            self.lbl_indicator.setText("○")
            self.lbl_indicator.setStyleSheet("font-size: 16px; font-weight: bold; color: inherit; background: transparent; border: none;")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.theme_id)
        super().mousePressEvent(event)


class MplCanvas(FigureCanvas):
    """Lớp Canvas của Matplotlib tích hợp vào giao diện Qt."""
    def __init__(self, parent=None, width=6, height=4, dpi=100):
        # Tạo Figure với nền khớp tông màu tối Dark Mode của ứng dụng (#141414)
        fig = Figure(figsize=(width, height), dpi=dpi, facecolor='#0C1724')
        self.axes = fig.add_subplot(111, facecolor='#0D1926')
        super().__init__(fig)
        self.setParent(parent)
        
        # Trục tung bên phải (twinx) cho số lượng đơn hàng
        self.axes_twin = self.axes.twinx()
        self.axes_twin.set_facecolor('none') # Không đè nền xám của trục chính
        
        # Định cấu hình sơ bộ trục tọa độ để hiển thị chữ sáng màu trên nền tối
        self.style_axes()
        self.tooltip = None
        self._hover_cid = self.mpl_connect('motion_notify_event', self._on_hover)
        self.chart_days = []
        self.chart_revenue = []
        self.chart_orders = []
        self.chart_month = ""

    def set_hover_data(self, days, revenue, orders, month_name):
        """Lưu dữ liệu dùng cho tooltip và tạo hộp tooltip trên trục chính."""
        from app_styles import ThemeManager
        theme = ThemeManager.get_active_theme()
        
        self.chart_days = list(days)
        self.chart_revenue = list(revenue)
        self.chart_orders = list(orders)
        self.chart_month = month_name
        self.tooltip = self.axes.annotate(
            "", xy=(0, 0), xytext=(14, 14), textcoords="offset points",
            color=theme.TEXT_PRIMARY, fontsize=9, linespacing=1.55,
            bbox=dict(boxstyle="round,pad=0.7", fc=theme.INPUT_BACKGROUND, ec=theme.BORDER, alpha=0.97),
            arrowprops=dict(arrowstyle="->", color=theme.BORDER),
            annotation_clip=False, zorder=20
        )
        self.tooltip.set_visible(False)

    def _on_hover(self, event):
        """Hiện tooltip của ngày gần con trỏ; tự đổi hướng ở các mép biểu đồ."""
        if event.inaxes not in (self.axes, self.axes_twin) or event.xdata is None or not self.chart_days:
            if self.tooltip is not None and self.tooltip.get_visible():
                self.tooltip.set_visible(False)
                self.draw_idle()
            return

        day = min(self.chart_days, key=lambda value: abs(value - event.xdata))
        # Chỉ kích hoạt khi con trỏ nằm gần một ngày, tránh tooltip bật khắp vùng vẽ.
        if abs(day - event.xdata) > 0.35:
            if self.tooltip is not None and self.tooltip.get_visible():
                self.tooltip.set_visible(False)
                self.draw_idle()
            return

        index = self.chart_days.index(day)
        revenue = self.chart_revenue[index]
        orders = self.chart_orders[index]
        month, year = self.chart_month.split('/')
        self.tooltip.xy = (day, revenue)
        x_offset = -170 if day > self.chart_days[-1] * 0.72 else 14
        ymax = self.axes.get_ylim()[1]
        y_offset = -82 if ymax and revenue > ymax * 0.76 else 14
        self.tooltip.set_position((x_offset, y_offset))
        self.tooltip.set_text(
            f"{day:02d}/{month}/{year}\n"
            f"●  Doanh thu: {revenue:,.0f}đ\n"
            f"●  Số đơn hàng: {orders} đơn"
        )
        self.tooltip.set_visible(True)
        self.draw_idle()

    def style_axes(self):
        """Cấu hình màu sắc của trục tọa độ khớp với theme hiện tại."""
        from app_styles import ThemeManager
        theme = ThemeManager.get_active_theme()
        
        bg_color = theme.BACKGROUND
        card_color = theme.CARD
        text_color = theme.TEXT_PRIMARY
        muted_color = theme.TEXT_SECONDARY
        border_color = theme.BORDER
        
        # Thiết lập màu nền cho figure và axes
        self.figure.set_facecolor(card_color)
        self.axes.set_facecolor(bg_color)
        
        for ax in [self.axes, self.axes_twin]:
            ax.tick_params(colors=muted_color, labelsize=9)
            ax.yaxis.label.set_color(text_color)
            ax.xaxis.label.set_color(text_color)
            ax.title.set_color(text_color)
            for spine in ax.spines.values():
                spine.set_color(border_color)
                
        # Trục hoành
        self.axes.set_xlabel("Ngày trong tháng", fontsize=10, labelpad=8)
        self.axes.grid(True, color=border_color, linestyle='--', linewidth=0.55, alpha=0.3)
        self.axes.tick_params(axis='y', colors='#35D982')
        self.axes_twin.tick_params(axis='y', colors='#3399FF')
        self.axes_twin.yaxis.tick_right()
        self.axes_twin.yaxis.set_label_position('right')
        self.axes.spines['left'].set_color('#35D982')
        self.axes_twin.spines['right'].set_color('#3399FF')
        
        # Trục bên phải không đè nền xám của trục chính
        self.axes_twin.set_facecolor('none')


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hệ Thống Quản Lý Bán Tài Khoản Premium (Netflix, Disney+,...)")
        self.setWindowIcon(QIcon(resource_path("assets/app.ico")))
        # Giữ cửa sổ trong vùng làm việc thực tế, kể cả khi Windows đang scale 125–200%.
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.resize(min(1450, int(available.width() * 0.96)),
                        min(850, int(available.height() * 0.94)))
            self.move(available.center() - self.frameGeometry().center())
        else:
            self.resize(1200, 760)
        
        # Khởi tạo database (Đảm bảo bảng được tạo và nạp dữ liệu mẫu)
        database.init_db()
        
        # Áp dụng stylesheet tối màu (Dark Theme) lên toàn bộ ứng dụng
        QApplication.instance().setStyleSheet(app_styles.DARK_THEME_STYLE)
        
        # Biến lưu trữ dữ liệu tài khoản và đơn hàng hiện hành phục vụ cho thao tác
        self.current_accounts = []
        self.current_orders = []
        self.all_accounts = []
        self.acc_current_page = 1
        self.acc_rows_per_page = 10
        self._update_thread = None
        self._update_worker = None
        self._pending_update_download = None
        
        self.init_ui()
        
        # Hiển thị dữ liệu mặc định ban đầu
        self.switch_tab(0) # Mặc định mở Tab "Danh sách tài khoản"
        
        # Cập nhật trạng thái sync Google Sheets
        self.update_sync_status()

        # Kiểm tra nền sau khi UI đã sẵn sàng. Lỗi mạng ở lần kiểm tra tự động
        # được bỏ qua để không làm gián đoạn lúc người dùng mở ứng dụng.
        QTimer.singleShot(1500, self.check_update_on_startup)

    def init_ui(self):
        # Widget trung tâm chính
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Bố cục ngang: Sidebar bên trái | Content Panel bên phải
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # --- 1. SIDEBAR BÊN TRÁI ---
        sidebar_frame = QFrame()
        sidebar_frame.setObjectName("SidebarFrame")
        sidebar_frame.setFixedWidth(272)
        sidebar_layout = QVBoxLayout(sidebar_frame)
        sidebar_layout.setContentsMargins(16, 20, 16, 16)
        sidebar_layout.setSpacing(7)
        
        # Tiêu đề Sidebar thương hiệu (Netflix Store ozon)
        avatar_frame = QFrame()
        avatar_frame.setObjectName("AvatarFrame")
        avatar_frame.setFixedSize(116, 116)
        avatar_layout = QVBoxLayout(avatar_frame)
        avatar_layout.setContentsMargins(6, 6, 6, 6)
        brand_label = QLabel()
        brand_label.setPixmap(
            QPixmap(resource_path("assets/app-logo-circle.png")).scaled(
                102, 102,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        brand_label.setToolTip("Netflix Ozon")
        brand_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_label.setStyleSheet("background: transparent; border-radius: 51px;")
        avatar_layout.addWidget(brand_label)
        avatar_shadow = QGraphicsDropShadowEffect(avatar_frame)
        avatar_shadow.setBlurRadius(26)
        avatar_shadow.setOffset(0, 0)
        avatar_shadow.setColor(QColor(72, 88, 255, 155))
        avatar_frame.setGraphicsEffect(avatar_shadow)
        sidebar_layout.addWidget(avatar_frame, 0, Qt.AlignmentFlag.AlignHCenter)

        user_name = QLabel("Nghiazon")
        user_name.setObjectName("UserName")
        user_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(user_name)

        admin_badge = QLabel("♛  Admin")
        admin_badge.setObjectName("AdminBadge")
        admin_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        admin_badge.setFixedHeight(25)
        admin_badge.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sidebar_layout.addWidget(admin_badge, 0, Qt.AlignmentFlag.AlignHCenter)
        
        # Thanh phân tách mỏng
        line = QFrame()
        line.setObjectName("SidebarDivider")
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        sidebar_layout.addWidget(line)
        
        # Các nút điều hướng Sidebar
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        
        self.btn_accounts = QPushButton("●   Tài Khoản")
        self.btn_orders = QPushButton("◆   Đơn Hàng")
        self.btn_charts = QPushButton("▰   Biểu Đồ (Tổng quan)")
        self.btn_apps = QPushButton("✦   Ứng Dụng & Phần Mềm")
        self.btn_settings = QPushButton("⚙   Cài Đặt")
        
        for idx, btn in enumerate([
            self.btn_accounts, self.btn_orders, self.btn_charts,
            self.btn_apps, self.btn_settings
        ]):
            btn.setCheckable(True)
            btn.setProperty("class", "SidebarButton")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.nav_group.addButton(btn, idx)
            sidebar_layout.addWidget(btn)
            
        # Đẩy nút điều hướng lên trên, chừa khoảng trống phía dưới
        sidebar_layout.addStretch()
        
        # Google Sheets Sync Status
        self.sync_status_label = QLabel("⚠  Sheets")
        self.sync_status_label.setObjectName("SyncStatusBox")
        self.sync_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sync_status_label.setWordWrap(False)
        sidebar_layout.addWidget(self.sync_status_label)
        
        # Nút Đồng bộ Google Sheets
        self.btn_sync = QPushButton("⟳  Đồng bộ Sheets")
        self.btn_sync.setProperty("class", "SyncButton")
        self.btn_sync.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sync.clicked.connect(self.on_sync_sheets_clicked)
        self.btn_sync.setToolTip("Đồng bộ dữ liệu lên Google Sheets")
        sidebar_layout.addWidget(self.btn_sync)

        self.btn_update = QPushButton("⬇ Cập nhật phần mềm")
        self.btn_update.setProperty("class", "SecondaryButton")
        self.btn_update.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_update.setToolTip("Kiểm tra và tải phiên bản mới")
        self.btn_update.clicked.connect(self.on_update_clicked)
        sidebar_layout.addWidget(self.btn_update)
        
        # Thanh phân tách
        line2 = QFrame()
        line2.setObjectName("SidebarDivider")
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setFixedHeight(1)
        sidebar_layout.addWidget(line2)
        
        # Thông tin bản quyền / phiên bản ở đáy sidebar
        version_label = QLabel(f"Version {APP_VERSION}\nDeveloped by Nghiazon")
        version_label.setObjectName("VersionLabel")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(version_label)
        
        main_layout.addWidget(sidebar_frame, 0)
        
        # --- 2. CONTENT PANEL BÊN PHẢI (Stacked Widget) ---
        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("ContentFrame")
        self.content_stack.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding
        )
        self.content_stack.setMinimumWidth(0)
        
        self.setup_accounts_tab()
        self.setup_orders_tab()
        self.setup_charts_tab()
        self.setup_apps_tab()
        self.setup_settings_tab()
        
        main_layout.addWidget(self.content_stack, 1)
        
        # Kết nối sự kiện chuyển Tab khi bấm nút Sidebar
        self.nav_group.buttonClicked.connect(self.on_nav_clicked)

    def _run_update_worker(self, action, payload, on_success, on_error=None):
        self.btn_update.setEnabled(False)
        thread = QThread(self)
        worker = UpdateWorker(action, payload)
        self._update_thread = thread
        self._update_worker = worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(on_success)
        worker.finished.connect(thread.quit)
        worker.failed.connect(on_error or self._on_update_error)
        worker.failed.connect(thread.quit)
        worker.progress.connect(
            lambda value: self.btn_update.setText(f"Đang tải... {value}%")
        )
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(
            lambda: self._on_update_thread_finished(thread, worker)
        )
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_update_thread_finished(self, thread, worker):
        if self._update_thread is thread:
            self._update_thread = None
        if self._update_worker is worker:
            self._update_worker = None
        pending = self._pending_update_download
        self._pending_update_download = None
        if pending is not None:
            self.btn_update.setText("Đang tải... 0%")
            QTimer.singleShot(
                0,
                lambda info=pending: self._run_update_worker(
                    "download", info, self._on_update_downloaded
                ),
            )
        else:
            self._reset_update_button()

    def _reset_update_button(self):
        self.btn_update.setText("⬇ Cập nhật phần mềm")
        self.btn_update.setEnabled(True)

    def on_update_clicked(self):
        self.btn_update.setText("Đang kiểm tra bản cập nhật...")
        self._run_update_worker("check", None, self._on_update_checked)

    def check_update_on_startup(self):
        if self._update_thread is not None and self._update_thread.isRunning():
            return
        self._run_update_worker(
            "check", None, self._on_startup_update_checked, lambda _message: None
        )

    def _on_startup_update_checked(self, info):
        if info.get("update_available"):
            self._on_update_checked(info)

    def _on_update_checked(self, info):
        if not info["update_available"]:
            QMessageBox.information(
                self, "Cập nhật phần mềm", "Bạn đang dùng phiên bản mới nhất."
            )
            return
        changelog = info.get("changelog") or "Không có thông tin thay đổi."
        choice = QMessageBox.question(
            self,
            "Có phiên bản mới",
            f"Có phiên bản mới {info['version']} (hiện tại: {APP_VERSION}).\n\n"
            f"Thay đổi:\n{changelog}\n\nBạn có muốn tải và cập nhật ngay không?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if choice == QMessageBox.StandardButton.Yes:
            self.btn_update.setText("Đang tải... 0%")
            # Chờ thread kiểm tra kết thúc hẳn rồi mới tạo thread tải. Nếu tạo
            # ngay trong signal finished, hai thread dùng chung thuộc tính UI
            # và thread cũ có thể reset nút trong lúc bản mới đang tải.
            self._pending_update_download = info

    def _on_update_downloaded(self, prepared_exe):
        try:
            updater.install_and_restart(prepared_exe)
        except Exception as exc:
            updater.log_exception("Install FAILED", exc)
            self._on_update_error(str(exc))
            return
        QApplication.quit()

    def _on_update_error(self, message):
        QMessageBox.critical(
            self,
            "Lỗi cập nhật",
            f"Không thể cập nhật phần mềm.\n\n{message}\n\n"
            "App và toàn bộ dữ liệu hiện tại vẫn được giữ nguyên.",
        )

    def on_nav_clicked(self, button):
        tab_index = self.nav_group.id(button)
        self.switch_tab(tab_index)

    def switch_tab(self, index):
        """Chuyển đổi giao diện hiển thị giữa các Tab và nạp dữ liệu tương ứng."""
        # Đồng bộ hóa nút Sidebar được checked tương ứng với Tab hiện tại
        btn = self.nav_group.button(index)
        if btn:
            btn.setChecked(True)
            
        self.content_stack.setCurrentIndex(index)
        
        # Tải lại dữ liệu cho từng tab khi truy cập
        if index == 0:
            self.refresh_accounts()
        elif index == 1:
            self.refresh_orders()
        elif index == 2:
            self.refresh_charts()

    # ==========================================
    # PHÂN HỆ 1: QUẢN LÝ DANH SÁCH TÀI KHOẢN
    # ==========================================
    
    def setup_accounts_tab(self):
        page = QWidget()
        page.setObjectName("PageRoot")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(16)
        
        # --- Tiêu đề & Công cụ tìm kiếm phía trên ---
        header_layout = QHBoxLayout()
        header_text = QVBoxLayout()
        header_text.setSpacing(4)
        title_label = QLabel("Danh Sách Tài Khoản")
        title_label.setProperty("class", "TabTitle")
        subtitle_label = QLabel("Quản lý và theo dõi tất cả tài khoản của bạn")
        subtitle_label.setProperty("class", "PageSubtitle")
        header_text.addWidget(title_label)
        header_text.addWidget(subtitle_label)
        header_layout.addLayout(header_text)
        header_layout.addStretch()
        ornament = QLabel("◈   ✦   ◇")
        ornament.setStyleSheet(
            "color:#756BFF; font-size:22px; font-weight:700; background:transparent; padding:8px 16px;"
        )
        header_layout.addWidget(ornament)
        layout.addLayout(header_layout)

        toolbar_card = QFrame()
        toolbar_card.setObjectName("ToolbarCard")
        top_bar_layout = QHBoxLayout()
        toolbar_card.setLayout(top_bar_layout)
        top_bar_layout.setContentsMargins(14, 14, 14, 14)
        top_bar_layout.setSpacing(10)
        
        # Ô Tìm kiếm
        self.acc_search_input = QLineEdit()
        self.acc_search_input.setPlaceholderText("⌕  Tìm kiếm tài khoản (Email, dịch vụ...)")
        self.acc_search_input.setMinimumWidth(220)
        self.acc_search_input.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.acc_search_input.textChanged.connect(
            lambda _text: self.refresh_accounts(reset_page=True)
        )
        top_bar_layout.addWidget(self.acc_search_input, 1)
        
        # Bộ lọc trạng thái
        self.acc_filter_combo = QComboBox()
        self.acc_filter_combo.addItems(["Tất cả", "Đang hoạt động", "Đã hết hạn"])
        self.acc_filter_combo.setMinimumWidth(140)
        self.acc_filter_combo.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        top_bar_layout.addWidget(self.acc_filter_combo)
        
        # Nút áp dụng bộ lọc
        btn_apply = QPushButton("✓  Áp dụng")
        btn_apply.clicked.connect(lambda: self.refresh_accounts(reset_page=True))
        top_bar_layout.addWidget(btn_apply)
        
        # Nút thêm mới tài khoản
        btn_add = QPushButton("＋  Thêm tài khoản")
        btn_add.setProperty("class", "PrimaryButton")
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.clicked.connect(self.on_add_account_clicked)
        top_bar_layout.addWidget(btn_add)
        
        # Nút Thùng rác
        btn_trash = QPushButton("🗑️ Thùng rác")
        btn_trash.setProperty("class", "SecondaryButton")
        btn_trash.clicked.connect(self.on_account_trash_clicked)
        top_bar_layout.addWidget(btn_trash)
        
        layout.addWidget(toolbar_card)
        
        # --- Bảng hiển thị thông tin tài khoản ---
        table_card = QFrame()
        table_card.setObjectName("TableCard")
        table_card_layout = QVBoxLayout(table_card)
        table_card_layout.setContentsMargins(1, 1, 1, 10)
        table_card_layout.setSpacing(8)

        self.acc_table = CopyableTableWidget()
        self.acc_table.set_row_action_callbacks(
            lambda row: self.on_edit_account_clicked(self.current_accounts[row]),
            lambda row: self.on_delete_account_clicked(self.current_accounts[row])
        )
        self.acc_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.acc_table.setAlternatingRowColors(True)
        self.acc_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        headers = [
            "STT", "Email", "Mật khẩu", "Liên kết", "Ghi chú", "Ngày hết hạn", "Trạng thái", "Nguồn", "Thao tác"
        ]
        self.acc_table.setColumnCount(len(headers))
        self.acc_table.setHorizontalHeaderLabels(headers)

        # Thiết lập co giãn tự động cho các cột phù hợp
        header = self.acc_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(False)
        # Cột Email tự động mở rộng để luôn hiển thị đầy đủ địa chỉ dài.
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)
        # Kích thước mặc định ban đầu
        header.resizeSection(0, 50)
        header.resizeSection(3, 76)
        header.resizeSection(6, 150)
        header.resizeSection(8, 104)
        self.acc_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.acc_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        
        table_card_layout.addWidget(self.acc_table, 1)
        # Đặt chiều cao hàng mặc định để chứa các nút hành động
        self.acc_table.verticalHeader().setDefaultSectionSize(50)
        self.acc_table.ApplyDataGridViewTheme()

        pagination_layout = QHBoxLayout()
        pagination_layout.setContentsMargins(12, 0, 12, 0)
        self.acc_results_label = QLabel("Hiển thị 0 kết quả")
        self.acc_results_label.setObjectName("PaginationLabel")
        pagination_layout.addWidget(self.acc_results_label)
        pagination_layout.addStretch()

        self.acc_prev_button = QPushButton("‹")
        self.acc_prev_button.setProperty("class", "PageButton")
        self.acc_prev_button.setToolTip("Trang trước")
        self.acc_prev_button.clicked.connect(lambda: self.change_account_page(-1))
        pagination_layout.addWidget(self.acc_prev_button)

        self.acc_page_button = QPushButton("1")
        self.acc_page_button.setProperty("class", "PageCurrent")
        self.acc_page_button.setFixedSize(36, 36)
        self.acc_page_button.setEnabled(False)
        pagination_layout.addWidget(self.acc_page_button)

        self.acc_next_button = QPushButton("›")
        self.acc_next_button.setProperty("class", "PageButton")
        self.acc_next_button.setToolTip("Trang sau")
        self.acc_next_button.clicked.connect(lambda: self.change_account_page(1))
        pagination_layout.addWidget(self.acc_next_button)
        pagination_layout.addSpacing(20)

        self.acc_rows_combo = QComboBox()
        self.acc_rows_combo.addItems(["10 / trang", "20 / trang", "50 / trang"])
        self.acc_rows_combo.setFixedWidth(112)
        self.acc_rows_combo.currentIndexChanged.connect(self.change_account_page_size)
        pagination_layout.addWidget(self.acc_rows_combo)
        table_card_layout.addLayout(pagination_layout)
        layout.addWidget(table_card, 1)
        
        self.content_stack.addWidget(page)

    def update_account_status_by_expire_date(self):
        """Cập nhật trạng thái tài khoản tự động dựa trên ngày hết hạn trước khi hiển thị."""
        database.sync_account_status_by_expire_date()

    def refresh_accounts(self, *_args, reset_page=False):
        """Truy vấn cơ sở dữ liệu và tải lại bảng danh sách tài khoản."""
        self.update_account_status_by_expire_date()
        search_query = self.acc_search_input.text().strip()
        status_filter = self.acc_filter_combo.currentText()

        self.all_accounts = database.get_accounts(search_query, status_filter)
        if reset_page:
            self.acc_current_page = 1
        total_pages = max(1, math.ceil(len(self.all_accounts) / self.acc_rows_per_page))
        self.acc_current_page = min(max(1, self.acc_current_page), total_pages)
        start_index = (self.acc_current_page - 1) * self.acc_rows_per_page
        end_index = start_index + self.acc_rows_per_page
        self.current_accounts = self.all_accounts[start_index:end_index]
        
        self.acc_table.setRowCount(0)
        self.acc_table.setRowCount(len(self.current_accounts))
        
        for idx, row in enumerate(self.current_accounts):
            # Cột [STT] đánh lại theo danh sách hiện đang hiển thị.
            stt_item = QTableWidgetItem(str(start_index + idx + 1))
            stt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.acc_table.setItem(idx, 0, stt_item)

            # Cột [Email]
            email_item = QTableWidgetItem(row['email'])
            email_item.setToolTip(row['email'] or "")
            self.acc_table.setItem(idx, 1, email_item)

            # Cột [Mật khẩu]
            password = row['mat_khau'] or ""
            pwd_item = QTableWidgetItem(password)
            pwd_item.setToolTip(password)
            self.acc_table.setItem(idx, 2, pwd_item)

            # Cột [Liên kết] - badge/button hiển thị số khách hàng đang dùng
            self.acc_table.setCellWidget(idx, 3, self.create_link_button_for_account(row))

            # Cột [Ghi chú]
            note_item = QTableWidgetItem(row['ghi_chu'] or "—")
            note_item.setToolTip(row['ghi_chu'] or "Không có ghi chú")
            self.acc_table.setItem(idx, 4, note_item)

            # Cột [Ngày hết hạn] - Định dạng dd/mm/yyyy
            exp_date = row['ngay_het_han']
            try:
                qdate = QDate.fromString(exp_date, "yyyy-MM-dd")
                exp_display = qdate.toString("dd/MM/yyyy")
            except:
                exp_display = exp_date
            self.acc_table.setItem(idx, 5, QTableWidgetItem(exp_display))

            # Cột [Trạng thái]
            trang_thai = row['trang_thai']
            self.acc_table.setCellWidget(idx, 6, self.create_status_badge(trang_thai))

            # Tô màu trạng thái cho sinh động
            # Cột [Nguồn]
            self.acc_table.setItem(idx, 7, QTableWidgetItem(row['nguon'] or "Khách hàng"))

            # Cột [Thao tác] (Sửa, Xóa)
            self.acc_table.setCellWidget(idx, 8, self.create_action_buttons_for_account(row))

        # Re-apply after every reload so new rows/items/widgets never inherit
        # colours from the Windows theme.
        self.acc_table.ApplyDataGridViewTheme()
        visible_start = start_index + 1 if self.all_accounts else 0
        visible_end = min(end_index, len(self.all_accounts))
        self.acc_results_label.setText(
            f"Hiển thị {visible_start}–{visible_end} trong {len(self.all_accounts)} kết quả"
        )
        self.acc_page_button.setText(str(self.acc_current_page))
        self.acc_prev_button.setEnabled(self.acc_current_page > 1)
        self.acc_next_button.setEnabled(self.acc_current_page < total_pages)

    def change_account_page(self, direction):
        """Đổi trang hiển thị; không thay đổi truy vấn hay dữ liệu tài khoản."""
        self.acc_current_page += direction
        self.refresh_accounts()

    def change_account_page_size(self, index):
        """Thay số dòng hiển thị trên một trang."""
        sizes = (10, 20, 50)
        self.acc_rows_per_page = sizes[index] if 0 <= index < len(sizes) else 10
        self.acc_current_page = 1
        self.refresh_accounts()

    def create_status_badge(self, status):
        """Create a compact status pill that remains readable on alternating rows."""
        colors = {
            "Đang hoạt động": ("#123B2B", "#69F59A"),
            "Đã hết hạn": ("#47202A", "#FF9BAA"),
            "Đã bán": ("#18375F", "#93C5FD"),
        }
        background, foreground = colors.get(status, ("#263447", "#cbd5e1"))
        label = QLabel(status or "—")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        label.setStyleSheet(
            f"background:{background}; color:{foreground}; border-radius:9px; "
            "padding:4px 10px; font-size:11px; font-weight:700;"
        )
        label.adjustSize()
        label.setFixedHeight(26)
        wrapper = QWidget()
        wrapper.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        row = QHBoxLayout(wrapper)
        row.setContentsMargins(4, 3, 4, 3)
        row.setSpacing(0)
        row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(label)
        return wrapper

    def create_action_buttons_for_account(self, account_data):
        """Tạo cụm nút icon Sửa/Xóa nhưng giữ nguyên callback nghiệp vụ."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(7)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        widget.setFixedWidth(92)
        
        # Nút Sửa (Bút chì - xanh lục)
        edit_btn = QPushButton("")
        edit_btn.setToolTip("Chỉnh sửa thông tin tài khoản")
        edit_btn.setIcon(QIcon(resource_path("assets/edit.svg")))
        edit_btn.setIconSize(QSize(16, 16))
        edit_btn.setFixedSize(34, 32)
        edit_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        edit_btn.setProperty("class", "ActionEdit")
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.clicked.connect(lambda: self.on_edit_account_clicked(account_data))
        
        # Nút Xóa (Thùng rác - đỏ)
        delete_btn = QPushButton("")
        delete_btn.setToolTip("Đưa tài khoản vào Thùng rác")
        delete_btn.setIcon(QIcon(resource_path("assets/trash.svg")))
        delete_btn.setIconSize(QSize(16, 16))
        delete_btn.setFixedSize(34, 32)
        delete_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        delete_btn.setProperty("class", "ActionDelete")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.clicked.connect(lambda: self.on_delete_account_clicked(account_data))
        
        layout.addWidget(edit_btn)
        layout.addWidget(delete_btn)
        return widget

    def create_link_button_for_account(self, account_data):
        """Trả về một badge/button nhỏ hiển thị số khách hàng đang dùng tài khoản.

        Badge có tooltip, hiệu ứng hover, và bấm sẽ chuyển sang Tab Đơn Hàng để lọc.
        """
        email = account_data.get('email')
        # Lấy số lượng đơn hàng đang dùng email này (không tính đã xóa)
        try:
            count = database.get_active_order_count_for_email(email) if email else 0
        except Exception:
            count = 0

        # Hiển thị văn bản badge
        if count <= 0:
            text = "0"
            tooltip = "Chưa có khách"
        else:
            text = str(count)
            tooltip = f"Có {count} khách hàng đang sử dụng. Nhấn để xem."

        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(tooltip)
        btn.setFixedSize(44, 28)
        btn.setStyleSheet(
            "QPushButton{min-height:26px; max-height:26px; "
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #2588FF,stop:1 #5264EE); "
            "color:white; border:1px solid #5DA3FF; border-radius:14px; padding:0; font-weight:bold;}"
            "QPushButton:hover{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #45A0FF,stop:1 #745BFF); border-color:#A3C8FF;}"
        )
        btn.clicked.connect(lambda _, acc=account_data: self.view_customers_for_account(acc))

        wrapper = QWidget()
        wrapper.setObjectName("AccountLinkCell")
        wrapper.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        wrapper_layout = QHBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(0)
        wrapper_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wrapper_layout.addWidget(btn)
        return wrapper

    def view_customers_for_account(self, account_data):
        """Chuyển sang Tab Đơn Hàng và lọc các đơn hàng theo email hoặc ID tài khoản.

        Sắp xếp theo ngày tạo tăng dần (đơn cũ lên trên).
        """
        # Lấy email và id
        email = account_data.get('email')
        acc_id = account_data.get('id')

        # Chuyển sang Tab Đơn Hàng
        self.switch_tab(1)

        # Đảm bảo filter dropdown có danh sách nền tảng
        self.populate_order_filter_dropdown()

        # Đặt bộ lọc tìm kiếm bằng email (ưu tiên) hoặc bằng ID dưới dạng DH-xxxx
        if email:
            self.order_search_input.setText(email)
        else:
            # Nếu không có email (không thực tế), dùng ID
            self.order_search_input.setText(f"DH-{acc_id:04d}")

        # Đặt bộ lọc nền tảng về 'Tất cả'
        idx = self.order_filter_combo.findText("Tất cả")
        if idx >= 0:
            self.order_filter_combo.setCurrentIndex(idx)

        # Tải lại đơn hàng với sắp xếp tăng dần
        self.refresh_orders(sort_asc=True)

        # Nếu không có đơn hàng liên quan, hiện thông báo
        if not self.current_orders:
            QMessageBox.information(self, "Thông báo", "Chưa có khách hàng nào sử dụng tài khoản này")

    def on_add_account_clicked(self):
        """Bấm nút thêm tài khoản -> Hiển thị Dialog."""
        dlg = dialogs.AccountDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh_accounts()

    def on_edit_account_clicked(self, account_data):
        """Bấm nút sửa tài khoản -> Hiển thị Dialog."""
        dlg = dialogs.AccountDialog(self, account_data)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh_accounts()

    def on_delete_account_clicked(self, account_data):
        """Bấm nút xóa tài khoản -> Hỏi xác nhận, xóa mềm."""
        confirm = QMessageBox.question(
            self, "Xác Nhận Xóa",
            f"Bạn có chắc chắn muốn đưa tài khoản '{account_data['email']}' vào Thùng rác?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if confirm == QMessageBox.StandardButton.Yes:
            if database.delete_account_soft(account_data['id']):
                self.refresh_accounts()
            else:
                QMessageBox.critical(self, "Lỗi", "Không thể xóa tài khoản này!")

    def on_account_trash_clicked(self):
        """Mở Thùng rác tài khoản."""
        dlg = dialogs.TrashBinDialog(self, is_account_mode=True)
        dlg.exec()
        # Refresh lại danh sách chính sau khi đóng thùng rác (để thấy tài khoản được khôi phục nếu có)
        self.refresh_accounts()

    def on_sync_sheets_clicked(self):
        """Đồng bộ dữ liệu lên Google Sheets."""
        self.sync_status_label.setText("⏳ Đang đồng bộ...")
        self.sync_status_label.setStyleSheet(
            "background:#17213A; color:#B7C5FF; border:1px solid #475A9B; "
            "border-radius:8px; padding:9px; font-size:11px; font-weight:600;"
        )
        
        success, msg = database.sync_all_to_sheets()
        if success:
            QMessageBox.information(self, "Thành Công", msg)
            self.sync_status_label.setText("✅ Đã đồng bộ")
        else:
            QMessageBox.warning(self, "Lỗi Đồng bộ", msg)
            self.sync_status_label.setText("❌ Lỗi sync")
        
        self.update_sync_status()
    
    def update_sync_status(self):
        """Cập nhật trạng thái kết nối Google Sheets."""
        sync_info = database.get_sync_status()
        status = sync_info.get('status', 'Chưa biết')
        connected = sync_info.get('connected', False)
        
        if connected:
            self.sync_status_label.setText("●  Sheets đã kết nối")
            self.sync_status_label.setToolTip(status)
            self.sync_status_label.setStyleSheet(
                "background:#10271E; color:#69F59A; border:1px solid #24523B; "
                "border-radius:8px; padding:9px; font-size:11px; font-weight:600;"
            )
        else:
            self.sync_status_label.setText("⚠  Sheets chưa kết nối")
            self.sync_status_label.setToolTip(status)
            self.sync_status_label.setStyleSheet(
                "background:#211C12; color:#F7BE4C; border:1px solid #55431F; "
                "border-radius:8px; padding:9px; font-size:11px; font-weight:600;"
            )


    # ==========================================
    # PHÂN HỆ 2: QUẢN LÝ ĐƠN HÀNG (ORDERS)
    # ==========================================
    
    def setup_orders_tab(self):
        page = QWidget()
        page.setObjectName("PageRoot")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(16)
        
        # --- Tiêu đề & Công cụ tìm kiếm phía trên ---
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        title_label = QLabel("Danh Sách Đơn Hàng")
        title_label.setProperty("class", "TabTitle")
        subtitle_label = QLabel("Theo dõi khách hàng, thời hạn và doanh thu của từng đơn hàng")
        subtitle_label.setProperty("class", "PageSubtitle")
        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)
        layout.addLayout(header_layout)

        toolbar_card = QFrame()
        toolbar_card.setObjectName("ToolbarCard")
        top_bar_layout = QHBoxLayout()
        toolbar_card.setLayout(top_bar_layout)
        top_bar_layout.setContentsMargins(14, 14, 14, 14)
        top_bar_layout.setSpacing(10)
        
        # Ô Tìm kiếm đơn hàng
        self.order_search_input = QLineEdit()
        self.order_search_input.setPlaceholderText("⌕  Tìm kiếm đơn hàng (Email, tên, mã...)")
        self.order_search_input.setMinimumWidth(230)
        self.order_search_input.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.order_search_input.textChanged.connect(self.refresh_orders)
        top_bar_layout.addWidget(self.order_search_input, 1)
        
        # Bộ lọc trạng thái đơn hàng
        self.order_filter_combo = QComboBox()
        self.order_filter_combo.setMinimumWidth(140)
        self.order_filter_combo.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        top_bar_layout.addWidget(self.order_filter_combo)
        
        # Nút áp dụng bộ lọc đơn hàng
        btn_apply = QPushButton("✓  Áp dụng")
        btn_apply.clicked.connect(self.refresh_orders)
        top_bar_layout.addWidget(btn_apply)
        
        # Nút xóa bộ lọc (trả về danh sách tất cả đơn hàng)
        btn_clear_filter = QPushButton("Xóa bộ lọc")
        btn_clear_filter.setToolTip("Xóa tìm kiếm và đặt bộ lọc về 'Tất cả'")
        btn_clear_filter.clicked.connect(self.clear_order_filter)
        top_bar_layout.addWidget(btn_clear_filter)
        
        # Nút thêm mới đơn hàng
        btn_add = QPushButton("＋  Thêm đơn hàng")
        btn_add.setProperty("class", "PrimaryButton")
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.clicked.connect(self.on_add_order_clicked)
        top_bar_layout.addWidget(btn_add)
        
        # Nút Thùng rác đơn hàng
        btn_trash = QPushButton("🗑️ Thùng rác")
        btn_trash.setProperty("class", "SecondaryButton")
        btn_trash.clicked.connect(self.on_order_trash_clicked)
        top_bar_layout.addWidget(btn_trash)
        
        layout.addWidget(toolbar_card)
        
        # --- Bảng hiển thị thông tin đơn hàng ---
        table_card = QFrame()
        table_card.setObjectName("TableCard")
        table_card_layout = QVBoxLayout(table_card)
        table_card_layout.setContentsMargins(1, 1, 1, 1)
        self.order_table = CopyableTableWidget()
        self.order_table.set_row_action_callbacks(
            lambda row: self.on_edit_order_clicked(self.current_orders[row]),
            lambda row: self.on_delete_order_clicked(self.current_orders[row])
        )
        self.order_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.order_table.setAlternatingRowColors(True)
        self.order_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        headers = [
            "STT", "Tài khoản (Email)", "Nền tảng", "Tên khách hàng", 
            "Số tiền", "Ghi chú", "Ngày mua", "Ngày hết hạn", "Trạng thái", "Thao tác"
        ]
        self.order_table.setColumnCount(len(headers))
        self.order_table.setHorizontalHeaderLabels(headers)
        
        header = self.order_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.Fixed)  # Thao tác
        header.resizeSection(0, 50)
        header.resizeSection(8, 150)
        header.resizeSection(9, 104)
        self.order_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.order_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        
        table_card_layout.addWidget(self.order_table)
        layout.addWidget(table_card, 1)
        # Đặt chiều cao hàng mặc định cho bảng đơn hàng
        self.order_table.verticalHeader().setDefaultSectionSize(50)
        self.order_table.ApplyDataGridViewTheme()
        
        self.content_stack.addWidget(page)

    def populate_order_filter_dropdown(self):
        """Thiết lập các lựa chọn lọc cố định theo trạng thái đơn hàng."""
        current_text = self.order_filter_combo.currentText()
        self.order_filter_combo.blockSignals(True)
        self.order_filter_combo.clear()
        self.order_filter_combo.addItems([
            "Tất cả",
            "Đơn hàng mới nhất",
            "Đã hết hạn",
        ])
        
        # Đặt lại giá trị cũ nếu khớp
        idx = self.order_filter_combo.findText(current_text)
        if idx >= 0:
            self.order_filter_combo.setCurrentIndex(idx)
        else:
            self.order_filter_combo.setCurrentIndex(0)
            
        self.order_filter_combo.blockSignals(False)

    def refresh_orders(self, sort_asc=False):
        """Tải dữ liệu từ DB lên bảng danh sách đơn hàng."""
        # Đảm bảo dropdown chỉ chứa các lựa chọn lọc theo trạng thái.
        self.populate_order_filter_dropdown()
        
        search_query = self.order_search_input.text().strip()
        status_filter = self.order_filter_combo.currentText()
        
        self.current_orders = database.get_orders(search_query, status_filter)
        
        self.order_table.setRowCount(0)
        self.order_table.setRowCount(len(self.current_orders))
        
        for idx, row in enumerate(self.current_orders):
            # Cột [STT] đánh lại theo danh sách hiện đang hiển thị.
            stt_item = QTableWidgetItem(str(idx + 1))
            stt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.order_table.setItem(idx, 0, stt_item)

            # Tài khoản Email
            email_item = QTableWidgetItem(row['email_tai_khoan'] or "—")
            email_item.setToolTip(row['email_tai_khoan'] or "Không có tài khoản")
            self.order_table.setItem(idx, 1, email_item)
            
            # Nền tảng
            self.order_table.setItem(idx, 2, QTableWidgetItem(row['nen_tang']))
            
            # Tên khách hàng
            self.order_table.setItem(idx, 3, QTableWidgetItem(row['ten_khach_hang'] or "—"))
            
            # Số tiền (Định dạng VND, ví dụ: 130,000đ)
            so_tien = row['so_tien'] or 0.0
            amount_item = QTableWidgetItem(f"{so_tien:,.0f} ₫")
            amount_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.order_table.setItem(idx, 4, amount_item)
            from app_styles import ThemeManager
            theme = ThemeManager.get_active_theme()
            self.order_table.item(idx, 4).setForeground(QColor(theme.SUCCESS)) # Chữ màu success theo theme cho tiền bạc dễ nhìn
            
            # Ghi chú
            note_item = QTableWidgetItem(row['ghi_chu'] or "—")
            note_item.setToolTip(row['ghi_chu'] or "Không có ghi chú")
            self.order_table.setItem(idx, 5, note_item)

            # Ngày mua (dd/mm/yyyy)
            purchase_date = row.get('ngay_mua', '')
            purchase_qdate = QDate.fromString(purchase_date, "yyyy-MM-dd")
            purchase_display = purchase_qdate.toString("dd/MM/yyyy") if purchase_qdate.isValid() else (purchase_date or "—")
            self.order_table.setItem(idx, 6, QTableWidgetItem(purchase_display))
            
            # Ngày hết hạn (dd/mm/yyyy)
            exp_date = row['ngay_het_han']
            try:
                qdate = QDate.fromString(exp_date, "yyyy-MM-dd")
                exp_display = qdate.toString("dd/MM/yyyy")
            except:
                exp_display = exp_date or "—"
            self.order_table.setItem(idx, 7, QTableWidgetItem(exp_display))
            
            # Trạng thái (tính từ ngày hết hạn)
            try:
                from datetime import date
                ngay_het_han = date.fromisoformat(exp_date)
                is_expired = ngay_het_han < date.today()
                trang_thai = "Đã hết hạn" if is_expired else "Đang hoạt động"
            except:
                trang_thai = "—"
            
            self.order_table.setCellWidget(idx, 8, self.create_status_badge(trang_thai))
            
            # Cột [Thao tác] (Sửa, Xóa)
            self.order_table.setCellWidget(idx, 9, self.create_action_buttons_for_order(row))

        self.order_table.ApplyDataGridViewTheme()
        for row_index in range(self.order_table.rowCount()):
            status_item = self.order_table.item(row_index, 8)
            if status_item and status_item.text() == "Đã hết hạn":
                highlight_expired_status(status_item)

    def create_action_buttons_for_order(self, order_data):
        """Tạo cụm nút icon Sửa/Xóa nhưng giữ nguyên callback nghiệp vụ."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        widget.setFixedWidth(92)
        
        # Nút Sửa
        edit_btn = QPushButton("")
        edit_btn.setToolTip("Chỉnh sửa thông tin đơn hàng")
        edit_btn.setIcon(QIcon(resource_path("assets/edit.svg")))
        edit_btn.setIconSize(QSize(16, 16))
        edit_btn.setFixedSize(34, 32)
        edit_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        edit_btn.setProperty("class", "ActionEdit")
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.clicked.connect(lambda _, od=order_data: self.on_edit_order_clicked(od))
        
        # Nút Xóa
        delete_btn = QPushButton("")
        delete_btn.setToolTip("Đưa đơn hàng vào Thùng rác")
        delete_btn.setIcon(QIcon(resource_path("assets/trash.svg")))
        delete_btn.setIconSize(QSize(16, 16))
        delete_btn.setFixedSize(34, 32)
        delete_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        delete_btn.setProperty("class", "ActionDelete")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.clicked.connect(lambda _, od=order_data: self.on_delete_order_clicked(od))
        
        layout.addWidget(edit_btn)
        layout.addWidget(delete_btn)
        return widget

    def on_add_order_clicked(self):
        """Bấm nút thêm đơn hàng -> Hiển thị Dialog."""
        dlg = dialogs.OrderDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh_orders()
            self.refresh_charts()

    def on_edit_order_clicked(self, order_data):
        """Bấm nút sửa đơn hàng -> Hiển thị Dialog."""
        dlg = dialogs.OrderDialog(self, order_data)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh_orders()
            self.refresh_charts()

    def on_delete_order_clicked(self, order_data):
        """Bấm nút xóa đơn hàng -> Hỏi xác nhận, xóa mềm."""
        ma_dh = f"DH-{order_data['id']:04d}"
        confirm = QMessageBox.question(
            self, "Xác Nhận Xóa Đơn Hàng",
            f"Bạn có chắc chắn muốn đưa đơn hàng '{ma_dh}' vào Thùng rác?\nTài khoản liên kết sẽ được tự động giải phóng về trạng thái rảnh rỗi.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if confirm == QMessageBox.StandardButton.Yes:
            if database.delete_order_soft(order_data['id']):
                self.refresh_orders()
                self.refresh_charts()
            else:
                QMessageBox.critical(self, "Lỗi", "Không thể xóa đơn hàng này!")

    def on_order_trash_clicked(self):
        """Mở Thùng rác đơn hàng."""
        dlg = dialogs.TrashBinDialog(self, is_account_mode=False)
        dlg.exec()
        self.refresh_orders()
        self.refresh_charts()

    def clear_order_filter(self):
        """Xóa bộ lọc tìm kiếm đơn hàng và trả về 'Tất cả'."""
        self.order_search_input.clear()
        idx = self.order_filter_combo.findText("Tất cả")
        if idx >= 0:
            self.order_filter_combo.setCurrentIndex(idx)
        self.refresh_orders()


    # ==========================================
    # PHÂN HỆ 3: BIỂU ĐỒ & THỐNG KÊ (DASHBOARD)
    # ==========================================

    def setup_apps_tab(self):
        """Trang trình bày các tác vụ tích hợp đã có, không thêm nghiệp vụ mới."""
        page = QWidget()
        page.setObjectName("PageRoot")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(18)

        title = QLabel("Ứng Dụng & Phần Mềm")
        title.setProperty("class", "TabTitle")
        subtitle = QLabel("Quản lý kết nối Google Sheets và phiên bản ứng dụng")
        subtitle.setProperty("class", "PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        cards = QHBoxLayout()
        cards.setSpacing(16)

        sheets_card = QFrame()
        sheets_card.setObjectName("InfoCard")
        sheets_layout = QVBoxLayout(sheets_card)
        sheets_layout.setContentsMargins(24, 22, 24, 22)
        sheets_layout.setSpacing(12)
        sheets_icon = QLabel("◉")
        sheets_icon.setStyleSheet("color:#3D9BFF; font-size:32px; background:transparent;")
        sheets_title = QLabel("Google Sheets")
        sheets_title.setProperty("class", "SectionTitle")
        sheets_desc = QLabel("Đồng bộ dữ liệu tài khoản và đơn hàng bằng cấu hình hiện tại của ứng dụng.")
        sheets_desc.setProperty("class", "PageSubtitle")
        sheets_desc.setWordWrap(True)
        sheets_button = QPushButton("⟳  Đồng bộ Sheets")
        sheets_button.setProperty("class", "SyncButton")
        sheets_button.clicked.connect(self.on_sync_sheets_clicked)
        sheets_layout.addWidget(sheets_icon)
        sheets_layout.addWidget(sheets_title)
        sheets_layout.addWidget(sheets_desc)
        sheets_layout.addStretch()
        sheets_layout.addWidget(sheets_button)
        cards.addWidget(sheets_card)

        update_card = QFrame()
        update_card.setObjectName("InfoCard")
        update_layout = QVBoxLayout(update_card)
        update_layout.setContentsMargins(24, 22, 24, 22)
        update_layout.setSpacing(12)
        update_icon = QLabel("⬇")
        update_icon.setStyleSheet("color:#B35CFF; font-size:32px; background:transparent;")
        update_title = QLabel("Cập nhật phần mềm")
        update_title.setProperty("class", "SectionTitle")
        update_desc = QLabel("Kiểm tra và cài đặt phiên bản mới bằng quy trình cập nhật an toàn sẵn có.")
        update_desc.setProperty("class", "PageSubtitle")
        update_desc.setWordWrap(True)
        update_button = QPushButton("⬇  Kiểm tra cập nhật")
        update_button.setProperty("class", "PrimaryButton")
        update_button.clicked.connect(self.on_update_clicked)
        update_layout.addWidget(update_icon)
        update_layout.addWidget(update_title)
        update_layout.addWidget(update_desc)
        update_layout.addStretch()
        update_layout.addWidget(update_button)
        cards.addWidget(update_card)

        layout.addLayout(cards, 1)
        layout.addStretch()
        self.content_stack.addWidget(page)

    def setup_settings_tab(self):
        """Thiết lập trang Cài đặt giao diện và cấu hình theme."""
        from app_styles import ThemeManager
        page = QWidget()
        page.setObjectName("PageRoot")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(20)

        # Tiêu đề Tab
        title = QLabel("Cài Đặt")
        title.setProperty("class", "TabTitle")
        subtitle = QLabel("Quản lý tùy chọn hiển thị và thiết lập hệ thống")
        subtitle.setProperty("class", "PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        # Card chứa 3 lựa chọn theme
        theme_card = QFrame()
        theme_card.setObjectName("ToolbarCard")
        theme_card_layout = QVBoxLayout(theme_card)
        theme_card_layout.setContentsMargins(24, 22, 24, 22)
        theme_card_layout.setSpacing(16)

        card_title = QLabel("Giao diện ứng dụng")
        card_title.setProperty("class", "SectionTitle")
        theme_card_layout.addWidget(card_title)
        
        card_desc = QLabel("Chọn giao diện hiển thị phù hợp với sở thích của bạn. Hệ thống sẽ lưu và áp dụng ngay lập tức.")
        card_desc.setProperty("class", "PageSubtitle")
        theme_card_layout.addWidget(card_desc)

        # Hộp chứa 3 card option nằm cạnh nhau
        options_layout = QHBoxLayout()
        options_layout.setSpacing(15)

        self.card_dark_neon = ThemeOptionCard(
            "dark_neon", "Dark Neon", "Giao diện tối xanh tím hiện đại\n■ Nền xanh tím  ■ Gradient  ■ Neon",
            ["#070D1A", "#0C1728", "#267DFF", "#FFFFFF"], self
        )
        self.card_classic_dark = ThemeOptionCard(
            "classic_dark", "Classic Dark", "Giao diện tối cổ điển đơn giản\n■ Nền xám đậm  ■ Accent xanh  ■ Tối giản",
            ["#121212", "#1E1E1E", "#2563EB", "#E0E0E0"], self
        )
        self.card_light = ThemeOptionCard(
            "light", "Light", "Giao diện sáng trắng hiện đại\n■ Nền sáng trắng  ■ Chữ tối  ■ Dễ đọc",
            ["#F1F5F9", "#FFFFFF", "#6366F1", "#0F172A"], self
        )

        options_layout.addWidget(self.card_dark_neon, 1)
        options_layout.addWidget(self.card_classic_dark, 1)
        options_layout.addWidget(self.card_light, 1)
        theme_card_layout.addLayout(options_layout)

        # Connect signals directly for instant switching
        self.card_dark_neon.clicked.connect(self.change_theme)
        self.card_classic_dark.clicked.connect(self.change_theme)
        self.card_light.clicked.connect(self.change_theme)

        # Status Message (Non-blocking notification)
        self.lbl_status_msg = QLabel("")
        self.lbl_status_msg.setProperty("class", "SafetyLabel")
        self.lbl_status_msg.setStyleSheet("color: #2ecc71; font-weight: bold; background: transparent; border: none; padding: 0;")
        theme_card_layout.addWidget(self.lbl_status_msg)

        # Chọn theme hiện tại
        current_theme = ThemeManager.get_theme_name()
        self.selected_theme_id = current_theme
        self.select_theme_option(current_theme)

        layout.addWidget(theme_card)

        # Panel thông báo an toàn dữ liệu
        safety_card = QFrame()
        safety_card.setObjectName("InfoCard")
        safety_layout = QVBoxLayout(safety_card)
        safety_layout.setContentsMargins(24, 20, 24, 20)
        safety_layout.setSpacing(10)

        safety_title = QLabel("✦  Trạng thái bảo toàn dữ liệu")
        safety_title.setProperty("class", "SectionTitle")
        safety_layout.addWidget(safety_title)

        safety_desc = QLabel(
            "Việc thay đổi giao diện (theme) chỉ áp dụng màu sắc hình ảnh hiển thị ngoài frontend. "
            "Toàn bộ dữ liệu tài khoản, dữ liệu đơn hàng, cấu trúc database SQLite, logic đồng bộ Google Sheets, "
            "cũng như quy trình cập nhật tự động hoàn toàn được giữ nguyên trạng và bảo vệ tuyệt đối."
        )
        safety_desc.setProperty("class", "PageSubtitle")
        safety_desc.setWordWrap(True)
        safety_layout.addWidget(safety_desc)

        safety_badge = QLabel("✓ Dữ liệu tài khoản & đơn hàng được bảo toàn tuyệt đối     ✓ Cấu trúc database được giữ nguyên")
        safety_badge.setProperty("class", "SafetyLabel")
        safety_layout.addWidget(safety_badge)

        layout.addWidget(safety_card)
        layout.addStretch()
        self.content_stack.addWidget(page)

    def select_theme_option(self, theme_id):
        self.selected_theme_id = theme_id
        self.card_dark_neon.set_selected(theme_id == "dark_neon")
        self.card_classic_dark.set_selected(theme_id == "classic_dark")
        self.card_light.set_selected(theme_id == "light")

    def change_theme(self, theme_id):
        from app_styles import ThemeManager
        # Cập nhật card đang chọn trên UI ngay lập tức
        self.select_theme_option(theme_id)
        
        # Lưu theme vào file config và lấy stylesheet mới
        if ThemeManager.set_theme(theme_id):
            # Cập nhật stylesheet toàn ứng dụng (app-level)
            QApplication.instance().setStyleSheet(ThemeManager.get_stylesheet())
            
            # Cập nhật lại màu sắc bảng biểu chính
            self.acc_table.ApplyDataGridViewTheme()
            self.order_table.ApplyDataGridViewTheme()
            
            # Tải lại dữ liệu các bảng để vẽ màu text mới
            self.refresh_accounts()
            self.refresh_orders()
            
            # Vẽ lại biểu đồ Matplotlib với dải màu của theme mới
            self.refresh_charts()
            
            # Hiển thị thông báo trạng thái nhỏ không chặn (non-blocking status label)
            self.lbl_status_msg.setText("✓ Đã tự động áp dụng và lưu giao diện mới.")
            QTimer.singleShot(3000, lambda: self.lbl_status_msg.setText(""))
    
    def setup_charts_tab(self):
        page = QWidget()
        page.setObjectName("PageRoot")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(15)
        
        # Tiêu đề Tab
        title_label = QLabel("Tổng Quan Hoạt Động Kinh Doanh")
        title_label.setProperty("class", "TabTitle")
        layout.addWidget(title_label)
        subtitle_label = QLabel("Theo dõi doanh thu, đơn hàng và hiệu suất theo thời gian")
        subtitle_label.setProperty("class", "PageSubtitle")
        layout.addWidget(subtitle_label)
        
        # --- KHU VỰC 4 THẺ THỐNG KÊ (QHBoxLayout) ---
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(15)
        
        # 1. Tổng đơn hàng
        self.card_total_orders = self.create_stat_card(
            "TỔNG ĐƠN HÀNG", "0 đơn", "♧", "#2FE58B", "#123F35", "#0B2C2A"
        )
        # 2. Đơn hàng còn bảo hành
        self.card_active_warranty = self.create_stat_card(
            "CÒN BẢO HÀNH", "0 đơn", "▣", "#3B9CFF", "#123B67", "#102945"
        )
        # 3. Tổng doanh thu
        self.card_total_revenue = self.create_stat_card(
            "TỔNG DOANH THU", "0đ", "$", "#35E58A", "#12483A", "#0D302B"
        )
        # 4. Doanh thu tháng
        self.card_month_revenue = self.create_stat_card(
            "DOANH THU THÁNG", "0đ", "▥", "#FFD21A", "#5B4A03", "#302905"
        )
        
        cards_layout.addWidget(self.card_total_orders)
        cards_layout.addWidget(self.card_active_warranty)
        cards_layout.addWidget(self.card_total_revenue)
        cards_layout.addWidget(self.card_month_revenue)
        
        layout.addLayout(cards_layout)
        
        # --- KHU VỰC BIỂU ĐỒ ĐƯỜNG (Matplotlib) ---
        chart_frame = QFrame()
        chart_frame.setObjectName("ChartContainer")
        chart_frame.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        chart_frame.setStyleSheet("""
            QFrame#ChartContainer {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #101B29, stop:1 #0A1521);
                border: 1px solid #29384A;
                border-radius: 12px;
            }
        """)
        chart_layout = QVBoxLayout(chart_frame)
        chart_layout.setContentsMargins(10, 10, 10, 10)
        chart_layout.setSpacing(8)

        chart_header = QHBoxLayout()
        self.chart_title_label = QLabel("Tổng quan doanh số & đơn hàng")
        self.chart_title_label.setMinimumWidth(0)
        self.chart_title_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.chart_title_label.setStyleSheet(
            "border:none; color:#F5F7FA; font-size:15px; font-weight:600; background:transparent;"
        )
        chart_header.addWidget(self.chart_title_label)
        chart_header.addStretch()
        self.chart_month_combo = QComboBox()
        self.chart_month_combo.setFixedWidth(170)
        self.chart_month_combo.setStyleSheet(
            "QComboBox { color:#DDE3EA; background:#18202B; border:1px solid #354052; padding:6px 10px; }"
        )
        chart_header.addWidget(self.chart_month_combo)
        self.btn_export_chart = QPushButton("⇩  Xuất biểu đồ")
        self.btn_export_chart.setFixedWidth(130)
        self.btn_export_chart.setStyleSheet(
            "QPushButton { background:#172231; border:1px solid #35465A; border-radius:7px; "
            "padding:7px 12px; color:#F1F5F9; } QPushButton:hover { background:#213148; border-color:#4B6683; }"
        )
        self.btn_export_chart.clicked.connect(self.export_chart)
        chart_header.addWidget(self.btn_export_chart)
        chart_layout.addLayout(chart_header)

        today = QDate.currentDate()
        for offset in range(12):
            month_date = today.addMonths(-offset)
            self.chart_month_combo.addItem(
                f"Tháng {month_date.month():02d}/{month_date.year()}",
                (month_date.year(), month_date.month())
            )
        self.chart_month_combo.currentIndexChanged.connect(self.refresh_charts)
        
        # Canvas vẽ biểu đồ
        self.canvas = MplCanvas(self, width=6, height=4, dpi=100)
        self.canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        chart_layout.addWidget(self.canvas)

        # Thanh thống kê nhanh nằm ngay dưới biểu đồ.
        summary_frame = QFrame()
        summary_frame.setMinimumHeight(132)
        summary_frame.setObjectName("ChartSummary")
        summary_frame.setStyleSheet("""
            QFrame#ChartSummary { background: #121E2D; border: 1px solid #2B3A4D; border-radius: 8px; }
            QLabel { border: none; background: transparent; }
        """)
        summary_layout = QHBoxLayout(summary_frame)
        summary_layout.setContentsMargins(10, 10, 10, 10)
        summary_layout.setSpacing(0)
        self.chart_summary_cards = []
        summary_titles = ("Doanh thu cao nhất", "Doanh thu thấp nhất", "Ngày có nhiều đơn nhất",
                          "Tổng đơn hàng", "Doanh thu trung bình/ngày")
        summary_icons = ("💰", "📉", "🛒", "📦", "📊")
        for index, (title, icon) in enumerate(zip(summary_titles, summary_icons)):
            card = QFrame()
            card.setObjectName(f"QuickStatCard{index}")
            card.setMinimumWidth(0)
            card.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
            card.setStyleSheet(
                f"QFrame#QuickStatCard{index} {{ background:#152334; border:none; border-radius:7px; }}"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            card_layout.setSpacing(8)
            card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            title_label = QLabel(f"{icon}  {title}")
            title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title_label.setWordWrap(True)
            title_label.setStyleSheet(
                'font-family:"Segoe UI Semibold"; font-size:13px; font-weight:600; color:#BFC9D4;'
            )

            value_label = QLabel("—")
            value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value_label.setStyleSheet(
                'font-family:"Segoe UI"; font-size:23px; font-weight:700; color:#E5E7EB;'
            )

            note_label = QLabel("—")
            note_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            note_label.setStyleSheet(
                'font-family:"Segoe UI"; font-size:12px; font-weight:400; color:#AEB9C7;'
            )
            card_layout.addWidget(title_label)
            card_layout.addWidget(value_label)
            card_layout.addWidget(note_label)
            summary_layout.addWidget(card, 1)
            self.chart_summary_cards.append((value_label, note_label))
            if index < len(summary_titles) - 1:
                divider = QFrame()
                divider.setFixedWidth(1)
                divider.setStyleSheet("background:#2B3A4D; border:none; margin:12px 5px;")
                summary_layout.addWidget(divider)
        chart_layout.addWidget(summary_frame)
        
        layout.addWidget(chart_frame, 1) # Cho phép khu vực biểu đồ giãn rộng chiếm không gian chính
        
        self.content_stack.addWidget(page)

    def create_stat_card(self, label_text, value_text, icon_text, accent, color_start, color_end):
        """Hàm helper tạo một Thẻ thống kê đẹp mắt."""
        card_frame = QFrame()
        card_frame.setObjectName("StatCard")
        card_frame.setProperty("class", "StatCard")
        card_frame.setStyleSheet(f"""
            QFrame#StatCard {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {color_start}, stop:1 {color_end});
                border: 1px solid {accent};
                border-radius: 11px;
            }}
        """)
        card_frame.setMinimumHeight(94)
        shadow = QGraphicsDropShadowEffect(card_frame)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor(0, 0, 0, 105))
        card_frame.setGraphicsEffect(shadow)
        
        card_layout = QHBoxLayout(card_frame)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(14)

        icon_label = QLabel(icon_text)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setFixedSize(52, 52)
        icon_label.setStyleSheet(
            f"background:{color_start}; color:{accent}; border:1px solid {accent}; "
            "border-radius:26px; font-size:25px; font-weight:700;"
        )
        card_layout.addWidget(icon_label)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        
        val_label = QLabel(value_text)
        val_label.setObjectName("StatCardValue")
        val_label.setProperty("class", "StatCardValue")
        val_label.setStyleSheet(
            "font-size: 22px; font-weight: bold; color: #FFFFFF; background: transparent; border: none;"
        )
        
        lbl_label = QLabel(label_text)
        lbl_label.setObjectName("StatCardLabel")
        lbl_label.setProperty("class", "StatCardLabel")
        lbl_label.setStyleSheet(
            "font-size: 11px; color: #E5E5E5; font-weight: bold; background: transparent; border: none;"
        )
        
        text_layout.addWidget(val_label)
        text_layout.addWidget(lbl_label)
        card_layout.addLayout(text_layout, 1)
        
        # Lưu tham chiếu nhãn để thay đổi dữ liệu sau này
        card_frame.val_label = val_label
        return card_frame

    def refresh_charts(self):
        """Hàm kích hoạt tính toán SELECT thống kê và vẽ lại biểu đồ đường."""
        # 1. Truy vấn các số liệu cho 4 thẻ thống kê từ Database
        stats = database.get_dashboard_stats()
        
        self.card_total_orders.val_label.setText(f"{stats['total_orders']} đơn")
        self.card_active_warranty.val_label.setText(f"{stats['active_warranty']} đơn")
        self.card_total_revenue.val_label.setText(f"{stats['total_revenue']:,.0f}đ")
        self.card_month_revenue.val_label.setText(f"{stats['month_revenue']:,.0f}đ")
        
        # 2. Truy vấn dữ liệu biểu đồ và vẽ lại đường biểu diễn
        selected_period = self.chart_month_combo.currentData()
        if selected_period:
            selected_year, selected_month = selected_period
            chart_data = database.get_chart_data(selected_year, selected_month)
        else:
            chart_data = database.get_chart_data_current_month()
        
        days = chart_data['days']
        revenue_data = chart_data['revenue']
        orders_data = chart_data['orders']
        month_name = chart_data['month_name']
        
        # Xóa trắng dữ liệu biểu đồ cũ để tránh đè chồng chất lên nhau
        self.canvas.axes.clear()
        self.canvas.axes_twin.clear()
        
        # Tạo dựng lại cấu hình trục hoành trục tung sau khi xóa
        self.canvas.style_axes()
        
        # Đặt tên tiêu đề biểu đồ tự động theo tháng
        self.chart_title_label.setText(f"Tổng quan doanh số & đơn hàng tháng {month_name}")
        self.card_month_revenue.val_label.setText(f"{sum(revenue_data):,.0f}đ")
        
        # VẼ ĐƯỜNG 1: DOANH THU (Trục tung bên Trái - Màu Xanh lá)
        line_rev = self.canvas.axes.plot(
            days, revenue_data, 
            color='#2ecc71', marker='o', markersize=4, linewidth=2, 
            label="Doanh thu (VND)"
        )
        # Fill nhiều lớp tạo cảm giác gradient nhẹ nhưng vẫn giữ nền tối dễ đọc.
        max_revenue = max(revenue_data, default=0)
        for fraction, alpha in ((1.0, 0.035), (0.72, 0.045), (0.45, 0.055)):
            self.canvas.axes.fill_between(
                days, 0, [min(value, max_revenue * fraction) for value in revenue_data],
                color='#2ecc71', alpha=alpha, linewidth=0
            )
        self.canvas.axes.set_ylabel("Doanh thu (VND)", fontsize=10, labelpad=10, color='#35D982')
        # Định dạng hiển thị tiền VNĐ gọn trên tick Y
        self.canvas.axes.yaxis.set_major_formatter(
            matplotlib.ticker.FuncFormatter(lambda x, p: f"{x:,.0f}đ" if x < 1000000 else f"{x/1000000:.1f}tr đ")
        )
        
        # VẼ ĐƯỜNG 2: SỐ ĐƠN HÀNG (Trục tung bên Phải - Màu Đỏ Neon)
        line_ord = self.canvas.axes_twin.plot(
            days, orders_data, 
            color='#3399ff', marker='o', markersize=4, linewidth=1.8,
            label="Số đơn hàng"
        )
        self.canvas.axes_twin.set_ylabel("Số đơn hàng", fontsize=10, labelpad=10, color='#3399FF')
        # Chỉ nhận tick số nguyên cho đơn hàng
        self.canvas.axes_twin.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
        
        # Thiết lập khoảng giới hạn trục hoành gọn gàng
        if days:
            # Thêm một khoảng đệm rất nhỏ để marker ngày 1 và ngày cuối không bị cắt.
            self.canvas.axes.set_xlim(1, len(days))
            self.canvas.axes.set_xticks(days)
            self.canvas.axes.tick_params(axis='x', labelsize=8)
            
        # Gom nhãn chú thích (Legend) chung từ cả 2 đường vẽ
        lines = line_rev + line_ord
        labels = [l.get_label() for l in lines]
        from app_styles import ThemeManager
        theme = ThemeManager.get_active_theme()
        legend = self.canvas.axes.legend(
            lines, labels, loc='upper center', bbox_to_anchor=(0.5, 1.10), ncol=2,
            facecolor=theme.BACKGROUND, edgecolor=theme.BORDER
        )
        for text in legend.get_texts():
            text.set_color(theme.TEXT_PRIMARY)
            
        # Co cấu khít bố cục
        # Chừa lề riêng cho hai nhãn trục Y, tránh chồng chữ khi cửa sổ co lại.
        # Chừa đủ chỗ cho nhãn trục và tick tiền tệ dài ở cả hai cạnh.
        # Lề cũ 9% khiến nhãn "Doanh thu (VND)" chạm mép canvas và bị cắt.
        self.canvas.figure.subplots_adjust(left=0.16, right=0.88, bottom=0.16, top=0.86)
        self.canvas.set_hover_data(days, revenue_data, orders_data, month_name)

        lowest_revenue = min(revenue_data, default=0)
        highest_revenue = max(revenue_data, default=0)
        highest_day = days[revenue_data.index(highest_revenue)] if days else 0
        lowest_days = [days[i] for i, value in enumerate(revenue_data) if value == lowest_revenue]
        max_orders = max(orders_data, default=0)
        max_order_day = days[orders_data.index(max_orders)] if days else 0
        total_orders = sum(orders_data)
        average_revenue = sum(revenue_data) / len(days) if days else 0
        summary_values = (
            ("Doanh thu cao nhất", f"{highest_revenue:,.0f}đ", f"Ngày {highest_day:02d}/{month_name[:2]}"),
            ("Doanh thu thấp nhất", f"{lowest_revenue:,.0f}đ", "Nhiều ngày" if len(lowest_days) > 1 else f"Ngày {lowest_days[0]:02d}/{month_name[:2]}"),
            ("Ngày có nhiều đơn nhất", f"{max_orders} đơn", f"Ngày {max_order_day:02d}/{month_name[:2]}"),
            ("Tổng đơn hàng", f"{total_orders} đơn", "Trong tháng"),
            ("Doanh thu trung bình/ngày", f"{average_revenue:,.0f}đ", "Trong tháng"),
        )
        raw_values = (highest_revenue, lowest_revenue, max_orders, total_orders, average_revenue)
        category_colors = ('#35D982', '#35D982', '#4DA3FF', '#4DA3FF', '#35D982')
        for (value_label, note_label), (_, value, note), raw_value, category_color in zip(
                self.chart_summary_cards, summary_values, raw_values, category_colors):
            value_color = category_color if raw_value else '#E5E7EB'
            value_label.setText(value)
            value_label.setStyleSheet(
                f'font-family:"Segoe UI"; font-size:23px; font-weight:700; color:{value_color};'
            )
            note_label.setText(note)
        
        # Vẽ lại canvas
        self.canvas.draw()

    def export_chart(self):
        """Xuất riêng biểu đồ hiện tại thành PNG độ phân giải cao."""
        month_name = getattr(self.canvas, 'chart_month', QDate.currentDate().toString('MM/yyyy'))
        default_name = f"bieu_do_{month_name.replace('/', '_')}.png"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Xuất biểu đồ", default_name, "Ảnh PNG (*.png);;Ảnh JPEG (*.jpg)"
        )
        if not file_path:
            return
        try:
            self.canvas.figure.savefig(file_path, dpi=180, facecolor='#0C1724', bbox_inches='tight')
            QMessageBox.information(self, "Xuất biểu đồ", "Đã lưu biểu đồ thành công.")
        except Exception as exc:
            QMessageBox.critical(self, "Lỗi", f"Không thể xuất biểu đồ:\n{exc}")


if __name__ == '__main__':
    if "--self-test-update" in sys.argv:
        raise SystemExit(0 if updater.frozen_runtime_self_test() else 1)

    # Hỗ trợ High DPI hiển thị mịn màng trên Windows màn hình phân giải cao
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(resource_path("assets/app.ico")))
    
    # Tạo font chữ mặc định của ứng dụng
    default_font = QFont("Segoe UI", 10)
    app.setFont(default_font)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
