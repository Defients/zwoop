"""
Kovrycha - Desktop Slime Assistant
Simplified Utilities Module
"""

import os
import json
import time
import logging
import ctypes
from typing import Dict, List, Tuple, Any, Optional, Callable

import win32api
import win32con
import win32gui
from ctypes import windll, Structure, c_long, byref


class POINT(Structure):
    """Win32 POINT structure."""
    _fields_ = [("x", c_long), ("y", c_long)]


class ScreenManager:
    """
    Manages information about the user's screen setup,
    handling multiple monitors and different DPI settings.
    """
    
    def __init__(self):
        self.logger = logging.getLogger("Kovrycha.ScreenManager")
        self.monitors = []
        self.refresh_monitors()
        self.logger.info(f"Screen manager initialized with {len(self.monitors)} monitors")
    
    def refresh_monitors(self):
        """Refresh the list of connected monitors and their properties."""
        self.monitors = []
        
        try:
            # Initialize monitor enumeration
            monitor_enum = []
            
            # Callback function for EnumDisplayMonitors
            def callback(monitor, dc, rect, data):
                info = win32api.GetMonitorInfo(monitor)
                monitor_enum.append({
                    "handle": monitor,
                    "device": info["Device"],
                    "work_area": info["Work"],
                    "monitor_area": info["Monitor"],
                    "flags": info["Flags"]
                })
                return True
            
            # Enumerate monitors
            win32gui.EnumDisplayMonitors(None, None, callback, 0)
            
            # Process monitor information
            for idx, monitor in enumerate(monitor_enum):
                # Get monitor dimensions
                monitor_rect = monitor["monitor_area"]
                left, top, right, bottom = monitor_rect
                
                # Check if this is the primary monitor
                is_primary = (monitor["flags"] & win32con.MONITORINFOF_PRIMARY) != 0
                
                # Get DPI for this monitor
                dpi_x = ctypes.c_uint()
                dpi_y = ctypes.c_uint()
                
                try:
                    windll.shcore.GetDpiForMonitor(
                        monitor["handle"],
                        0,  # MDT_EFFECTIVE_DPI
                        byref(dpi_x),
                        byref(dpi_y)
                    )
                except:
                    # Fallback for older Windows versions
                    dc = win32gui.GetDC(0)
                    dpi_x.value = win32gui.GetDeviceCaps(dc, win32con.LOGPIXELSX)
                    dpi_y.value = win32gui.GetDeviceCaps(dc, win32con.LOGPIXELSY)
                    win32gui.ReleaseDC(0, dc)
                
                # Add monitor info
                self.monitors.append({
                    "index": idx,
                    "device": monitor["device"],
                    "left": left,
                    "top": top,
                    "right": right,
                    "bottom": bottom,
                    "width": right - left,
                    "height": bottom - top,
                    "work_left": monitor["work_area"][0],
                    "work_top": monitor["work_area"][1],
                    "work_right": monitor["work_area"][2],
                    "work_bottom": monitor["work_area"][3],
                    "work_width": monitor["work_area"][2] - monitor["work_area"][0],
                    "work_height": monitor["work_area"][3] - monitor["work_area"][1],
                    "is_primary": is_primary,
                    "dpi": (dpi_x.value, dpi_y.value)
                })
                
            self.logger.info(f"Refreshed monitor information: {len(self.monitors)} monitors detected")
            
        except Exception as e:
            self.logger.error(f"Error refreshing monitors: {e}", exc_info=True)
            
            # Default fallback if no monitors detected
            if not self.monitors:
                self.monitors.append({
                    "index": 0,
                    "device": "Default",
                    "left": 0,
                    "top": 0,
                    "right": 1920,
                    "bottom": 1080,
                    "width": 1920,
                    "height": 1080,
                    "work_left": 0,
                    "work_top": 0,
                    "work_right": 1920,
                    "work_bottom": 1040,
                    "work_width": 1920,
                    "work_height": 1040,
                    "is_primary": True,
                    "dpi": (96, 96)
                })
    
    def get_monitors(self) -> List[Dict[str, Any]]:
        """
        Get information about all connected monitors.
        
        Returns:
            List of dictionaries with monitor properties
        """
        return self.monitors
    
    def get_primary_monitor(self) -> Dict[str, Any]:
        """
        Get information about the primary monitor.
        
        Returns:
            Dictionary with primary monitor properties
        """
        for monitor in self.monitors:
            if monitor["is_primary"]:
                return monitor
                
        # If no primary monitor found, return the first one
        if self.monitors:
            return self.monitors[0]
            
        # Default fallback
        return {
            "index": 0,
            "device": "Default",
            "left": 0,
            "top": 0,
            "right": 1920,
            "bottom": 1080,
            "width": 1920,
            "height": 1080,
            "work_left": 0,
            "work_top": 0,
            "work_right": 1920,
            "work_bottom": 1040,
            "work_width": 1920,
            "work_height": 1040,
            "is_primary": True,
            "dpi": (96, 96)
        }
    
    def get_primary_size(self) -> Tuple[int, int]:
        """
        Get the size of the primary monitor.
        
        Returns:
            Tuple of (width, height)
        """
        primary = self.get_primary_monitor()
        return (primary["width"], primary["height"])
    
    def get_combined_bounds(self) -> Dict[str, int]:
        """
        Get the combined bounds of all monitors.
        
        Returns:
            Dictionary with left, top, right, bottom coordinates
        """
        if not self.monitors:
            return {"left": 0, "top": 0, "right": 1920, "bottom": 1080}
            
        # Find the extremes of all monitor coordinates
        left = min(monitor["left"] for monitor in self.monitors)
        top = min(monitor["top"] for monitor in self.monitors)
        right = max(monitor["right"] for monitor in self.monitors)
        bottom = max(monitor["bottom"] for monitor in self.monitors)
        
        return {"left": left, "top": top, "right": right, "bottom": bottom}
    
    def point_to_monitor(self, x: int, y: int) -> Optional[Dict[str, Any]]:
        """
        Find which monitor contains the given point.
        
        Args:
            x: X coordinate
            y: Y coordinate
            
        Returns:
            Monitor dictionary or None if point is not on any monitor
        """
        for monitor in self.monitors:
            if (monitor["left"] <= x < monitor["right"] and
                monitor["top"] <= y < monitor["bottom"]):
                return monitor
                
        return None
    
    def get_cursor_position(self) -> Tuple[int, int]:
        """
        Get the current cursor position.
        
        Returns:
            Tuple of (x, y) coordinates
        """
        point = POINT()
        windll.user32.GetCursorPos(byref(point))
        return (point.x, point.y)


