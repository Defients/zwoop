"""
Kovrycha - Desktop Slime Assistant
Basic Renderer Module

This module implements a simplified renderer using Tkinter instead of OpenGL,
which avoids the Win32 API compatibility issues.
"""

import math
import random
import logging
import time
import tkinter as tk
from typing import Dict, Any, List, Tuple


class SlimeRenderer:
    """
    A very simple renderer for Kovrycha using Tkinter for drawing.
    This avoids the OpenGL initialization issues.
    """
    
    def __init__(self, screen_manager, physics_engine, config: Dict[str, Any], events=None):
        self.logger = logging.getLogger("Kovrycha.Renderer")
        self.screen_manager = screen_manager
        self.physics = physics_engine
        self.config = config
        self.events = events
        
        # Rendering state
        self.window = None
        self.canvas = None
        self.running = True
        self.frame_count = 0
        self.fps = 0
        self.last_fps_update = 0
        
        # Visual configuration
        self.base_color = self._hex_color(config.get("base_color", (0.5, 0.1, 0.9)))  # Deep purple
        self.accent_colors = [
            self._hex_color(config.get("accent_colors", [[0.1, 0.8, 0.3], [0.9, 0.2, 0.7]])[0]),  # Green
            self._hex_color(config.get("accent_colors", [[0.1, 0.8, 0.3], [0.9, 0.2, 0.7]])[1])   # Pink
        ]
        self.current_color = self.base_color
        self.color_state = 0.0  # Transition between colors
        
        # Animation
        self.time = 0.0
        self.last_update = 0.0
        self.particle_shapes = []
        
        self.logger.info("Basic Renderer initialized")
    
    def _hex_color(self, rgb: Tuple[float, float, float]) -> str:
        """Convert RGB floats (0-1) to hex color string."""
        r = int(max(0, min(255, rgb[0] * 255)))
        g = int(max(0, min(255, rgb[1] * 255)))
        b = int(max(0, min(255, rgb[2] * 255)))
        return f"#{r:02x}{g:02x}{b:02x}"
    
    def initialize(self):
        """Initialize the renderer and create the window."""
        self.logger.info("Creating Tkinter window")
        
        try:
            # Create the Tkinter root window
            self.window = tk.Tk()
            self.window.title("Kovrycha")
            
            # Get primary monitor dimensions
            primary = self.screen_manager.get_primary_monitor()
            width = primary["width"]
            height = primary["height"]
            
            # Configure the window
            self.window.geometry(f"{width}x{height}+{primary['left']}+{primary['top']}")
            self.window.attributes("-alpha", 0.85)  # Make window partially transparent
            self.window.attributes("-topmost", True)  # Keep on top
            
            # Create the canvas for drawing
            self.canvas = tk.Canvas(
                self.window, 
                width=width, 
                height=height, 
                bg="black",
                highlightthickness=0
            )
            self.canvas.pack(fill=tk.BOTH, expand=True)
            
            # Set up window closing handler
            self.window.protocol("WM_DELETE_WINDOW", self._on_close)
            
            # Make window click-through (partially - this is basic)
            # On Windows, this requires additional calls to Win32 API
            # that we're avoiding for simplicity
            
            self.logger.info("Tkinter window created successfully")
            
        except Exception as e:
            self.logger.error(f"Error creating window: {e}", exc_info=True)
            if self.events:
                self.events.emit("app_error", {
                    "thread": "renderer", 
                    "error": str(e),
                    "fatal": True
                })
            raise
    
    def _on_close(self):
        """Handle window close event."""
        self.running = False
        if self.events:
            self.events.emit("exit_requested", {})
        self.window.destroy()
    
    def update_color(self, color_state: float):
        """
        Update the color transition state.
        
        Args:
            color_state: Value between 0.0 and 1.0 indicating the color transition
        """
        self.color_state = max(0.0, min(1.0, color_state))
        
        # Calculate the current color
        if self.color_state < 0.5:
            # Transition from base to accent1
            t = self.color_state * 2.0
            r1, g1, b1 = int(self.base_color[1:3], 16), int(self.base_color[3:5], 16), int(self.base_color[5:7], 16)
            r2, g2, b2 = int(self.accent_colors[0][1:3], 16), int(self.accent_colors[0][3:5], 16), int(self.accent_colors[0][5:7], 16)
            r = int(r1 + t * (r2 - r1))
            g = int(g1 + t * (g2 - g1))
            b = int(b1 + t * (b2 - b1))
            self.current_color = f"#{r:02x}{g:02x}{b:02x}"
        else:
            # Transition from accent1 to accent2
            t = (self.color_state - 0.5) * 2.0
            r1, g1, b1 = int(self.accent_colors[0][1:3], 16), int(self.accent_colors[0][3:5], 16), int(self.accent_colors[0][5:7], 16)
            r2, g2, b2 = int(self.accent_colors[1][1:3], 16), int(self.accent_colors[1][3:5], 16), int(self.accent_colors[1][5:7], 16)
            r = int(r1 + t * (r2 - r1))
            g = int(g1 + t * (g2 - g1))
            b = int(b1 + t * (b2 - b1))
            self.current_color = f"#{r:02x}{g:02x}{b:02x}"
    
    def render_frame(self):
        """Render a single frame of the slime animation."""
        if not self.canvas or not self.window:
            return False
        
        try:
            current_time = time.time()
            dt = current_time - self.last_update
            self.time += dt
            self.last_update = current_time
            
            # Calculate FPS
            self.frame_count += 1
            if current_time - self.last_fps_update >= 1.0:
                self.fps = self.frame_count
                self.frame_count = 0
                self.last_fps_update = current_time
                self.window.title(f"Kovrycha - FPS: {self.fps}")
            
            # Clear the canvas
            self.canvas.delete("all")
            
            # Get particles from physics engine
            particles = self.physics.get_particles()
            
            # Draw each particle
            for particle in particles:
                x, y = particle["position"]
                radius = particle["radius"]
                
                # Add wobble effect for organic feel
                wobble = math.sin(self.time * 3 + particle["id"]) * 2
                
                # Draw particle as circle
                self.canvas.create_oval(
                    x - radius - wobble, 
                    y - radius - wobble,
                    x + radius + wobble, 
                    y + radius + wobble,
                    fill=self.current_color,
                    outline=""
                )
            
            # Draw springs as lines connecting particles
            for spring in self.physics.springs:
                p1 = particles[spring["p1"]]
                p2 = particles[spring["p2"]]
                
                x1, y1 = p1["position"]
                x2, y2 = p2["position"]
                
                # Draw spring as line
                self.canvas.create_line(
                    x1, y1, x2, y2,
                    fill=self.current_color,
                    width=2
                )
            
            # Update canvas
            self.window.update()
            
            return True
            
        except tk.TclError as e:
            if "application has been destroyed" in str(e):
                self.running = False
                return False
            self.logger.error(f"Tkinter error: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Error in render frame: {e}")
            if self.events:
                self.events.emit("app_error", {"thread": "renderer", "error": str(e)})
            return False
    
    def run(self):
        """Run the main rendering loop."""
        self.logger.info("Starting render loop")
        
        self.last_update = time.time()
        
        try:
            # Main rendering loop
            while self.running:
                if not self.render_frame():
                    break
                
                # Control frame rate
                target_fps = self.config.get("fps_limit", 30)
                current_time = time.time()
                frame_time = current_time - self.last_update
                sleep_time = max(0, 1.0/target_fps - frame_time)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                
        except Exception as e:
            self.logger.error(f"Error in render loop: {e}", exc_info=True)
            if self.events:
                self.events.emit("app_error", {"thread": "renderer", "error": str(e)})
        finally:
            if self.window:
                try:
                    self.window.destroy()
                except:
                    pass
        
        self.logger.info("Render loop stopped")
    
    def cleanup(self):
        """Clean up resources."""
        self.logger.info("Cleaning up renderer resources")
        
        self.running = False
        
        if self.window:
            try:
                self.window.destroy()
            except:
                pass
        
        self.logger.info("Renderer resources cleaned up")