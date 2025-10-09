"""
webview component
"""

import json
import time
from PySide6.QtCore import QTimer, QUrl, Signal, QThread, QObject, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QCheckBox, QHBoxLayout
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage, QWebEngineProfile
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtGui import QFont

class OptimizedWebEnginePage(QWebEnginePage):
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.last_error_time = 0
        self.error_count = 0
        
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceId):
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            current_time = time.time()
            if current_time - self.last_error_time < 1:
                self.error_count += 1
                if self.error_count > 10:
                    return
            else:
                self.error_count = 0
            self.last_error_time = current_time
            print(f"[WebView Error] {message}")

class PerformanceWebView(QWebEngineView):
    
    load_started = Signal()
    load_finished = Signal(bool)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_performance_settings()
        self.setup_custom_page()
        self.is_active = False
        self.pending_updates = []
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.process_pending_updates)
        self.update_timer.start(100)
        
    def setup_custom_page(self):
        custom_page = OptimizedWebEnginePage(self)
        self.setPage(custom_page)
        
    def setup_performance_settings(self):
        settings = self.settings()
        profile = self.page().profile()
        
        def safe_set_attribute(attr_name, value):
            if hasattr(QWebEngineSettings.WebAttribute, attr_name):
                attr = getattr(QWebEngineSettings.WebAttribute, attr_name)
                settings.setAttribute(attr, value)
        
        safe_set_attribute('JavascriptEnabled', True)
        safe_set_attribute('LocalStorageEnabled', False)
        safe_set_attribute('PluginsEnabled', False)
        safe_set_attribute('JavascriptCanOpenWindows', False)
        safe_set_attribute('JavascriptCanAccessClipboard', False)
        safe_set_attribute('LocalContentCanAccessFileUrls', False)
        safe_set_attribute('XSSAuditingEnabled', True)
        safe_set_attribute('SpatialNavigationEnabled', False)
        safe_set_attribute('FocusOnNavigationEnabled', False)
        safe_set_attribute('AllowGeolocationOnInsecureOrigins', False)
        safe_set_attribute('WebGLEnabled', True)
        safe_set_attribute('Accelerated2dCanvasEnabled', True)
        safe_set_attribute('PdfViewerEnabled', False)
        safe_set_attribute('ShowScrollBars', True)
        
        profile.setHttpCacheMaximumSize(50 * 1024 * 1024)
        
    def set_hardware_acceleration(self, enabled):
        settings = self.settings()
        
        def safe_set_attribute(attr_name, value):
            if hasattr(QWebEngineSettings.WebAttribute, attr_name):
                attr = getattr(QWebEngineSettings.WebAttribute, attr_name)
                settings.setAttribute(attr, value)
        
        safe_set_attribute('WebGLEnabled', enabled)
        safe_set_attribute('Accelerated2dCanvasEnabled', enabled)
        
    def inject_performance_css(self):
        css = """
        * {
            animation-duration: 0.1s !important;
            transition-duration: 0.1s !important;
        }
        
        .heavy-shadow, .complex-gradient {
            box-shadow: none !important;
            background: linear-gradient(180deg, rgba(0,0,0,0.1) 0%, rgba(0,0,0,0.2) 100%) !important;
        }
        
        .backdrop-blur {
            backdrop-filter: none !important;
        }
        
        .particles, .particle-container {
            display: none !important;
        }
        
        .gpu-accelerated {
            transform: translateZ(0);
            will-change: transform;
        }
        """
        
        js_code = f"""
        (function() {{
            var style = document.createElement('style');
            style.textContent = `{css}`;
            document.head.appendChild(style);
        }})();
        """
        self.page().runJavaScript(js_code)
        
    def inject_performance_javascript(self):
        js_code = """
        (function() {
            let scrolling = false;
            window.addEventListener('scroll', function() {
                if (!scrolling) {
                    window.requestAnimationFrame(function() {
                        scrolling = false;
                    });
                    scrolling = true;
                }
            }, { passive: true });
            
            const originalRAF = window.requestAnimationFrame;
            let skipFrame = false;
            window.requestAnimationFrame = function(callback) {
                if (skipFrame) {
                    skipFrame = false;
                    return originalRAF(callback);
                }
                skipFrame = true;
                return setTimeout(callback, 32);
            };
            
            let resizeTimeout;
            window.addEventListener('resize', function(event) {
                clearTimeout(resizeTimeout);
                resizeTimeout = setTimeout(function() {
                }, 250);
            });
            
            if (window.WebGLRenderingContext) {
                const getContext = HTMLCanvasElement.prototype.getContext;
                HTMLCanvasElement.prototype.getContext = function(type, ...args) {
                    if (type === 'webgl' || type === 'webgl2' || type === 'experimental-webgl') {
                        args[0] = args[0] || {};
                        args[0].antialias = false;
                        args[0].depth = false;
                        args[0].powerPreference = 'low-power';
                        args[0].preserveDrawingBuffer = false;
                        args[0].failIfMajorPerformanceCaveat = false;
                    }
                    return getContext.call(this, type, ...args);
                };
            }
            
            if ('IntersectionObserver' in window) {
                const imageObserver = new IntersectionObserver((entries, observer) => {
                    entries.forEach(entry => {
                        if (entry.isIntersecting) {
                            const img = entry.target;
                            if (img.dataset.src) {
                                img.src = img.dataset.src;
                                img.removeAttribute('data-src');
                                observer.unobserve(img);
                            }
                        }
                    });
                });
                
                document.querySelectorAll('img[data-src]').forEach(img => {
                    imageObserver.observe(img);
                });
            }
        })();
        """
        self.page().runJavaScript(js_code)
    
    def loadFinished(self, ok):
        super().loadFinished(ok)
        if ok:
            QTimer.singleShot(1000, self.inject_performance_css)
            QTimer.singleShot(1500, self.inject_performance_javascript)
        self.load_finished.emit(ok)
    
    def queue_update(self, update_data):
        self.pending_updates.append(update_data)
        
    def process_pending_updates(self):
        if not self.pending_updates or not self.is_active:
            return
            
        updates_to_process = self.pending_updates[:5]
        self.pending_updates = self.pending_updates[5:]
        
        for update in updates_to_process:
            self.apply_update(update)
            
    def apply_update(self, update_data):
        try:
            js_code = f"""
            if (window.updateMatchLoadout) {{
                window.updateMatchLoadout({json.dumps(update_data)});
            }}
            """
            self.page().runJavaScript(js_code)
        except Exception as e:
            print(f"Error applying update: {e}")
    
    def set_active(self, active):
        self.is_active = active
        if hasattr(self.page(), 'setLifecycleState'):
            try:
                if not active:
                    self.page().setLifecycleState(QWebEnginePage.LifecycleState.Frozen)
                else:
                    self.page().setLifecycleState(QWebEnginePage.LifecycleState.Active)
            except AttributeError:
                pass