class PerformanceTracker:
    """
    Tracks and manages performance metrics for Kovrycha.
    """
    
    def __init__(self):
        self.logger = logging.getLogger("Kovrycha.Performance")
        
        # Performance metrics
        self.cpu_usage = 0.0
        self.memory_usage = 0.0
        self.fps = 0
        self.dropped_frames = 0
        
        # Sampling
        self.last_update = time.time()
        self.update_interval = 1.0  # seconds
        
        self.logger.info("Performance tracker initialized")
    
    def update(self):
        """Update performance metrics."""
        current_time = time.time()
        
        # Only update at specified intervals
        if current_time - self.last_update < self.update_interval:
            return
            
        try:
            # Get process info for own process
            import psutil
            process = psutil.Process(os.getpid())
            
            # Update CPU usage (percentage)
            self.cpu_usage = process.cpu_percent()
            
            # Update memory usage (MB)
            memory_info = process.memory_info()
            self.memory_usage = memory_info.rss / (1024 * 1024)
            
            self.logger.debug(f"CPU: {self.cpu_usage:.1f}%, Memory: {self.memory_usage:.1f} MB")
            
        except ImportError:
            self.logger.warning("psutil not available, performance tracking limited")
        except Exception as e:
            self.logger.warning(f"Error updating performance metrics: {e}")
            
        self.last_update = current_time
    
    def get_metrics(self) -> Dict[str, float]:
        """
        Get current performance metrics.
        
        Returns:
            Dictionary with performance metrics
        """
        return {
            "cpu_usage": self.cpu_usage,
            "memory_usage": self.memory_usage,
            "fps": self.fps,
            "dropped_frames": self.dropped_frames
        }
    
    def set_fps(self, fps: int, dropped: int = 0):
        """
        Set current FPS metrics.
        
        Args:
            fps: Frames per second
            dropped: Number of dropped frames
        """
        self.fps = fps
        self.dropped_frames = dropped


