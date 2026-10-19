"""
Kovrycha - Desktop Slime Assistant (Enhanced)
Main Application Module

This module initializes and coordinates all components of Kovrycha,
managing the application lifecycle and event loop with robust error handling
and performance optimization.
"""

import os
import sys
import time
import signal
import threading
import logging
import traceback
from typing import Dict, Any, List, Optional
from logging.handlers import RotatingFileHandler

# Custom modules
from renderer import SlimeRenderer
from motion import PhysicsEngine
from interaction import SystemMonitor
from utils import ScreenManager, ConfigManager, PerformanceTracker, EventSystem


class Kovrycha:
    """Main application class for Kovrycha desktop slime assistant."""
    
    def __init__(self, config_path: str = None):
        # Setup directories
        self.app_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = os.path.join(os.path.expanduser("~"), ".kovrycha")
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Initialize logging with rotation
        log_path = os.path.join(self.data_dir, "kovrycha.log")
        self._setup_logging(log_path)
        self.logger = logging.getLogger("Kovrycha")
        self.logger.info("=== Kovrycha Starting ===")
        self.logger.info(f"App directory: {self.app_dir}")
        self.logger.info(f"Data directory: {self.data_dir}")
        
        # Application state
        self.state = {
            "running": True,
            "paused": False,
            "mood": "calm",  # calm, playful, sleepy, excited
            "color_state": 0.0,  # 0.0 = purple, 0.5 = green, 1.0 = pink
            "stretch_factor": 0.0,  # 0.0 = normal, 1.0 = fully stretched
            "startup_complete": False,
            "exit_requested": False,
            "debug_mode": False
        }
        
        # Handle signals for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        try:
            # Load configuration
            if config_path is None:
                config_path = os.path.join(self.data_dir, "config.json")
            self.config = ConfigManager(config_path)
            
            # Debug mode
            self.state["debug_mode"] = self.config.get("debug_mode", False)
            if self.state["debug_mode"]:
                self._enable_debug_logging()
                
            # Create event system for cross-component communication
            self.events = EventSystem()
            self.events.register("state_change", self._on_state_change)
            self.events.register("app_error", self._on_app_error)
            
            # Initialize components in the correct order
            self.logger.info("Initializing components...")
            
            # Screen manager first (needed by other components)
            self.screen_manager = ScreenManager()
            
            # Performance tracking
            self.performance = PerformanceTracker()
            
            # Create system monitor (for user activity detection)
            self.system_monitor = SystemMonitor(
                callback=self._on_system_event,
                events=self.events
            )
            
            # Initialize physics engine
            self.physics = PhysicsEngine(
                screen_manager=self.screen_manager,
                config=self.config.get_physics_config(),
                events=self.events
            )
            
            # Initialize renderer (must be in main thread for OpenGL)
            self.renderer = SlimeRenderer(
                screen_manager=self.screen_manager,
                physics_engine=self.physics,
                config=self.config.get_renderer_config(),
                events=self.events
            )
            
            # Create worker threads with better error handling
            self.threads = {}
            self._create_worker_threads()
            
            # Set startup complete
            self.state["startup_complete"] = True
            self.logger.info("Kovrycha initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Initialization error: {e}", exc_info=True)
            self._cleanup()
            raise
    
    def _setup_logging(self, log_path: str):
        """Set up rotating file logging."""
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        
        # Console handler
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        root_logger.addHandler(console)
        
        # File handler with rotation (5 files, 1MB each)
        file_handler = RotatingFileHandler(
            log_path, maxBytes=1024*1024, backupCount=5
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        root_logger.addHandler(file_handler)
    
    def _enable_debug_logging(self):
        """Enable debug logging for all loggers."""
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        for handler in root_logger.handlers:
            handler.setLevel(logging.DEBUG)
        self.logger.debug("Debug logging enabled")
    
    def _create_worker_threads(self):
        """Create worker threads with error handlers."""
        self.threads["physics"] = threading.Thread(
            target=self._thread_wrapper,
            args=(self._physics_loop, "physics"),
            daemon=True,
            name="PhysicsThread"
        )
        
        self.threads["monitor"] = threading.Thread(
            target=self._thread_wrapper,
            args=(self._monitor_loop, "monitor"),
            daemon=True,
            name="MonitorThread"
        )
        
        self.threads["pulse"] = threading.Thread(
            target=self._thread_wrapper,
            args=(self._pulse_loop, "pulse"),
            daemon=True,
            name="PulseThread"
        )
    
    def _thread_wrapper(self, target_func, thread_name):
        """Wrapper for threads to handle exceptions."""
        self.logger.debug(f"Starting thread: {thread_name}")
        try:
            target_func()
        except Exception as e:
            self.logger.error(f"Error in {thread_name} thread: {e}", exc_info=True)
            self.events.emit("app_error", {
                "thread": thread_name,
                "error": str(e),
                "traceback": traceback.format_exc()
            })
        finally:
            self.logger.debug(f"Thread exited: {thread_name}")
    
    def _physics_loop(self):
        """Run the physics simulation in a separate thread."""
        self.logger.info("Physics loop started")
        
        last_time = time.time()
        while self.state["running"]:
            try:
                current_time = time.time()
                dt = min(current_time - last_time, 0.1)  # Cap delta time
                
                if not self.state["paused"]:
                    # Update slime physics
                    self.physics.update(
                        dt, 
                        mood=self.state["mood"],
                        stretch_factor=self.state["stretch_factor"]
                    )
                    
                    # Update color based on stretch
                    self._update_color_state()
                
                # Sleep to maintain consistent frame rate and reduce CPU usage
                frame_rate = 90  # Higher frame rate for smoother physics
                sleep_time = max(0, 1/frame_rate - (time.time() - current_time))
                time.sleep(sleep_time)
                last_time = current_time
                
                # Check for exit signal
                if self.state["exit_requested"]:
                    break
                    
            except Exception as e:
                self.logger.error(f"Error in physics loop: {e}", exc_info=True)
                time.sleep(0.5)  # Prevent tight error loop
            
        self.logger.info("Physics loop stopped")
    
    def _monitor_loop(self):
        """Run the system monitoring in a separate thread."""
        self.logger.info("Monitor loop started")
        
        while self.state["running"]:
            try:
                # Skip if paused
                if self.state["paused"]:
                    time.sleep(0.5)
                    continue
                
                # Check system activity levels
                activity = self.system_monitor.get_activity_level()
                self._adjust_mood(activity)
                
                # Update performance metrics
                self.performance.update()
                
                # Check for any screen configuration changes
                self.screen_manager.check_for_changes()
                
                # Sleep to reduce CPU usage
                time.sleep(1.0)
                
                # Check for exit signal
                if self.state["exit_requested"]:
                    break
                    
            except Exception as e:
                self.logger.error(f"Error in monitor loop: {e}", exc_info=True)
                time.sleep(0.5)  # Prevent tight error loop
            
        self.logger.info("Monitor loop stopped")
    
    def _pulse_loop(self):
        """Run periodic pulses for animations and effects."""
        self.logger.info("Pulse loop started")
        
        pulse_state = 0.0
        pulse_direction = 1.0
        
        while self.state["running"]:
            try:
                # Skip if paused
                if self.state["paused"]:
                    time.sleep(0.1)
                    continue
                
                # Update pulse state (0.0 to 1.0, back and forth)
                pulse_state += 0.02 * pulse_direction
                if pulse_state >= 1.0:
                    pulse_state = 1.0
                    pulse_direction = -1.0
                elif pulse_state <= 0.0:
                    pulse_state = 0.0
                    pulse_direction = 1.0
                
                # Send pulse event
                self.events.emit("pulse", {
                    "value": pulse_state,
                    "mood": self.state["mood"]
                })
                
                # Sleep for smooth pulse
                time.sleep(0.05)
                
                # Check for exit signal
                if self.state["exit_requested"]:
                    break
                    
            except Exception as e:
                self.logger.error(f"Error in pulse loop: {e}", exc_info=True)
                time.sleep(0.5)  # Prevent tight error loop
            
        self.logger.info("Pulse loop stopped")
    
    def _update_color_state(self):
        """Update the color state based on the stretch factor."""
        target = 0.0  # Default purple
        
        # Map stretch factor to color transition: purple -> green -> pink
        if self.state["stretch_factor"] > 0.7:
            # Transition to pink (0.5 to 1.0)
            target = 0.5 + (self.state["stretch_factor"] - 0.7) * (0.5 / 0.3)
        elif self.state["stretch_factor"] > 0.3:
            # Transition to green (0.0 to 0.5)
            target = (self.state["stretch_factor"] - 0.3) * (0.5 / 0.4)
            
        # Smooth transition
        self.state["color_state"] += (target - self.state["color_state"]) * 0.1
        
        # Update renderer color
        self.renderer.update_color(self.state["color_state"])
    
    def _adjust_mood(self, activity_level: float):
        """
        Adjust the slime's mood based on user activity.
        
        Args:
            activity_level: 0.0 = idle, 1.0 = very active
        """
        old_mood = self.state["mood"]
        
        if activity_level > 0.8:
            # User is very active, slime becomes sleepy and hides
            new_mood = "sleepy"
        elif activity_level > 0.4:
            # User is moderately active, slime is calm
            new_mood = "calm"
        elif activity_level > 0.15:
            # User is somewhat active, slime is calm but more animated
            new_mood = "calm"
        else:
            # User is relatively idle, slime becomes playful
            new_mood = "playful"
            
        # Only update if mood changed
        if new_mood != old_mood:
            self.state["mood"] = new_mood
            self.logger.debug(f"Mood changed: {old_mood} -> {new_mood}")
            self.events.emit("mood_change", {"mood": new_mood})
    
    def _on_system_event(self, event_type: str, data: Dict[str, Any]):
        """
        Handle system events from the monitor.
        
        Args:
            event_type: Type of event (e.g., 'application_change', 'idle')
            data: Event-specific data
        """
        if event_type == "application_change":
            # React to application changes
            self.physics.set_avoidance_zone(data.get("window_rect", None))
            self.logger.debug(f"Application change: {data.get('title', 'Unknown')}")
        
        elif event_type == "idle_state_change":
            if data.get("idle", False):
                # User is idle, become more playful
                self.state["mood"] = "playful"
                self.logger.debug("User is now idle, becoming playful")
            else:
                # User is active, become calmer
                self.state["mood"] = "calm"
                self.logger.debug("User is now active, becoming calm")
                
        elif event_type == "drag_slime":
            # User is interacting with the slime directly
            self.state["stretch_factor"] = min(1.0, data.get("distance", 0) / 100)
            self.state["mood"] = "excited"
            self.logger.debug(f"Dragging slime, stretch: {self.state['stretch_factor']:.2f}")
    
    def _on_state_change(self, data: Dict[str, Any]):
        """Handle state change events from other components."""
        for key, value in data.items():
            if key in self.state:
                old_value = self.state[key]
                self.state[key] = value
                self.logger.debug(f"State change: {key} = {value} (was {old_value})")
    
    def _on_app_error(self, data: Dict[str, Any]):
        """Handle error events from components and threads."""
        thread_name = data.get("thread", "unknown")
        error_msg = data.get("error", "No error message")
        self.logger.error(f"Application error in {thread_name}: {error_msg}")
        
        # In serious errors, consider safe shutdown
        if data.get("fatal", False):
            self.logger.critical("Fatal error detected, requesting application shutdown")
            self.stop()
    
    def _signal_handler(self, signum, frame):
        """Handle system signals for graceful shutdown."""
        sig_name = signal.Signals(signum).name
        self.logger.info(f"Received signal {sig_name}, shutting down")
        self.stop()
    
    def start(self):
        """Start Kovrycha application."""
        self.logger.info("Starting Kovrycha")
        
        try:
            # Start worker threads
            for name, thread in self.threads.items():
                thread.start()
                self.logger.debug(f"Started {name} thread")
            
            # Initialize renderer (must be in main thread for most GUI frameworks)
            self.renderer.initialize()
            
            # Start main rendering loop (blocks until exit)
            self.renderer.run()
            
        except Exception as e:
            self.logger.error(f"Error in main loop: {e}", exc_info=True)
        finally:
            self.stop()
    
    def stop(self):
        """Stop Kovrycha application and clean up resources."""
        if not self.state["exit_requested"]:
            self.logger.info("Stopping Kovrycha")
            self.state["exit_requested"] = True
            self.state["running"] = False
            
            # Save configuration
            self.config.save()
            
            # Allow threads time to exit gracefully
            time.sleep(0.5)
            
            # Cleanup resources
            self._cleanup()
            
            self.logger.info("Kovrycha stopped")
    
    def _cleanup(self):
        """Clean up all resources."""
        # Stop renderer first
        if hasattr(self, 'renderer'):
            try:
                self.renderer.cleanup()
            except Exception as e:
                self.logger.error(f"Error cleaning up renderer: {e}")
        
        # Stop system monitor
        if hasattr(self, 'system_monitor'):
            try:
                self.system_monitor.cleanup()
            except Exception as e:
                self.logger.error(f"Error cleaning up system monitor: {e}")
        
        # Wait for threads to terminate
        if hasattr(self, 'threads'):
            for name, thread in self.threads.items():
                if thread.is_alive():
                    self.logger.debug(f"Waiting for {name} thread to terminate")
                    thread.join(timeout=1.0)
                    if thread.is_alive():
                        self.logger.warning(f"{name} thread did not terminate cleanly")
        
        # Clear resources from event system
        if hasattr(self, 'events'):
            self.events.clear()


if __name__ == "__main__":
    # Process command line arguments
    import argparse
    parser = argparse.ArgumentParser(description='Kovrycha Desktop Slime Assistant')
    parser.add_argument('--config', '-c', help='Path to configuration file')
    parser.add_argument('--debug', '-d', action='store_true', help='Enable debug mode')
    args = parser.parse_args()
    
    try:
        # Create and start Kovrycha
        slime = Kovrycha(config_path=args.config)
        
        # Enable debug mode if requested
        if args.debug:
            slime.state["debug_mode"] = True
            slime._enable_debug_logging()
        
        # Start the application
        slime.start()
    except KeyboardInterrupt:
        print("\nKovrycha terminated by user")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}")
        traceback.print_exc()
        sys.exit(1)