class MatchLoadoutsContainer(QWidget):
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.web_view = None
        self.performance_mode = False
        self.init_ui()
        
    def init_ui(self):
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        control_panel = QWidget()
        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(10, 5, 10, 5)
        
        self.perf_checkbox = QCheckBox("Performance Mode")
        self.perf_checkbox.setToolTip("Reduces visual effects for better performance")
        self.perf_checkbox.toggled.connect(self.toggle_performance_mode)
        control_layout.addWidget(self.perf_checkbox)
        
        self.reload_btn = QPushButton("Reload")
        self.reload_btn.setMaximumWidth(80)
        self.reload_btn.clicked.connect(self.reload_view)
        control_layout.addWidget(self.reload_btn)
        
        control_layout.addStretch()
        
        self.status_label = QLabel("Status: Loading...")
        control_layout.addWidget(self.status_label)
        
        control_panel.setLayout(control_layout)
        self.layout.addWidget(control_panel)
        
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        
        self.layout.addWidget(self.content_widget, 1)
        self.setLayout(self.layout)
        
        self.show_web_view()
        
    def show_web_view(self):
        if not self.web_view:
            try:
                self.web_view = PerformanceWebView()
                self.web_view.load(QUrl("https://vry-ui.netlify.app/matchLoadouts"))
                self.web_view.load_finished.connect(self.on_load_finished)
                self.content_layout.addWidget(self.web_view)
            except Exception as e:
                print(f"Error creating web view: {e}")
                self.status_label.setText("Status: Failed to load web view")
                return
        
        self.web_view.set_active(True)
        self.status_label.setText("Status: Web View Active")
        
    def toggle_performance_mode(self, checked):
        self.performance_mode = checked
        if self.web_view:
            self.web_view.set_hardware_acceleration(not checked)
            if checked:
                self.web_view.inject_performance_css()
                self.web_view.inject_performance_javascript()
            self.status_label.setText(f"Status: Performance Mode {'ON' if checked else 'OFF'}")
            
    def reload_view(self):
        if self.web_view:
            self.web_view.reload()
            self.status_label.setText("Status: Reloading...")
            
    def on_load_finished(self, ok):
        if ok:
            self.status_label.setText("Status: Loaded Successfully")
            if self.performance_mode and self.web_view:
                QTimer.singleShot(1000, self.web_view.inject_performance_css)
                QTimer.singleShot(1500, self.web_view.inject_performance_javascript)
        else:
            self.status_label.setText("Status: Load Failed")
            
    def update_data(self, data):
        if self.web_view:
            self.web_view.queue_update(data)
            
    def cleanup(self):
        try:
            if self.web_view:
                self.web_view.stop()
                self.web_view.deleteLater()
                self.web_view = None
        except Exception as e:
            print(f"Error during cleanup: {e}")