class ConfigManager:
    """
    Manages configuration settings for Kovrycha.
    """
    
    # Default configuration
    DEFAULT_CONFIG = {
        "version": "1.0.0",
        "autostart": True,
        "rendering": {
            "fps_limit": 60,
            "quality": "high",
            "effects_level": 2,
            "pulse_speed": 0.5,
            "glow_intensity": 0.7
        },
        "physics": {
            "particle_count": 12,
            "core_radius": 40,
            "outer_radius": 80,
            "gravity": 0.1,
            "drag": 0.02,
            "elasticity": 0.8,
            "stickiness": 0.3,
            "edge_bounce": 0.6,
            "max_velocity": 50.0,
            "random_impulse_chance": 0.01,
            "random_impulse_strength": 1.0,
            "wander_strength": 0.5,
            "cursor_avoid_distance": 150,
            "cursor_avoid_strength": 1.5
        },
        "behavior": {
            "idle_threshold": 30,
            "activity_sensitivity": 0.5,
            "shyness_level": 0.3
        },
        "appearance": {
            "base_color": [0.5, 0.1, 0.9],
            "accent_colors": [
                [0.1, 0.8, 0.3],
                [0.9, 0.2, 0.7]
            ],
            "opacity": 0.9,
            "size": 1.0
        }
    }
    
    def __init__(self, config_path: Optional[str] = None):
        self.logger = logging.getLogger("Kovrycha.Config")
        
        # Set default config path if not provided
        if config_path is None:
            config_dir = os.path.join(os.path.expanduser("~"), ".kovrycha")
            config_path = os.path.join(config_dir, "config.json")
            
        self.config_path = config_path
        self.config = self.DEFAULT_CONFIG.copy()
        
        # Load config file if it exists
        self.load()
        
        self.logger.info("Configuration manager initialized")
    
    def load(self):
        """Load configuration from file."""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    loaded_config = json.load(f)
                    
                # Update config with loaded values (preserving defaults for missing keys)
                self._update_dict(self.config, loaded_config)
                
                self.logger.info(f"Configuration loaded from {self.config_path}")
            else:
                self.logger.info("No configuration file found, using defaults")
                
        except Exception as e:
            self.logger.error(f"Error loading configuration: {e}", exc_info=True)
            self.logger.info("Using default configuration")
    
    def save(self):
        """Save configuration to file."""
        try:
            # Ensure directory exists
            config_dir = os.path.dirname(self.config_path)
            os.makedirs(config_dir, exist_ok=True)
            
            # Write config file
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
                
            self.logger.info(f"Configuration saved to {self.config_path}")
            
        except Exception as e:
            self.logger.error(f"Error saving configuration: {e}", exc_info=True)
    
    def _update_dict(self, target: Dict, source: Dict):
        """
        Recursively update a dictionary with values from another dictionary.
        
        Args:
            target: Target dictionary to update
            source: Source dictionary with new values
        """
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                # Recursively update nested dictionaries
                self._update_dict(target[key], value)
            else:
                # Update value
                target[key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.
        
        Args:
            key: Dot-separated key path (e.g., "physics.gravity")
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        keys = key.split('.')
        value = self.config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key: str, value: Any):
        """
        Set a configuration value.
        
        Args:
            key: Dot-separated key path (e.g., "physics.gravity")
            value: Value to set
        """
        keys = key.split('.')
        config = self.config
        
        # Navigate to the innermost dict
        for k in keys[:-1]:
            if k not in config or not isinstance(config[k], dict):
                config[k] = {}
            config = config[k]
            
        # Set the value
        config[keys[-1]] = value
    
    def get_renderer_config(self) -> Dict[str, Any]:
        """
        Get renderer-specific configuration.
        
        Returns:
            Dictionary with renderer settings
        """
        return {
            "fps_limit": self.get("rendering.fps_limit", 60),
            "quality": self.get("rendering.quality", "high"),
            "effects_level": self.get("rendering.effects_level", 2),
            "pulse_speed": self.get("rendering.pulse_speed", 0.5),
            "glow_intensity": self.get("rendering.glow_intensity", 0.7),
            "base_color": self.get("appearance.base_color", [0.5, 0.1, 0.9]),
            "accent_colors": self.get("appearance.accent_colors", 
                                      [[0.1, 0.8, 0.3], [0.9, 0.2, 0.7]]),
            "opacity": self.get("appearance.opacity", 0.9),
            "size": self.get("appearance.size", 1.0)
        }
    
    def get_physics_config(self) -> Dict[str, Any]:
        """
        Get physics-specific configuration.
        
        Returns:
            Dictionary with physics settings
        """
        return {
            "particle_count": self.get("physics.particle_count", 12),
            "core_radius": self.get("physics.core_radius", 40),
            "outer_radius": self.get("physics.outer_radius", 80),
            "gravity": self.get("physics.gravity", 0.1),
            "drag": self.get("physics.drag", 0.02),
            "elasticity": self.get("physics.elasticity", 0.8),
            "stickiness": self.get("physics.stickiness", 0.3),
            "edge_bounce": self.get("physics.edge_bounce", 0.6),
            "max_velocity": self.get("physics.max_velocity", 50.0),
            "random_impulse_chance": self.get("physics.random_impulse_chance", 0.01),
            "random_impulse_strength": self.get("physics.random_impulse_strength", 1.0),
            "wander_strength": self.get("physics.wander_strength", 0.5),
            "cursor_avoid_distance": self.get("physics.cursor_avoid_distance", 150),
            "cursor_avoid_strength": self.get("physics.cursor_avoid_strength", 1.5)
        }
    
    def get_behavior_config(self) -> Dict[str, Any]:
        """
        Get behavior-specific configuration.
        
        Returns:
            Dictionary with behavior settings
        """
        return {
            "idle_threshold": self.get("behavior.idle_threshold", 30),
            "activity_sensitivity": self.get("behavior.activity_sensitivity", 0.5),
            "shyness_level": self.get("behavior.shyness_level", 0.3)
        }


class EventSystem:
    """
    Simple event system for inter-module communication.
    """
    
    def __init__(self):
        self.logger = logging.getLogger("Kovrycha.Events")
        self.handlers = {}
    
    def register(self, event_type: str, handler: Callable[[Dict[str, Any]], None]):
        """Register a handler for an event type."""
        if event_type not in self.handlers:
            self.handlers[event_type] = []
            
        if handler not in self.handlers[event_type]:
            self.handlers[event_type].append(handler)
    
    def unregister(self, event_type: str, handler: Callable[[Dict[str, Any]], None]):
        """Unregister a handler for an event type."""
        if event_type in self.handlers and handler in self.handlers[event_type]:
            self.handlers[event_type].remove(handler)
    
    def emit(self, event_type: str, data: Dict[str, Any]):
        """Emit an event to all registered handlers."""
        if event_type in self.handlers:
            for handler in self.handlers[event_type]:
                try:
                    handler(data)
                except Exception as e:
                    self.logger.warning(f"Error in event handler for {event_type}: {e}")
    
    def clear(self):
        """Clear all event handlers."""
        self.handlers = {}