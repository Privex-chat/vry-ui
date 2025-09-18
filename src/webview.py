"""
Optimized for PySide6's WebEngine
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
        """Suppress console messages to reduce overhead"""
        # Only log critical errors
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            current_time = time.time()
            if current_time - self.last_error_time < 1:  # Throttle error logging
                self.error_count += 1
                if self.error_count > 10:  # Too many errors, might be causing issues
                    return
            else:
                self.error_count = 0
            self.last_error_time = current_time
            print(f"[WebView Error] {message}")

class PerformanceWebView(QWebEngineView):
    
    load_started = Signal()
    load_finished = Signal(bool)
    resource_warning = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_performance_settings()
        self.setup_custom_page()
        self.is_active = False
        self.pending_updates = []
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.process_pending_updates)
        self.update_timer.start(100)  # Process updates every 100ms
        
    def setup_custom_page(self):
        """Use custom page with error handling"""
        custom_page = OptimizedWebEnginePage(self)
        self.setPage(custom_page)
        
    def setup_performance_settings(self):
        """Configure WebEngine settings for better performance"""
        settings = self.settings()
        profile = self.page().profile()
        
        # Performance optimizations for PySide6
        def safe_set_attribute(attr_name, value):
            """Safely set an attribute if it exists"""
            if hasattr(QWebEngineSettings.WebAttribute, attr_name):
                attr = getattr(QWebEngineSettings.WebAttribute, attr_name)
                settings.setAttribute(attr, value)
        
        # Core settings (these should exist in PySide6)
        safe_set_attribute('JavascriptEnabled', True)
        safe_set_attribute('LocalStorageEnabled', False)  # Disable if not needed
        safe_set_attribute('PluginsEnabled', False)
        safe_set_attribute('JavascriptCanOpenWindows', False)
        safe_set_attribute('JavascriptCanAccessClipboard', False)
        safe_set_attribute('LocalContentCanAccessFileUrls', False)
        safe_set_attribute('XSSAuditingEnabled', True)
        safe_set_attribute('SpatialNavigationEnabled', False)
        
        # Settings that might vary between versions
        safe_set_attribute('FocusOnNavigationEnabled', False)
        safe_set_attribute('AllowGeolocationOnInsecureOrigins', False)
        
        # Enable hardware acceleration (can be toggled)
        safe_set_attribute('WebGLEnabled', True)
        safe_set_attribute('Accelerated2dCanvasEnabled', True)
        
        # PySide6 specific optimizations
        safe_set_attribute('PdfViewerEnabled', False)
        safe_set_attribute('ShowScrollBars', True)
        
        # Set cache and memory limits for better performance
        profile.setHttpCacheMaximumSize(50 * 1024 * 1024)  # 50MB cache
        
    def set_hardware_acceleration(self, enabled):
        """Toggle hardware acceleration"""
        settings = self.settings()
        
        def safe_set_attribute(attr_name, value):
            """Safely set an attribute if it exists"""
            if hasattr(QWebEngineSettings.WebAttribute, attr_name):
                attr = getattr(QWebEngineSettings.WebAttribute, attr_name)
                settings.setAttribute(attr, value)
        
        safe_set_attribute('WebGLEnabled', enabled)
        safe_set_attribute('Accelerated2dCanvasEnabled', enabled)
        
    def inject_performance_css(self):
        """Inject CSS to reduce visual complexity"""
        css = """
        /* Reduce animation complexity */
        * {
            animation-duration: 0.1s !important;
            transition-duration: 0.1s !important;
        }
        
        /* Disable complex shadows and effects */
        .heavy-shadow, .complex-gradient {
            box-shadow: none !important;
            background: linear-gradient(180deg, rgba(0,0,0,0.1) 0%, rgba(0,0,0,0.2) 100%) !important;
        }
        
        /* Simplify blur effects */
        .backdrop-blur {
            backdrop-filter: none !important;
        }
        
        /* Reduce particle effects if any */
        .particles, .particle-container {
            display: none !important;
        }
        
        /* Force GPU acceleration for transforms */
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
        """Inject JavaScript to optimize performance"""
        js_code = """
        (function() {
            // Throttle scroll events
            let scrolling = false;
            window.addEventListener('scroll', function() {
                if (!scrolling) {
                    window.requestAnimationFrame(function() {
                        scrolling = false;
                    });
                    scrolling = true;
                }
            }, { passive: true });
            
            // Reduce animation frame rate for non-critical animations
            const originalRAF = window.requestAnimationFrame;
            let skipFrame = false;
            window.requestAnimationFrame = function(callback) {
                if (skipFrame) {
                    skipFrame = false;
                    return originalRAF(callback);
                }
                skipFrame = true;
                return setTimeout(callback, 32); // ~30fps instead of 60fps
            };
            
            // Debounce resize events
            let resizeTimeout;
            window.addEventListener('resize', function(event) {
                clearTimeout(resizeTimeout);
                resizeTimeout = setTimeout(function() {
                    // Handle resize
                }, 250);
            });
            
            // Optimize WebGL if present
            if (window.WebGLRenderingContext) {
                const getContext = HTMLCanvasElement.prototype.getContext;
                HTMLCanvasElement.prototype.getContext = function(type, ...args) {
                    if (type === 'webgl' || type === 'webgl2' || type === 'experimental-webgl') {
                        args[0] = args[0] || {};
                        args[0].antialias = false; // Disable antialiasing
                        args[0].depth = false; // Disable depth buffer if not needed
                        args[0].powerPreference = 'low-power'; // Use low-power GPU
                        args[0].preserveDrawingBuffer = false; // Don't preserve buffer
                        args[0].failIfMajorPerformanceCaveat = false;
                    }
                    return getContext.call(this, type, ...args);
                };
            }
            
            // Lazy load images if any
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
        """Handle load completion"""
        super().loadFinished(ok)
        if ok:
            # Inject performance optimizations after page loads
            QTimer.singleShot(1000, self.inject_performance_css)
            QTimer.singleShot(1500, self.inject_performance_javascript)
        self.load_finished.emit(ok)
    
    def queue_update(self, update_data):
        """Queue updates instead of applying immediately"""
        self.pending_updates.append(update_data)
        
    def process_pending_updates(self):
        """Process pending updates in batch"""
        if not self.pending_updates or not self.is_active:
            return
            
        # Process maximum 5 updates at once to avoid overwhelming
        updates_to_process = self.pending_updates[:5]
        self.pending_updates = self.pending_updates[5:]
        
        for update in updates_to_process:
            self.apply_update(update)
            
    def apply_update(self, update_data):
        """Apply update to the web view"""
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
        """Set whether this view is active/visible"""
        self.is_active = active
        # PySide6 has better lifecycle management
        if hasattr(self.page(), 'setLifecycleState'):
            try:
                if not active:
                    # Pause JavaScript execution when not visible
                    self.page().setLifecycleState(QWebEnginePage.LifecycleState.Frozen)
                else:
                    self.page().setLifecycleState(QWebEnginePage.LifecycleState.Active)
            except AttributeError:
                # Lifecycle state might not be available in all PySide6 versions
                pass

class LightweightLoadoutView(QWidget):
    """Lightweight alternative view for match loadouts"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Header
        header = QLabel("Match Loadouts - Lightweight Mode")
        header.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        layout.addWidget(header)
        
        # Info label
        self.info_label = QLabel("Lightweight view active - Lower resource usage")
        layout.addWidget(self.info_label)
        
        # Placeholder for simplified loadout display
        self.loadout_display = QLabel("Loadout data will appear here...")
        self.loadout_display.setWordWrap(True)
        layout.addWidget(self.loadout_display)
        
        layout.addStretch()
        self.setLayout(layout)
        
    def update_loadouts(self, data):
        """Update the lightweight display with loadout data"""
        try:
            # Simple text representation of loadouts
            display_text = "Current Loadouts:\n\n"
            players = data.get("Players", {})
            for player_id, player_data in players.items():
                name = player_data.get("Name", "Unknown")
                agent = player_data.get("Agent", "Unknown")
                display_text += f"• {name} - {agent}\n"
                
            self.loadout_display.setText(display_text)
        except Exception as e:
            self.loadout_display.setText(f"Error displaying loadouts: {str(e)}")

