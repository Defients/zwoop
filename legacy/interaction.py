"""
Kovrycha - Desktop Slime Assistant (Enhanced)
Interaction Module

This module handles system-level integration and detection,
monitoring user activity and system events to drive Kovrycha's behavior.
"""

import os
import time
import logging
import threading
import ctypes
import math
import random
from typing import Dict, Any, Callable, Optional, List, Tuple, Union

import win32api
import win32con
import win32gui
import win32process
import win32ts
import win32security
import pythoncom
import win32com.client
from ctypes import windll, Structure, c_long, c_int, byref, sizeof


class POINT(Structure):
    """Win32 POINT structure."""
    _fields_ = [("x", c_long), ("y", c_long)]


class LASTINPUTINFO(Structure):
    """Win32 LASTINPUTINFO structure for idle detection."""
    _fields_ = [
        ('cbSize', c_int),
        ('dwTime', c_long),
    ]


class SystemMonitor:
    """
    Enhanced system monitor for detecting user activity and system events
    to inform Kovrycha's behavior with sophisticated awareness.
    """
    
    # Idle time threshold in seconds
    IDLE_THRESHOLD = 30
    
    def __init__(self, callback: Callable[[str, Dict[str, Any]], None], events=None):
        self.logger = logging.getLogger("Kovrycha.Interaction")
        self.callback = callback
        self.events = events
        
        # State tracking
        self.running = True
        self.last_active_window = None
        self.is_idle = False
        self.last_cursor_pos = (0, 0)
        self.cursor_speed = 0
        self.cursor_history = []  # Track cursor positions for pattern detection
        self.cursor_history_max = 20
        self.idle_time = 0
        self.activity_level = 0.0  # 0.0 = idle, 1.0 = very active
        self.last_activity_check = time.time()
        
        # Advanced activity tracking
        self.key_presses = 0
        self.mouse_clicks = 0
        self.mouse_movement = 0
        self.last_input_time = time.time()
        self.active_duration = 0
        self.idle_duration = 0
        self.activity_samples = []  # Recent activity samples for trend analysis
        self.max_samples = 20
        
        # Session awareness
        self.session_start_time = time.time()
        self.last_lock_status = False
        self.screen_saver_active = False
        
        # Pattern recognition state
        self.recognized_patterns = {
            "circular_motion": False,
            "rapid_clicking": False,
            "directional_movement": None,  # "left", "right", "up", "down"
            "zigzag": False
        }
        
        # Initialize COM for the shell windows API
        try:
            pythoncom.CoInitialize()
        except Exception as e:
            self.logger.warning(f"Failed to initialize COM: {e}")
        
        # Set up monitoring threads
        self.threads = {}
        self._create_monitoring_threads()
        
        self.logger.info("Enhanced System monitor initialized")
    
    def _create_monitoring_threads(self):
        """Create all monitoring threads with error handling."""
        self.threads["window"] = threading.Thread(
            target=self._thread_wrapper,
            args=(self._monitor_windows, "window"),
            daemon=True,
            name="WindowMonitorThread"
        )
        
        self.threads["activity"] = threading.Thread(
            target=self._thread_wrapper,
            args=(self._monitor_activity, "activity"),
            daemon=True,
            name="ActivityMonitorThread"
        )
        
        self.threads["cursor"] = threading.Thread(
            target=self._thread_wrapper,
            args=(self._monitor_cursor, "cursor"),
            daemon=True,
            name="CursorMonitorThread"
        )
        
        self.threads["session"] = threading.Thread(
            target=self._thread_wrapper,
            args=(self._monitor_session, "session"),
            daemon=True,
            name="SessionMonitorThread"
        )
        
        # Start all threads
        for name, thread in self.threads.items():
            thread.start()
            self.logger.debug(f"Started {name} monitoring thread")
    
    def _thread_wrapper(self, target_func, thread_name):
        """Wrapper for threads to handle exceptions."""
        self.logger.debug(f"Initializing {thread_name} monitor thread")
        try:
            target_func()
        except Exception as e:
            self.logger.error(f"Error in {thread_name} monitor thread: {e}", exc_info=True)
            if self.events:
                self.events.emit("app_error", {
                    "thread": f"monitor_{thread_name}",
                    "error": str(e)
                })
        finally:
            self.logger.debug(f"{thread_name.capitalize()} monitor thread stopped")
    
    def _monitor_windows(self):
        """Monitor active window changes with enhanced detection."""
        self.logger.info("Window monitoring thread started")
        
        last_check_time = 0
        check_interval = 0.25  # Check every 250ms
        
        try:
            while self.running:
                current_time = time.time()
                
                # Limit checking frequency to reduce CPU usage
                if current_time - last_check_time < check_interval:
                    time.sleep(0.05)
                    continue
                    
                last_check_time = current_time
                
                # Get foreground window
                hwnd = win32gui.GetForegroundWindow()
                
                if hwnd != 0 and hwnd != self.last_active_window:
                    try:
                        # Get window info
                        window_info = self._get_window_info(hwnd)
                        
                        if window_info:
                            # Notify callback
                            self.callback("application_change", window_info)
                            
                            # Store for tracking
                            self.last_active_window = hwnd
                            
                            # Emit event
                            if self.events:
                                self.events.emit("window_change", window_info)
                            
                            self.logger.debug(f"Active window changed: {window_info.get('title', 'Unknown')}")
                    except Exception as e:
                        self.logger.warning(f"Error getting window info: {e}")
                
                # Check for full-screen applications
                if hwnd != 0:
                    try:
                        # Get monitor info
                        monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
                        monitor_info = win32api.GetMonitorInfo(monitor)
                        
                        # Get window rect
                        window_rect = win32gui.GetWindowRect(hwnd)
                        
                        # Check if window covers the entire monitor
                        monitor_rect = monitor_info.get("Monitor")
                        is_fullscreen = (
                            window_rect[0] <= monitor_rect[0] and
                            window_rect[1] <= monitor_rect[1] and
                            window_rect[2] >= monitor_rect[2] and
                            window_rect[3] >= monitor_rect[3]
                        )
                        
                        # Notify if fullscreen status changed
                        if is_fullscreen != getattr(self, "last_fullscreen", False):
                            self.last_fullscreen = is_fullscreen
                            
                            if self.events:
                                self.events.emit("fullscreen_change", {"fullscreen": is_fullscreen})
                            
                            self.logger.debug(f"Fullscreen status changed: {is_fullscreen}")
                    except Exception as e:
                        self.logger.warning(f"Error checking fullscreen: {e}")
                
                # Sleep to reduce CPU usage
                time.sleep(check_interval)
                
        except Exception as e:
            self.logger.error(f"Error in window monitoring thread: {e}", exc_info=True)
        
        self.logger.info("Window monitoring thread stopped")
    
    def _get_window_info(self, hwnd: int) -> Optional[Dict[str, Any]]:
        """Get detailed information about a window."""
        if not hwnd or not win32gui.IsWindow(hwnd):
            return None
            
        try:
            # Get window title
            title = win32gui.GetWindowText(hwnd)
            
            # Skip certain system windows or empty titles
            if not title or title in ["Program Manager", "Windows Shell Experience Host"]:
                return None
            
            # Get window rect
            rect = win32gui.GetWindowRect(hwnd)
            left, top, right, bottom = rect
            
            # Skip zero-sized windows
            if left == right or top == bottom:
                return None
            
            # Get window class
            class_name = win32gui.GetClassName(hwnd)
            
            # Get process information
            thread_id, process_id = win32process.GetWindowThreadProcessId(hwnd)
            
            # Get process name (try to get executable path)
            process_name = "Unknown"
            try:
                # Open the process to get executable path
                process_handle = win32api.OpenProcess(
                    win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ,
                    False, process_id
                )
                
                if process_handle:
                    # Get executable path
                    process_path = win32process.GetModuleFileNameEx(process_handle, 0)
                    process_name = os.path.basename(process_path)
                    win32api.CloseHandle(process_handle)
            except Exception:
                # Fallback to just PID if we can't get the name
                process_name = f"PID-{process_id}"
            
            # Check if the window is visible and not minimized
            is_visible = win32gui.IsWindowVisible(hwnd)
            is_iconic = win32gui.IsIconic(hwnd)
            is_enabled = win32gui.IsWindowEnabled(hwnd)
            
            # Create detailed window info
            window_info = {
                "hwnd": hwnd,
                "title": title,
                "class_name": class_name,
                "process_id": process_id,
                "process_name": process_name,
                "thread_id": thread_id,
                "window_rect": {
                    "left": left,
                    "top": top,
                    "right": right,
                    "bottom": bottom,
                    "width": right - left,
                    "height": bottom - top
                },
                "is_visible": is_visible,
                "is_minimized": is_iconic,
                "is_enabled": is_enabled
            }
            
            return window_info
            
        except Exception as e:
            self.logger.warning(f"Error getting window info: {e}")
            return None
    
    def _monitor_activity(self):
        """Monitor user activity with enhanced detection and pattern recognition."""
        self.logger.info("Activity monitoring thread started")
        
        # Initialize LASTINPUTINFO structure for idle detection
        last_input_info = LASTINPUTINFO()
        last_input_info.cbSize = sizeof(LASTINPUTINFO)
        
        # Tracking state
        last_input_check = 0
        input_check_interval = 0.5  # Check every 500ms
        activity_update_interval = 2.0  # Update activity level every 2 seconds
        last_activity_update = 0
        
        try:
            while self.running:
                current_time = time.time()
                
                # Check for user input at regular intervals
                if current_time - last_input_check >= input_check_interval:
                    last_input_check = current_time
                    
                    # Query last input time from Windows
                    if windll.user32.GetLastInputInfo(byref(last_input_info)):
                        last_input_tick = last_input_info.dwTime
                        current_tick = windll.kernel32.GetTickCount()
                        
                        # Calculate idle time in seconds
                        idle_time = (current_tick - last_input_tick) / 1000.0
                        
                        # Update idle state if it changed
                        new_idle = idle_time >= self.IDLE_THRESHOLD
                        
                        if new_idle != self.is_idle:
                            self.is_idle = new_idle
                            
                            # Update idle/active duration
                            if new_idle:
                                self.idle_duration = 0
                                self.logger.debug("User is now idle")
                            else:
                                self.active_duration = 0
                                self.logger.debug("User is now active")
                            
                            # Emit event
                            self.callback("idle_state_change", {"idle": new_idle})
                            
                            if self.events:
                                self.events.emit("idle_state_change", {"idle": new_idle})
                        
                        # Update duration counters
                        if self.is_idle:
                            self.idle_duration += input_check_interval
                        else:
                            self.active_duration += input_check_interval
                
                # Update activity level at regular intervals
                if current_time - last_activity_update >= activity_update_interval:
                    last_activity_update = current_time
                    
                    # Calculate activity metrics
                    cursor_speed = getattr(self, "cursor_speed", 0)
                    mouse_clicks = getattr(self, "mouse_clicks", 0)
                    
                    # Combine metrics for overall activity level
                    raw_activity = min(1.0, (
                        # Normalize and weight metrics
                        (1.0 - min(1.0, idle_time / self.IDLE_THRESHOLD)) * 0.5 +  # Idle time (50%)
                        min(1.0, cursor_speed / 500) * 0.3 +                        # Cursor speed (30%)
                        min(1.0, mouse_clicks / 10) * 0.2                          # Click frequency (20%)
                    ))
                    
                    # Smooth activity level changes
                    self.activity_level += (raw_activity - self.activity_level) * 0.3
                    
                    # Store sample for trend analysis
                    self.activity_samples.append(self.activity_level)
                    if len(self.activity_samples) > self.max_samples:
                        self.activity_samples.pop(0)
                    
                    # Reset counters
                    self.mouse_clicks = 0
                    
                    # Emit activity level update
                    if self.events:
                        self.events.emit("activity_level", {
                            "level": self.activity_level,
                            "idle_time": idle_time,
                            "idle": self.is_idle
                        })
                    
                    # Analyze activity patterns
                    self._analyze_activity_patterns()
                
                # Sleep to reduce CPU usage
                time.sleep(0.1)
                
        except Exception as e:
            self.logger.error(f"Error in activity monitoring thread: {e}", exc_info=True)
        
        self.logger.info("Activity monitoring thread stopped")
    
    def _analyze_activity_patterns(self):
        """Analyze activity patterns to detect user behavior trends."""
        # Need enough samples for analysis
        if len(self.activity_samples) < 5:
            return
            
        try:
            # Check for activity trend
            rising = all(self.activity_samples[i] <= self.activity_samples[i+1] 
                         for i in range(len(self.activity_samples)-3, len(self.activity_samples)-1))
            
            falling = all(self.activity_samples[i] >= self.activity_samples[i+1] 
                         for i in range(len(self.activity_samples)-3, len(self.activity_samples)-1))
            
            steady = not rising and not falling
            
            if rising and self.activity_level > 0.7:
                # User is becoming very active
                if self.events:
                    self.events.emit("activity_pattern", {
                        "pattern": "increasing_activity",
                        "level": self.activity_level
                    })
                
            elif falling and self.activity_level < 0.3:
                # User is becoming inactive
                if self.events:
                    self.events.emit("activity_pattern", {
                        "pattern": "decreasing_activity",
                        "level": self.activity_level
                    })
            
            # Detect work patterns
            if steady and self.activity_level > 0.6 and self.active_duration > 300:
                # User has been actively working for 5+ minutes
                if self.events:
                    self.events.emit("activity_pattern", {
                        "pattern": "sustained_work",
                        "duration": self.active_duration
                    })
                    
        except Exception as e:
            self.logger.warning(f"Error analyzing activity patterns: {e}")
    
    def _monitor_cursor(self):
        """Monitor cursor position and movement with pattern detection."""
        self.logger.info("Cursor monitoring thread started")
        
        last_pos = (0, 0)
        last_check_time = time.time()
        check_interval = 0.05  # 50ms for responsive cursor tracking
        
        # Detect click events
        try:
            windll.user32.GetAsyncKeyState.restype = c_int
        except Exception as e:
            self.logger.warning(f"Could not set GetAsyncKeyState return type: {e}")
        
        try:
            while self.running:
                current_time = time.time()
                
                # Limit checking frequency
                if current_time - last_check_time < check_interval:
                    time.sleep(0.01)
                    continue
                
                dt = current_time - last_check_time
                last_check_time = current_time
                
                # Get current cursor position
                point = POINT()
                if windll.user32.GetCursorPos(byref(point)):
                    current_pos = (point.x, point.y)
                else:
                    # GetCursorPos failed, use last position
                    current_pos = last_pos
                
                # Calculate movement since last check
                movement_x = current_pos[0] - last_pos[0]
                movement_y = current_pos[1] - last_pos[1]
                movement = (movement_x**2 + movement_y**2)**0.5
                
                # Update cursor speed (pixels per second)
                if dt > 0:
                    self.cursor_speed = movement / dt
                else:
                    self.cursor_speed = 0
                
                # Track total movement for activity level
                self.mouse_movement += movement
                
                # Update cursor history for pattern detection
                if movement > 0:
                    self.cursor_history.append(current_pos)
                    if len(self.cursor_history) > self.cursor_history_max:
                        self.cursor_history.pop(0)
                    
                    # Detect patterns when we have enough history
                    if len(self.cursor_history) >= 10:
                        self._detect_cursor_patterns()
                
                # Check for mouse clicks
                try:
                    # Left button
                    if windll.user32.GetAsyncKeyState(0x01) & 0x8000:
                        self.mouse_clicks += 1
                        
                        if self.events:
                            self.events.emit("mouse_click", {
                                "button": "left",
                                "position": current_pos
                            })
                    
                    # Right button
                    if windll.user32.GetAsyncKeyState(0x02) & 0x8000:
                        self.mouse_clicks += 1
                        
                        if self.events:
                            self.events.emit("mouse_click", {
                                "button": "right",
                                "position": current_pos
                            })
                except Exception:
                    pass  # Ignore errors in click detection
                
                # Update last position
                self.last_cursor_pos = current_pos
                last_pos = current_pos
                
                # Sleep briefly
                time.sleep(max(0, check_interval - (time.time() - current_time)))
                
        except Exception as e:
            self.logger.error(f"Error in cursor monitoring thread: {e}", exc_info=True)
        
        self.logger.info("Cursor monitoring thread stopped")
    
    def _detect_cursor_patterns(self):
        """Detect cursor movement patterns for advanced responsiveness."""
        try:
            # Need sufficient history
            if len(self.cursor_history) < 10:
                return
                
            # Get recent positions
            positions = self.cursor_history[-10:]
            
            # Detect circular motion
            circular = self._detect_circular_motion(positions)
            if circular and not self.recognized_patterns["circular_motion"]:
                self.recognized_patterns["circular_motion"] = True
                
                if self.events:
                    self.events.emit("cursor_pattern", {"pattern": "circular"})
                    
                self.logger.debug("Detected circular cursor motion")
            elif not circular:
                self.recognized_patterns["circular_motion"] = False
            
            # Detect directional movement
            direction = self._detect_directional_movement(positions)
            if direction and direction != self.recognized_patterns["directional_movement"]:
                self.recognized_patterns["directional_movement"] = direction
                
                if self.events:
                    self.events.emit("cursor_pattern", {"pattern": f"direction_{direction}"})
                    
                self.logger.debug(f"Detected {direction} cursor movement")
            
            # Detect zigzag pattern
            zigzag = self._detect_zigzag(positions)
            if zigzag and not self.recognized_patterns["zigzag"]:
                self.recognized_patterns["zigzag"] = True
                
                if self.events:
                    self.events.emit("cursor_pattern", {"pattern": "zigzag"})
                    
                self.logger.debug("Detected zigzag cursor pattern")
            elif not zigzag:
                self.recognized_patterns["zigzag"] = False
                
        except Exception as e:
            self.logger.warning(f"Error in cursor pattern detection: {e}")
    
    def _detect_circular_motion(self, positions):
        """Detect if the cursor is moving in a circular pattern."""
        # Need at least 8 points for reliable detection
        if len(positions) < 8:
            return False
            
        try:
            # Calculate center as average of positions
            center_x = sum(p[0] for p in positions) / len(positions)
            center_y = sum(p[1] for p in positions) / len(positions)
            
            # Calculate average distance from center
            avg_radius = sum(
                ((p[0] - center_x)**2 + (p[1] - center_y)**2)**0.5
                for p in positions
            ) / len(positions)
            
            # Check if points are roughly equidistant from center
            radius_variation = sum(
                abs(((p[0] - center_x)**2 + (p[1] - center_y)**2)**0.5 - avg_radius)
                for p in positions
            ) / len(positions)
            
            # Calculate angular change
            angles = [math.atan2(p[1] - center_y, p[0] - center_x) for p in positions]
            angle_diffs = [
                (angles[i+1] - angles[i] + math.pi) % (2 * math.pi) - math.pi
                for i in range(len(angles) - 1)
            ]
            
            # Check if angles are consistently changing in one direction
            is_clockwise = sum(1 for d in angle_diffs if d > 0) > len(angle_diffs) / 2
            angle_consistency = sum(1 for d in angle_diffs if (d > 0) == is_clockwise) / len(angle_diffs)
            
            # Circular motion criteria
            is_circular = (
                radius_variation / avg_radius < 0.3 and  # Points follow a roughly circular path
                angle_consistency > 0.7 and             # Angular motion is consistent
                sum(abs(d) for d in angle_diffs) > 3.0   # Sufficient angular movement
            )
            
            return is_circular
            
        except Exception:
            return False
    
    def _detect_directional_movement(self, positions):
        """Detect if the cursor is moving consistently in one direction."""
        # Need at least 5 points
        if len(positions) < 5:
            return None
            
        try:
            # Calculate movement in x and y directions
            x_movement = positions[-1][0] - positions[0][0]
            y_movement = positions[-1][1] - positions[0][1]
            
            # Calculate total distance moved
            total_movement = (x_movement**2 + y_movement**2)**0.5
            
            # Must have moved a minimum distance
            if total_movement < 100:
                return None
                
            # Calculate directional ratios
            x_ratio = abs(x_movement) / total_movement if total_movement > 0 else 0
            y_ratio = abs(y_movement) / total_movement if total_movement > 0 else 0
            
            # Determine primary direction
            if x_ratio > 0.7 and abs(x_movement) > 100:
                return "right" if x_movement > 0 else "left"
            elif y_ratio > 0.7 and abs(y_movement) > 100:
                return "down" if y_movement > 0 else "up"
            else:
                return None
                
        except Exception:
            return None
    
    def _detect_zigzag(self, positions):
        """Detect if the cursor is moving in a zigzag pattern."""
        # Need at least 6 points
        if len(positions) < 6:
            return False
            
        try:
            # Look for alternating direction changes on one axis
            x_directions = [positions[i+1][0] - positions[i][0] for i in range(len(positions) - 1)]
            y_directions = [positions[i+1][1] - positions[i][1] for i in range(len(positions) - 1)]
            
            # Count direction changes
            x_changes = sum(1 for i in range(len(x_directions) - 1) 
                           if (x_directions[i] > 0) != (x_directions[i+1] > 0))
            
            y_changes = sum(1 for i in range(len(y_directions) - 1) 
                           if (y_directions[i] > 0) != (y_directions[i+1] > 0))
            
            # Zigzag has frequent direction changes on one axis
            return x_changes >= 3 or y_changes >= 3
            
        except Exception:
            return False
    
    def _monitor_session(self):
        """Monitor system session state like lock, logon, screensaver."""
        self.logger.info("Session monitoring thread started")
        
        last_check_time = 0
        check_interval = 1.0  # Check every second
        
        try:
            while self.running:
                current_time = time.time()
                
                # Limit checking frequency
                if current_time - last_check_time < check_interval:
                    time.sleep(0.1)
                    continue
                    
                last_check_time = current_time
                
                try:
                    # Check if screen is locked
                    session_id = win32ts.WTSGetActiveConsoleSessionId()
                    is_locked = False
                    
                    try:
                        session_info = win32ts.WTSQuerySessionInformation(
                            win32ts.WTS_CURRENT_SERVER_HANDLE,
                            session_id,
                            win32ts.WTSSessionInfoEx
                        )
                        is_locked = session_info.get("IsLocked", False)
                    except Exception:
                        # Fallback method: check specific windows
                        lock_hwnd = win32gui.FindWindow("LockScreenApp", None)
                        is_locked = lock_hwnd != 0
                    
                    # Notify on lock state change
                    if is_locked != self.last_lock_status:
                        self.last_lock_status = is_locked
                        
                        if self.events:
                            self.events.emit("lock_state_change", {"locked": is_locked})
                            
                        self.logger.debug(f"Screen lock state changed: {is_locked}")
                    
                    # Check if screen saver is active
                    saver_running = windll.user32.GetSystemMetrics(win32con.SM_SAVERRUNNING) != 0
                    
                    if saver_running != self.screen_saver_active:
                        self.screen_saver_active = saver_running
                        
                        if self.events:
                            self.events.emit("screensaver_change", {"active": saver_running})
                            
                        self.logger.debug(f"Screen saver state changed: {saver_running}")
                    
                except Exception as e:
                    self.logger.warning(f"Error checking session state: {e}")
                
                # Sleep to reduce CPU usage
                time.sleep(check_interval)
                
        except Exception as e:
            self.logger.error(f"Error in session monitoring thread: {e}", exc_info=True)
        
        self.logger.info("Session monitoring thread stopped")
    
    def get_activity_level(self) -> float:
        """
        Get the current user activity level.
        
        Returns:
            Activity level from 0.0 (idle) to 1.0 (very active)
        """
        return self.activity_level
    
    def get_activity_trend(self) -> Dict[str, Any]:
        """
        Analyze activity trend over recent history.
        
        Returns:
            Dictionary with trend information
        """
        if len(self.activity_samples) < 3:
            return {"trend": "unknown", "confidence": 0.0}
            
        try:
            # Calculate trend using linear regression
            n = len(self.activity_samples)
            x = list(range(n))
            y = self.activity_samples
            
            # Calculate slope
            x_mean = sum(x) / n
            y_mean = sum(y) / n
            
            numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
            denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
            
            if denominator == 0:
                slope = 0
            else:
                slope = numerator / denominator
            
            # Determine trend direction and confidence
            if abs(slope) < 0.01:
                trend = "stable"
                confidence = 1.0 - min(1.0, abs(slope) * 100)
            elif slope > 0:
                trend = "increasing"
                confidence = min(1.0, slope * 10)
            else:
                trend = "decreasing"
                confidence = min(1.0, abs(slope) * 10)
            
            return {
                "trend": trend,
                "confidence": confidence,
                "slope": slope,
                "current_level": self.activity_level,
                "samples": len(self.activity_samples)
            }
            
        except Exception as e:
            self.logger.warning(f"Error calculating activity trend: {e}")
            return {"trend": "unknown", "confidence": 0.0}
    
    def get_active_window_info(self) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about the currently active window.
        
        Returns:
            Dictionary with window information or None if unavailable
        """
        try:
            hwnd = win32gui.GetForegroundWindow()
            if hwnd != 0:
                return self._get_window_info(hwnd)
        except Exception as e:
            self.logger.warning(f"Error getting active window info: {e}")
            
        return None
    
    def get_all_windows(self) -> List[Dict[str, Any]]:
        """
        Get information about all visible windows.
        
        Returns:
            List of dictionaries with window information
        """
        windows = []
        
        def enum_windows_callback(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                window_info = self._get_window_info(hwnd)
                if window_info:
                    windows.append(window_info)
            return True
        
        try:
            # Enumerate all top-level windows
            win32gui.EnumWindows(enum_windows_callback, None)
        except Exception as e:
            self.logger.warning(f"Error enumerating windows: {e}")
            
        return windows
    
    def is_user_idle(self) -> bool:
        """
        Check if the user is currently idle.
        
        Returns:
            True if the user is idle, False otherwise
        """
        return self.is_idle
    
    def get_cursor_movement(self) -> Tuple[float, Tuple[int, int]]:
        """
        Get the current cursor movement speed and position.
        
        Returns:
            Tuple of (speed, position)
        """
        return (self.cursor_speed, self.last_cursor_pos)
    
    def get_cursor_pattern(self) -> Dict[str, Any]:
        """
        Get information about recognized cursor patterns.
        
        Returns:
            Dictionary with pattern information
        """
        return self.recognized_patterns
    
    def is_screen_locked(self) -> bool:
        """
        Check if the screen is currently locked.
        
        Returns:
            True if screen is locked, False otherwise
        """
        return self.last_lock_status
    
    def is_screensaver_active(self) -> bool:
        """
        Check if the screen saver is currently active.
        
        Returns:
            True if screen saver is active, False otherwise
        """
        return self.screen_saver_active
    
    def cleanup(self):
        """Clean up resources and stop monitoring threads."""
        self.logger.info("Cleaning up system monitor")
        
        self.running = False
        
        # Wait for threads to terminate
        for name, thread in self.threads.items():
            if thread.is_alive():
                thread.join(timeout=1.0)
                if thread.is_alive():
                    self.logger.warning(f"{name} monitor thread did not terminate cleanly")
        
        # Clean up COM
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
        
        self.logger.info("System monitor cleaned up")


class EventSystem:
    """
    Event system for inter-module communication to coordinate behaviors.
    """
    
    def __init__(self):
        self.logger = logging.getLogger("Kovrycha.Events")
        self.handlers = {}
        self.event_history = {}
        self.max_history = 20
    
    def register(self, event_type: str, handler: Callable[[Dict[str, Any]], None]):
        """
        Register a handler for an event type.
        
        Args:
            event_type: Type of event to handle
            handler: Callback function for the event
        """
        if event_type not in self.handlers:
            self.handlers[event_type] = []
            
        if handler not in self.handlers[event_type]:
            self.handlers[event_type].append(handler)
            self.logger.debug(f"Registered handler for {event_type}")
    
    def unregister(self, event_type: str, handler: Callable[[Dict[str, Any]], None]):
        """
        Unregister a handler for an event type.
        
        Args:
            event_type: Type of event to handle
            handler: Callback function to remove
        """
        if event_type in self.handlers and handler in self.handlers[event_type]:
            self.handlers[event_type].remove(handler)
            self.logger.debug(f"Unregistered handler for {event_type}")
    
    def emit(self, event_type: str, data: Dict[str, Any]):
        """
        Emit an event to all registered handlers.
        
        Args:
            event_type: Type of event to emit
            data: Event data
        """
        # Store in history
        if event_type not in self.event_history:
            self.event_history[event_type] = []
            
        self.event_history[event_type].append({
            "time": time.time(),
            "data": data
        })
        
        # Trim history
        if len(self.event_history[event_type]) > self.max_history:
            self.event_history[event_type].pop(0)
        
        # Call handlers
        if event_type in self.handlers:
            for handler in self.handlers[event_type]:
                try:
                    handler(data)
                except Exception as e:
                    self.logger.warning(f"Error in event handler for {event_type}: {e}")
    
    def get_history(self, event_type: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent history for an event type.
        
        Args:
            event_type: Type of event to get history for
            limit: Maximum number of events to return
            
        Returns:
            List of recent events
        """
        if event_type not in self.event_history:
            return []
            
        return self.event_history[event_type][-limit:]
    
    def clear(self):
        """Clear all event handlers and history."""
        self.handlers = {}
        self.event_history = {}
        self.logger.debug("Event system cleared")