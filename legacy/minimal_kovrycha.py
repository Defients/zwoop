"""
Kovrycha - Desktop Slime Assistant
Minimal Implementation

This is a minimal, working implementation of Kovrycha that avoids problematic
Win32 API calls and uses Tkinter for rendering.
"""

import os
import sys
import time
import random
import math
import threading
import logging
import numpy as np
import tkinter as tk
from typing import Dict, List, Tuple, Any, Optional

# Constants
COLOR_PURPLE = "#8030e0"
COLOR_GREEN = "#20c040"
COLOR_PINK = "#f050a0"
DEFAULT_PARTICLE_COUNT = 12
DEFAULT_RADIUS = 40


class Kovrycha:
    """Minimal implementation of Kovrycha desktop slime assistant."""
    
    def __init__(self):
        # Setup logging
        self._setup_logging()
        self.logger = logging.getLogger("Kovrycha")
        self.logger.info("Initializing Minimal Kovrycha")
        
        # State
        self.running = True
        self.mood = "calm"
        self.color_state = 0.0
        self.stretch_factor = 0.0
        
        # Get screen dimensions
        self.screen_width, self.screen_height = self._get_screen_size()
        self.logger.info(f"Screen size: {self.screen_width}x{self.screen_height}")
        
        # Physics parameters - MOVED BEFORE particle initialization
        self.gravity = 0.1
        self.elasticity = 0.8
        self.drag = 0.02
        self.edge_bounce = 0.6
        self.max_velocity = 50.0
        
        # Initialize particles
        self.particles = []
        self.springs = []
        self._init_particles()
        
        # Create main window
        self.root = tk.Tk()
        self.root.title("Kovrycha")
        self.root.geometry(f"{self.screen_width}x{self.screen_height}+0+0")
        self.root.attributes("-alpha", 0.85)  # Semi-transparent
        self.root.attributes("-topmost", True)  # Always on top
        self.root.protocol("WM_DELETE_WINDOW", self.stop)
        
        # Create canvas
        self.canvas = tk.Canvas(
            self.root, 
            width=self.screen_width, 
            height=self.screen_height, 
            bg="black",
            highlightthickness=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Animation state
        self.fps = 0
        self.frame_count = 0
        self.last_fps_time = 0
        self.current_color = COLOR_PURPLE
        
        # Start physics thread
        self.physics_thread = threading.Thread(
            target=self._physics_loop,
            daemon=True
        )
        self.physics_thread.start()
        
        self.logger.info("Kovrycha initialized")
    
    def _setup_logging(self):
        """Set up logging configuration."""
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        
        # Console handler
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        root_logger.addHandler(console)
        
        # Try to add file handler
        try:
            log_dir = os.path.join(os.path.expanduser("~"), ".kovrycha")
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, "minimal_kovrycha.log")
            
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            root_logger.addHandler(file_handler)
        except Exception as e:
            print(f"Warning: Could not set up file logging: {e}")
    
    def _get_screen_size(self) -> Tuple[int, int]:
        """Get screen dimensions using tkinter for compatibility."""
        temp = tk.Tk()
        width = temp.winfo_screenwidth()
        height = temp.winfo_screenheight()
        temp.destroy()
        return width, height
    
    def _init_particles(self):
        """Initialize particles for the slime."""
        # Calculate center of screen
        center_x = self.screen_width // 2
        center_y = self.screen_height // 2
        
        # Create core particle
        core = {
            "id": 0,
            "position": np.array([center_x, center_y], dtype=float),
            "velocity": np.array([0.0, 0.0], dtype=float),
            "force": np.array([0.0, 0.0], dtype=float),
            "mass": 2.0,
            "radius": DEFAULT_RADIUS,
            "type": "core"
        }
        self.particles.append(core)
        
        # Create outer particles
        particle_count = DEFAULT_PARTICLE_COUNT
        outer_radius = DEFAULT_RADIUS * 2
        
        for i in range(1, particle_count):
            angle = (i - 1) * (2 * math.pi / (particle_count - 1))
            
            # Position around core with some randomness
            offset_x = outer_radius * math.cos(angle) + random.uniform(-10, 10)
            offset_y = outer_radius * math.sin(angle) + random.uniform(-10, 10)
            
            particle = {
                "id": i,
                "position": np.array([center_x + offset_x, center_y + offset_y], dtype=float),
                "velocity": np.array([0.0, 0.0], dtype=float),
                "force": np.array([0.0, 0.0], dtype=float),
                "mass": 1.0,
                "radius": DEFAULT_RADIUS * 0.6,
                "type": "outer"
            }
            self.particles.append(particle)
            
            # Create springs
            # Core to outer
            self._add_spring(0, i, outer_radius, self.elasticity)
            
            # Outer to adjacent outer
            if i > 1:
                chord_length = 2 * outer_radius * math.sin(math.pi / (particle_count - 1))
                self._add_spring(i - 1, i, chord_length, self.elasticity * 0.7)
            
            # Complete the circle
            if i == particle_count - 1:
                chord_length = 2 * outer_radius * math.sin(math.pi / (particle_count - 1))
                self._add_spring(i, 1, chord_length, self.elasticity * 0.7)
    
    def _add_spring(self, p1_id: int, p2_id: int, rest_length: float, strength: float):
        """Add a spring between two particles."""
        spring = {
            "p1": p1_id,
            "p2": p2_id,
            "rest_length": rest_length,
            "strength": strength
        }
        self.springs.append(spring)
    
    def _physics_loop(self):
        """Run the physics simulation loop."""
        self.logger.info("Physics loop started")
        
        last_time = time.time()
        while self.running:
            current_time = time.time()
            dt = min(current_time - last_time, 0.1)  # Cap time step
            
            # Update physics
            self._update_physics(dt)
            
            # Sleep to control physics rate
            time.sleep(max(0, 1/60 - (time.time() - current_time)))
            last_time = current_time
        
        self.logger.info("Physics loop stopped")
    
    def _update_physics(self, dt: float):
        """Update physics simulation for one time step."""
        # Update color based on stretch
        self._update_color()
        
        # Reset forces
        for particle in self.particles:
            particle["force"] = np.array([0.0, 0.0], dtype=float)
        
        # Apply spring forces
        self._apply_spring_forces()
        
        # Apply gravity and drag
        self._apply_environmental_forces()
        
        # Apply forces for movement and cursor avoidance
        self._apply_behavioral_forces()
        
        # Update positions and velocities
        self._integrate(dt)
        
        # Handle collisions with edges
        self._handle_edge_collisions()
        
        # Handle collisions between particles
        self._handle_particle_collisions()
    
    def _update_color(self):
        """Update color based on stretch factor."""
        target = 0.0  # Default purple
        
        # Map stretch factor to color transition
        if self.stretch_factor > 0.7:
            # Purple -> Green -> Pink
            target = 0.5 + (self.stretch_factor - 0.7) * (0.5 / 0.3)
        elif self.stretch_factor > 0.3:
            target = (self.stretch_factor - 0.3) * (0.5 / 0.4)
            
        # Smooth transition
        self.color_state += (target - self.color_state) * 0.1
        
        # Calculate color
        if self.color_state < 0.5:
            # Purple to Green
            t = self.color_state * 2.0
            r1, g1, b1 = int(COLOR_PURPLE[1:3], 16), int(COLOR_PURPLE[3:5], 16), int(COLOR_PURPLE[5:7], 16)
            r2, g2, b2 = int(COLOR_GREEN[1:3], 16), int(COLOR_GREEN[3:5], 16), int(COLOR_GREEN[5:7], 16)
            r = int(r1 + t * (r2 - r1))
            g = int(g1 + t * (g2 - g1))
            b = int(b1 + t * (b2 - b1))
        else:
            # Green to Pink
            t = (self.color_state - 0.5) * 2.0
            r1, g1, b1 = int(COLOR_GREEN[1:3], 16), int(COLOR_GREEN[3:5], 16), int(COLOR_GREEN[5:7], 16)
            r2, g2, b2 = int(COLOR_PINK[1:3], 16), int(COLOR_PINK[3:5], 16), int(COLOR_PINK[5:7], 16)
            r = int(r1 + t * (r2 - r1))
            g = int(g1 + t * (g2 - g1))
            b = int(b1 + t * (b2 - b1))
            
        self.current_color = f"#{r:02x}{g:02x}{b:02x}"
    
    def _apply_spring_forces(self):
        """Apply forces from springs connecting particles."""
        for spring in self.springs:
            p1 = self.particles[spring["p1"]]
            p2 = self.particles[spring["p2"]]
            
            # Calculate direction and distance
            direction = p2["position"] - p1["position"]
            distance = np.linalg.norm(direction)
            
            if distance > 0:
                # Normalize direction
                direction = direction / distance
                
                # Calculate stretch
                stretch = distance - spring["rest_length"]
                
                # Adjust for global stretch factor
                adjusted_rest_length = spring["rest_length"] * (1.0 + self.stretch_factor)
                stretch = distance - adjusted_rest_length
                
                # Calculate spring force
                force_magnitude = stretch * spring["strength"]
                spring_force = direction * force_magnitude
                
                # Apply forces
                p1["force"] += spring_force
                p2["force"] -= spring_force
    
    def _apply_environmental_forces(self):
        """Apply environmental forces like gravity and drag."""
        for particle in self.particles:
            # Apply gravity
            gravity_force = np.array([0.0, self.gravity * particle["mass"]])
            particle["force"] += gravity_force
            
            # Apply drag (proportional to velocity squared)
            velocity = particle["velocity"]
            speed_squared = np.dot(velocity, velocity)
            
            if speed_squared > 0:
                drag_force = -self.drag * speed_squared * velocity / np.sqrt(speed_squared)
                particle["force"] += drag_force
    
    def _apply_behavioral_forces(self):
        """Apply forces for movement and cursor avoidance."""
        # Get cursor position
        try:
            cursor_x = self.root.winfo_pointerx()
            cursor_y = self.root.winfo_pointery()
            cursor_pos = np.array([cursor_x, cursor_y])
            
            # Random movement for core
            if random.random() < 0.01:
                angle = random.uniform(0, 2 * math.pi)
                impulse = np.array([
                    math.cos(angle) * 1.0,
                    math.sin(angle) * 1.0
                ])
                self.particles[0]["force"] += impulse
            
            # Cursor avoidance
            avoid_distance = 150
            for particle in self.particles:
                # Direction from cursor to particle
                direction = particle["position"] - cursor_pos
                distance = np.linalg.norm(direction)
                
                # Avoid cursor if close
                if distance < avoid_distance:
                    if distance > 0:
                        direction = direction / distance
                    else:
                        angle = random.uniform(0, 2 * math.pi)
                        direction = np.array([math.cos(angle), math.sin(angle)])
                    
                    # Stronger avoidance when closer
                    avoidance_factor = 1.0 - (distance / avoid_distance)
                    avoidance_force = direction * 1.5 * avoidance_factor
                    particle["force"] += avoidance_force
                    
                    # Stretch when avoiding cursor
                    self.stretch_factor = max(0, min(1.0, 1.0 - distance / avoid_distance))
        except:
            pass
    
    def _integrate(self, dt: float):
        """Update positions and velocities."""
        for particle in self.particles:
            # Calculate acceleration
            acc = particle["force"] / particle["mass"]
            
            # Update velocity
            particle["velocity"] += acc * dt
            
            # Cap velocity
            speed = np.linalg.norm(particle["velocity"])
            if speed > self.max_velocity:
                particle["velocity"] = particle["velocity"] * (self.max_velocity / speed)
            
            # Update position
            particle["position"] += particle["velocity"] * dt
    
    def _handle_edge_collisions(self):
        """Handle collisions with screen edges."""
        for particle in self.particles:
            pos = particle["position"]
            vel = particle["velocity"]
            radius = particle["radius"]
            
            # Left edge
            if pos[0] - radius < 0:
                pos[0] = radius
                vel[0] = -vel[0] * self.edge_bounce
            
            # Right edge
            if pos[0] + radius > self.screen_width:
                pos[0] = self.screen_width - radius
                vel[0] = -vel[0] * self.edge_bounce
            
            # Top edge
            if pos[1] - radius < 0:
                pos[1] = radius
                vel[1] = -vel[1] * self.edge_bounce
            
            # Bottom edge
            if pos[1] + radius > self.screen_height:
                pos[1] = self.screen_height - radius
                vel[1] = -vel[1] * self.edge_bounce
    
    def _handle_particle_collisions(self):
        """Handle collisions between particles."""
        for i in range(len(self.particles)):
            for j in range(i + 1, len(self.particles)):
                p1 = self.particles[i]
                p2 = self.particles[j]
                
                # Calculate vector between particles
                direction = p2["position"] - p1["position"]
                distance = np.linalg.norm(direction)
                
                # Minimum distance for collision
                min_distance = p1["radius"] + p2["radius"]
                
                # Check for collision
                if distance < min_distance and distance > 0:
                    # Normalize direction
                    direction = direction / distance
                    
                    # Calculate overlap
                    overlap = min_distance - distance
                    
                    # Move particles apart
                    correction = direction * overlap * 0.5
                    p1["position"] -= correction
                    p2["position"] += correction
                    
                    # Handle velocity changes
                    rel_vel = p2["velocity"] - p1["velocity"]
                    normal_vel = np.dot(rel_vel, direction)
                    
                    # Only resolve if moving toward each other
                    if normal_vel < 0:
                        # Calculate impulse
                        restitution = self.elasticity
                        impulse = -(1 + restitution) * normal_vel
                        impulse /= (1/p1["mass"] + 1/p2["mass"])
                        
                        # Apply impulse
                        impulse_vec = direction * impulse
                        p1["velocity"] -= impulse_vec / p1["mass"]
                        p2["velocity"] += impulse_vec / p2["mass"]
    
    def _render_frame(self):
        """Render a single frame."""
        if not self.running:
            return False
        
        try:
            # Clear canvas
            self.canvas.delete("all")
            
            # Draw springs first so they appear behind particles
            for spring in self.springs:
                p1 = self.particles[spring["p1"]]
                p2 = self.particles[spring["p2"]]
                
                x1, y1 = p1["position"]
                x2, y2 = p2["position"]
                
                # Draw spring
                self.canvas.create_line(
                    x1, y1, x2, y2,
                    fill=self.current_color,
                    width=3
                )
            
            # Draw each particle
            time_val = time.time() * 2
            for particle in self.particles:
                x, y = particle["position"]
                radius = particle["radius"]
                
                # Add wobble for organic feel
                wobble = math.sin(time_val + particle["id"]) * 3
                
                # Draw particle
                self.canvas.create_oval(
                    x - radius - wobble, 
                    y - radius - wobble,
                    x + radius + wobble, 
                    y + radius + wobble,
                    fill=self.current_color,
                    outline=""
                )
            
            # Update FPS counter
            current_time = time.time()
            self.frame_count += 1
            if current_time - self.last_fps_time >= 1.0:
                self.fps = self.frame_count
                self.frame_count = 0
                self.last_fps_time = current_time
                self.root.title(f"Kovrycha - FPS: {self.fps}")
            
            # Update window
            self.root.update()
            return True
            
        except tk.TclError as e:
            if "application has been destroyed" in str(e):
                self.running = False
                return False
            self.logger.error(f"Render error: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Render error: {e}")
            return False
    
    def run(self):
        """Run the main application loop."""
        self.logger.info("Starting Kovrycha")
        
        try:
            # Main loop
            while self.running:
                if not self._render_frame():
                    break
                
                # Control frame rate
                time.sleep(1/30)  # cap at 30 FPS
                
        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received")
        except Exception as e:
            self.logger.error(f"Error in main loop: {e}", exc_info=True)
        finally:
            self.stop()
    
    def stop(self):
        """Stop the application and clean up resources."""
        if not self.running:
            return
            
        self.logger.info("Stopping Kovrycha")
        self.running = False
        
        # Wait for physics thread
        if hasattr(self, 'physics_thread') and self.physics_thread.is_alive():
            self.physics_thread.join(timeout=1.0)
        
        # Destroy window
        try:
            if hasattr(self, 'root') and self.root:
                self.root.destroy()
        except:
            pass
        
        self.logger.info("Kovrycha stopped")


if __name__ == "__main__":
    slime = Kovrycha()
    slime.run()