class MatchLoadoutsContainer(QWidget):
    """Container widget that can switch between web and lightweight views"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.web_view = None
        self.lightweight_view = None
        self.current_view = "web"
        self.performance_mode = False
        self.init_ui()
        
    def init_ui(self):
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # Control panel
        control_panel = QWidget()
        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(10, 5, 10, 5)
        
        # Performance mode toggle
        self.perf_checkbox = QCheckBox("Performance Mode")
        self.perf_checkbox.setToolTip("Reduces visual effects for better performance")
        self.perf_checkbox.toggled.connect(self.toggle_performance_mode)
        control_layout.addWidget(self.perf_checkbox)
        
        # Reload button
        self.reload_btn = QPushButton("Reload")
        self.reload_btn.setMaximumWidth(80)
        self.reload_btn.clicked.connect(self.reload_view)
        control_layout.addWidget(self.reload_btn)
        
        control_layout.addStretch()
        
        # Status label
        self.status_label = QLabel("Status: Loading...")
        control_layout.addWidget(self.status_label)
        
        control_panel.setLayout(control_layout)
        self.layout.addWidget(control_panel)
        
        # Content area
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        
        self.layout.addWidget(self.content_widget, 1)
        self.setLayout(self.layout)
        
        # Start with web view
        self.show_web_view()
        
    def show_web_view(self):
        """Show the web view"""
        if self.lightweight_view:
            self.lightweight_view.hide()
            
        if not self.web_view:
            try:
                self.web_view = PerformanceWebView()
                self.web_view.load(QUrl("https://vry-ui.netlify.app/matchLoadouts"))
                self.web_view.load_finished.connect(self.on_load_finished)
                self.content_layout.addWidget(self.web_view)
            except Exception as e:
                print(f"Error creating web view: {e}")
                # Fall back to lightweight view
                self.show_lightweight_view()
                return
        else:
            self.web_view.show()
            
        self.web_view.set_active(True)
        self.current_view = "web"
        self.status_label.setText("Status: Web View Active")
        
    def show_lightweight_view(self):
        """Show the lightweight view"""
        if self.web_view:
            self.web_view.hide()
            self.web_view.set_active(False)
            
        if not self.lightweight_view:
            self.lightweight_view = LightweightLoadoutView()
            self.content_layout.addWidget(self.lightweight_view)
        else:
            self.lightweight_view.show()
            
        self.current_view = "lightweight"
        self.status_label.setText("Status: Lightweight View Active")
        
    def toggle_performance_mode(self, checked):
        """Toggle performance optimizations"""
        self.performance_mode = checked
        if self.web_view:
            self.web_view.set_hardware_acceleration(not checked)
            if checked:
                self.web_view.inject_performance_css()
                self.web_view.inject_performance_javascript()
            self.status_label.setText(f"Status: Performance Mode {'ON' if checked else 'OFF'}")
            
    def reload_view(self):
        """Reload the current view"""
        if self.current_view == "web" and self.web_view:
            self.web_view.reload()
            self.status_label.setText("Status: Reloading...")
        elif self.current_view == "lightweight" and self.lightweight_view:
            self.lightweight_view.update_loadouts({})
            
    def on_load_finished(self, ok):
        """Handle load completion"""
        if ok:
            self.status_label.setText("Status: Loaded Successfully")
            if self.performance_mode and self.web_view:
                QTimer.singleShot(1000, self.web_view.inject_performance_css)
                QTimer.singleShot(1500, self.web_view.inject_performance_javascript)
        else:
            self.status_label.setText("Status: Load Failed")
            
    def update_data(self, data):
        """Update the view with new data"""
        if self.current_view == "web" and self.web_view:
            self.web_view.queue_update(data)
        elif self.current_view == "lightweight" and self.lightweight_view:
            self.lightweight_view.update_loadouts(data)
            
    def cleanup(self):
        """Clean up resources"""
        try:
            if self.web_view:
                self.web_view.stop()
                self.web_view.deleteLater()
                self.web_view = None
        except Exception as e:
            print(f"Error during cleanup: {e}")