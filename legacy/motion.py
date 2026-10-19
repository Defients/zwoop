"""
Kovrycha - Desktop Slime Assistant (Enhanced)
Motion Module

This module handles the physics simulation for Kovrycha,
implementing advanced soft-body dynamics and movement behavior
for an ethereal, magical experience.
"""

import random
import math
import logging
import numpy as np
from typing import Dict, List, Tuple, Any, Optional
import time


class PhysicsEngine:
    """
    Enhanced physics engine for simulating the soft-body dynamics of Kovrycha.
    Uses a particle system with advanced spring constraints to create an
    ethereal, magical motion that feels like it shouldn't exist but does.
    """
    
    def __init__(self, screen_manager, config: Dict[str, Any], events=None):
        self.logger = logging.getLogger("Kovrycha.Physics")
        self.screen_manager = screen_manager
        self.config = config
        self.events = events
        
        # Physics parameters (with more options for the ethereal feel)
        self.gravity = config.get("gravity", 0.08)  # Reduced for floatier feel
        self.drag = config.get("drag", 0.015)  # Lower drag for smoother movement
        self.elasticity = config.get("elasticity", 0.85)  # More bounce
        self.stickiness = config.get("stickiness", 0.25)  # Base stickiness
        self.edge_bounce = config.get("edge_bounce", 0.7)  # Bouncier edges
        self.max_velocity = config.get("max_velocity", 60.0)  # Higher max speed
        self.ghost_factor = config.get("ghost_factor", 0.2)  # How much particles ignore obstacles (magical effect)
        
        # Dampening for smoother movement
        self.velocity_dampening = config.get("velocity_dampening", 0.97)
        
        # Noise for organic motion (Perlin-like)
        self.noise_strength = config.get("noise_strength", 0.12)
        self.noise_scale = config.get("noise_scale", 0.02)
        self.noise_time = 0.0
        
        # Movement parameters for magical behavior
        self.random_impulse_chance = config.get("random_impulse_chance", 0.015)
        self.random_impulse_strength = config.get("random_impulse_strength", 1.5)
        self.wander_strength = config.get("wander_strength", 0.65)
        self.cursor_avoid_distance = config.get("cursor_avoid_distance", 180)
        self.cursor_avoid_strength = config.get("cursor_avoid_strength", 2.0)
        
        # Advanced behavior parameters
        self.hover_tendency = config.get("hover_tendency", 0.15)  # Tendency to float upward
        self.gather_strength = config.get("gather_strength", 0.3)  # Tendency for particles to gather
        self.coherence_strength = config.get("coherence_strength", 0.5)  # How much the slime stays together
        
        # Initialize particle system
        self.particles = []
        self.springs = []
        self.avoidance_zones = []
        
        # Behavioral state
        self.mood = "calm"  # calm, playful, sleepy, excited
        self.target_position = None
        self.last_edge_collision = None
        self.stretch_factor = 0.0
        self.time_since_last_impulse = 0.0
        
        # Add noise offsets for organic movement
        self.noise_offsets = []
        
        # Mood-based behavior adjustments
        self.mood_behaviors = {
            "calm": {
                "wander_strength": 0.65,
                "random_impulse_chance": 0.015,
                "elasticity": 0.85,
                "hover_tendency": 0.15,
                "gather_strength": 0.3
            },
            "playful": {
                "wander_strength": 1.5,
                "random_impulse_chance": 0.035,
                "elasticity": 0.95,
                "hover_tendency": 0.35,
                "gather_strength": 0.1
            },
            "sleepy": {
                "wander_strength": 0.2,
                "random_impulse_chance": 0.005,
                "elasticity": 0.7,
                "hover_tendency": 0.05,
                "gather_strength": 0.5
            },
            "excited": {
                "wander_strength": 2.0,
                "random_impulse_chance": 0.06,
                "elasticity": 1.0,
                "hover_tendency": 0.4,
                "gather_strength": 0.15
            }
        }
        
        # Initialize particles and springs
        self._initialize_particles()
        
        # Register event handlers
        if self.events:
            self.events.register("mood_change", self._on_mood_change)
        
        self.logger.info("Physics engine initialized with %d particles and %d springs",
                        len(self.particles), len(self.springs))
    
    def _initialize_particles(self):
        """Initialize the particle system for the slime with ethereal properties."""
        # Get the primary monitor dimensions
        primary = self.screen_manager.get_primary_monitor()
        
        # Calculate initial position (center of primary monitor)
        center_x = primary["left"] + primary["width"] // 2
        center_y = primary["top"] + primary["height"] // 2
        
        # Slime parameters - more particles for smoother appearance
        particle_count = self.config.get("particle_count", 16)  # More particles
        core_radius = self.config.get("core_radius", 45)
        outer_radius = self.config.get("outer_radius", 90)
        
        # Create core particle (center of the slime)
        core_particle = {
            "id": 0,
            "position": np.array([center_x, center_y], dtype=float),
            "velocity": np.array([0.0, 0.0], dtype=float),
            "force": np.array([0.0, 0.0], dtype=float),
            "mass": 2.5,  # Heavier core for more stability
            "radius": core_radius,
            "fixed": False,
            "type": "core",
            "ghost_phase": 0.0  # For ethereal phase shifting
        }
        self.particles.append(core_particle)
        self.noise_offsets.append(random.uniform(0, 100))
        
        # Create outer particles arranged in a circle
        for i in range(1, particle_count):
            angle = (i - 1) * (2 * math.pi / (particle_count - 1))
            
            # Position particles in a circle around the core
            # Add slight randomness for organic feel
            radius_variance = random.uniform(0.9, 1.1)
            offset_x = outer_radius * radius_variance * math.cos(angle)
            offset_y = outer_radius * radius_variance * math.sin(angle)
            
            # Add some randomness to initial positions
            offset_x += random.uniform(-15, 15)
            offset_y += random.uniform(-15, 15)
            
            # Randomize particle sizes slightly for organic feel
            size_variance = random.uniform(0.85, 1.15)
            
            particle = {
                "id": i,
                "position": np.array([center_x + offset_x, center_y + offset_y], dtype=float),
                "velocity": np.array([0.0, 0.0], dtype=float),
                "force": np.array([0.0, 0.0], dtype=float),
                "mass": 1.0,
                "radius": core_radius * 0.65 * size_variance,
                "fixed": False,
                "type": "outer",
                "ghost_phase": random.uniform(0, math.pi * 2)  # Random phase
            }
            self.particles.append(particle)
            self.noise_offsets.append(random.uniform(0, 100))
            
            # Create springs from core to this particle
            self._add_spring(0, i, outer_radius, self.elasticity)
            
            # Create springs between adjacent outer particles
            if i > 1:
                chord_length = 2 * outer_radius * math.sin(math.pi / (particle_count - 1))
                self._add_spring(i - 1, i, chord_length, self.elasticity * 0.75)
            
            # Complete the circle
            if i == particle_count - 1:
                chord_length = 2 * outer_radius * math.sin(math.pi / (particle_count - 1))
                self._add_spring(i, 1, chord_length, self.elasticity * 0.75)
        
        # Add some cross-springs for stability and better deformation
        if particle_count >= 8:
            # Add cross-springs for more organic deformation
            for i in range(1, particle_count // 2 + 1):
                opposite = i + particle_count // 2
                if opposite < particle_count:
                    # Connect opposite particles
                    self._add_spring(i, opposite, outer_radius * 2, self.elasticity * 0.4)
    
    def _add_spring(self, p1_id: int, p2_id: int, rest_length: float, strength: float):
        """Add a spring constraint between two particles."""
        spring = {
            "p1": p1_id,
            "p2": p2_id,
            "rest_length": rest_length,
            "strength": strength,
            "dampening": 0.2  # Add dampening for more organic motion
        }
        self.springs.append(spring)
    
    def update(self, dt: float, mood: str = None, stretch_factor: float = None):
        """
        Update the physics simulation for the given time step.
        
        Args:
            dt: Time delta in seconds
            mood: Current mood of the slime (calm, playful, sleepy, excited)
            stretch_factor: Current stretch factor (0.0 to 1.0)
        """
        if mood is not None and mood != self.mood:
            self.mood = mood
            self._adjust_behavior()
            
        if stretch_factor is not None:
            self.stretch_factor = stretch_factor
        
        # Update noise time for organic motion
        self.noise_time += dt * 0.5
        self.time_since_last_impulse += dt
        
        # Reset forces on all particles
        for particle in self.particles:
            particle["force"] = np.array([0.0, 0.0], dtype=float)
        
        # Apply forces in this order:
        # 1. Spring forces (internal structure)
        self._apply_spring_forces()
        
        # 2. Environmental forces (gravity, drag, noise)
        self._apply_environmental_forces(dt)
        
        # 3. Behavioral forces (movement, avoidance)
        self._apply_behavioral_forces(dt)
        
        # 4. Boundary forces (screen edges)
        self._apply_boundary_forces()
        
        # Update particle positions using Verlet integration
        self._integrate(dt)
        
        # Apply edge collision constraints
        self._handle_edge_collisions()
        
        # Apply particle-particle collision constraints
        self._handle_particle_collisions()
        
        # Apply position constraints to maintain shape
        self._apply_position_constraints()
    
    def _adjust_behavior(self):
        """Adjust physics parameters based on current mood for magical effects."""
        if self.mood in self.mood_behaviors:
            behavior = self.mood_behaviors[self.mood]
            self.wander_strength = behavior["wander_strength"]
            self.random_impulse_chance = behavior["random_impulse_chance"]
            self.elasticity = behavior["elasticity"]
            self.hover_tendency = behavior["hover_tendency"]
            self.gather_strength = behavior["gather_strength"]
            
            # Additional mood-specific adjustments
            if self.mood == "playful":
                # More energetic, bouncy behavior
                self.gravity *= 0.7  # Less gravity
                self.velocity_dampening = 0.98  # Less dampening
            elif self.mood == "sleepy":
                # Very minimal movement, higher stickiness
                self.gravity *= 1.3  # More gravity
                self.stickiness = 0.5
                self.velocity_dampening = 0.95  # More dampening
            elif self.mood == "excited":
                # Highly energetic, very bouncy
                self.gravity *= 0.5  # Much less gravity
                self.stickiness = 0.1
                self.velocity_dampening = 0.99  # Almost no dampening
            else:  # calm
                # Reset to default
                self.gravity = self.config.get("gravity", 0.08)
                self.stickiness = self.config.get("stickiness", 0.25)
                self.velocity_dampening = self.config.get("velocity_dampening", 0.97)
    
    def _generate_noise(self, offset, scale=1.0):
        """Generate Perlin-like noise for organic motion."""
        # Simple noise function - in a real implementation, use a proper Perlin noise library
        t = self.noise_time * self.noise_scale
        x = math.sin(offset * 0.3 + t) * math.cos(offset * 0.8 + t * 1.5)
        y = math.sin(offset * 0.7 + t * 0.8) * math.cos(offset * 0.4 + t * 0.9)
        return np.array([x, y], dtype=float) * scale
    
    def _apply_spring_forces(self):
        """Apply forces from springs connecting particles with improved dynamics."""
        for spring in self.springs:
            p1 = self.particles[spring["p1"]]
            p2 = self.particles[spring["p2"]]
            
            # Get positions
            pos1 = p1["position"]
            pos2 = p2["position"]
            
            # Calculate distance between particles
            direction = pos2 - pos1
            distance = np.linalg.norm(direction)
            
            if distance > 0.001:  # Avoid division by zero
                # Normalize direction vector
                direction = direction / distance
                
                # Adjust rest length based on global stretch factor
                adjusted_rest_length = spring["rest_length"] * (1.0 + self.stretch_factor * 0.5)
                
                # Calculate stretch factor of this spring
                stretch = distance - adjusted_rest_length
                
                # Calculate spring force (Hooke's Law: F = k * x)
                force_magnitude = stretch * spring["strength"]
                spring_force = direction * force_magnitude
                
                # Add velocity-based dampening for more stable springs
                vel1 = p1["velocity"]
                vel2 = p2["velocity"]
                relative_velocity = np.dot(vel2 - vel1, direction)
                damping_force = direction * relative_velocity * spring["dampening"]
                
                # Apply forces to particles (equal and opposite)
                if not p1["fixed"]:
                    p1["force"] += spring_force + damping_force
                if not p2["fixed"]:
                    p2["force"] -= spring_force + damping_force
                
                # Special effect: make springs visibly more elastic when excited
                if self.mood == "excited" and random.random() < 0.002:
                    # Add random perpendicular impulse for jiggle
                    perp = np.array([-direction[1], direction[0]], dtype=float)
                    impulse = perp * random.uniform(-2.0, 2.0)
                    
                    if not p1["fixed"]:
                        p1["force"] += impulse
                    if not p2["fixed"]:
                        p2["force"] -= impulse
    
    def _apply_environmental_forces(self, dt):
        """Apply environmental forces like gravity, drag, and magical influences."""
        # Get core particle for reference
        core = self.particles[0]
        core_pos = core["position"]
        
        for i, particle in enumerate(self.particles):
            if particle["fixed"]:
                continue
            
            # Basic forces
            mass = particle["mass"]
            pos = particle["position"]
            vel = particle["velocity"]
            
            # 1. Apply gravity with hover tendency (magical floating effect)
            hover = math.sin(self.noise_time * 0.7 + i * 0.5) * self.hover_tendency * mass
            gravity_force = np.array([0.0, (self.gravity - hover) * mass], dtype=float)
            particle["force"] += gravity_force
            
            # 2. Apply drag (proportional to velocity)
            speed_squared = np.dot(vel, vel)
            if speed_squared > 0:
                drag_force = -self.drag * speed_squared * vel / np.sqrt(speed_squared)
                particle["force"] += drag_force
            
            # 3. Apply noise for organic movement
            noise = self._generate_noise(self.noise_offsets[i], self.noise_strength * mass)
            particle["force"] += noise
            
            # 4. Apply coherence - attraction toward the core (magical gathering effect)
            if i > 0:  # Not the core itself
                to_core = core_pos - pos
                dist_to_core = np.linalg.norm(to_core)
                
                if dist_to_core > 0.001:
                    # Normalize and apply attraction
                    to_core = to_core / dist_to_core
                    
                    # Stronger attraction when far from core
                    gather_strength = self.gather_strength * (1.0 + dist_to_core * 0.002)
                    
                    # Apply coherence force
                    coherence_force = to_core * gather_strength * mass
                    particle["force"] += coherence_force
    
    def _apply_behavioral_forces(self, dt):
        """Apply forces related to slime behavior and movement."""
        cursor_pos = self.screen_manager.get_cursor_position()
        
        # Get core particle (for movement control)
        core = self.particles[0]
        
        # Apply random impulses for organic movement
        impulse_chance = self.random_impulse_chance * dt * 60  # Scale with framerate
        
        # More frequent impulses in playful/excited moods
        if self.time_since_last_impulse > 0.5 and random.random() < impulse_chance:
            # Random angle with directional bias toward upper screen (magical floating)
            bias = random.uniform(0, 0.3)  # Slight upward bias
            angle = random.uniform(-math.pi + bias, math.pi - bias)
            
            # Create impulse vector
            strength = self.random_impulse_strength
            if self.mood == "excited":
                strength *= 2.0
            elif self.mood == "sleepy":
                strength *= 0.5
                
            impulse = np.array([
                math.cos(angle) * strength,
                math.sin(angle) * strength
            ], dtype=float)
            
            # Apply impulse to core
            core["force"] += impulse
            self.time_since_last_impulse = 0
            
            # For magical effect: when excited, occasionally apply impulse to all particles
            if self.mood == "excited" and random.random() < 0.2:
                for p in self.particles[1:]:  # Skip core
                    # Scaled impulse with variation
                    p_angle = angle + random.uniform(-0.5, 0.5)
                    p_impulse = np.array([
                        math.cos(p_angle) * strength * 0.5,
                        math.sin(p_angle) * strength * 0.5
                    ], dtype=float)
                    p["force"] += p_impulse
        
        # Apply cursor avoidance with ethereal effects
        if cursor_pos is not None:
            cursor_np = np.array(cursor_pos, dtype=float)
            
            for particle in self.particles:
                # Calculate distance to cursor
                direction = particle["position"] - cursor_np
                distance = np.linalg.norm(direction)
                
                # If cursor is close enough, avoid it
                if distance < self.cursor_avoid_distance:
                    # Normalize direction vector
                    if distance > 0.001:
                        direction = direction / distance
                    else:
                        # Random direction if too close
                        angle = random.uniform(0, 2 * math.pi)
                        direction = np.array([math.cos(angle), math.sin(angle)], dtype=float)
                    
                    # Calculate avoidance force (stronger as cursor gets closer)
                    avoidance_factor = 1.0 - (distance / self.cursor_avoid_distance)
                    avoidance_factor = avoidance_factor ** 1.5  # Exponential falloff
                    
                    # Apply avoidance force
                    avoidance_force = direction * self.cursor_avoid_strength * avoidance_factor
                    particle["force"] += avoidance_force
                    
                    # Special effect: when cursor is very close, particles can "phase through" (ghost effect)
                    # by temporarily reducing collision response
                    if distance < self.cursor_avoid_distance * 0.3:
                        particle["ghost_phase"] = (particle["ghost_phase"] + dt * 5) % (math.pi * 2)
        
        # Apply avoidance for active windows
        self._apply_avoidance_forces()
    
    def _apply_avoidance_forces(self):
        """Apply avoidance forces for active windows with ethereal ghosting effects."""
        for zone in self.avoidance_zones:
            # Convert rectangle to numpy arrays for calculation
            zone_min = np.array([zone["left"], zone["top"]], dtype=float)
            zone_max = np.array([zone["right"], zone["bottom"]], dtype=float)
            
            for particle in self.particles:
                pos = particle["position"]
                
                # Check if particle is inside or near the avoidance zone
                nearest_point = np.maximum(zone_min, np.minimum(pos, zone_max))
                distance_vector = pos - nearest_point
                distance = np.linalg.norm(distance_vector)
                
                # If particle is close to or inside avoidance zone
                avoidance_radius = 120  # Distance to start avoiding
                
                if distance < avoidance_radius:
                    # Ethereal effect: sometimes particles can phase through objects
                    # based on ghost_phase and ghost_factor
                    ghost_effect = abs(math.sin(particle["ghost_phase"])) * self.ghost_factor
                    
                    # If not ghosting through, apply avoidance
                    if random.random() > ghost_effect:
                        # Normalized direction away from nearest point
                        if distance > 0.001:
                            direction = distance_vector / distance
                        else:
                            # If inside, choose a random direction
                            angle = random.uniform(0, 2 * math.pi)
                            direction = np.array([math.cos(angle), math.sin(angle)], dtype=float)
                        
                        # Avoidance force (stronger when closer)
                        avoidance_factor = 1.0 - (distance / avoidance_radius)
                        avoidance_force = direction * 2.5 * avoidance_factor
                        particle["force"] += avoidance_force
                    else:
                        # When ghosting, apply a slight attraction in the opposite direction
                        # to create that "phasing through" effect
                        if distance > 0.001:
                            direction = -distance_vector / distance
                            particle["force"] += direction * 0.3
                    
                    # Update ghost phase - particles have different phase speeds for variation
                    particle["ghost_phase"] = (particle["ghost_phase"] + 0.05) % (math.pi * 2)
    
    def _apply_boundary_forces(self):
        """Apply forces to keep the slime within screen boundaries with magical effects."""
        combined_bounds = self.screen_manager.get_combined_bounds()
        
        for particle in self.particles:
            pos = particle["position"]
            
            # Check if near any edge of the combined screen area
            # Larger edge zone for more gradual response
            edge_distance = 70  # Distance from edge to start applying force
            
            # Left edge
            if pos[0] < combined_bounds["left"] + edge_distance:
                distance = pos[0] - combined_bounds["left"]
                force = (edge_distance - distance) / edge_distance
                particle["force"][0] += force * 2.0
            
            # Right edge
            if pos[0] > combined_bounds["right"] - edge_distance:
                distance = combined_bounds["right"] - pos[0]
                force = (edge_distance - distance) / edge_distance
                particle["force"][0] -= force * 2.0
            
            # Top edge - slightly weaker to encourage upward floating
            if pos[1] < combined_bounds["top"] + edge_distance:
                distance = pos[1] - combined_bounds["top"]
                force = (edge_distance - distance) / edge_distance
                particle["force"][1] += force * 1.5
            
            # Bottom edge - slightly stronger to prevent falling off
            if pos[1] > combined_bounds["bottom"] - edge_distance:
                distance = combined_bounds["bottom"] - pos[1]
                force = (edge_distance - distance) / edge_distance
                particle["force"][1] -= force * 2.5
    
    def _integrate(self, dt: float):
        """
        Update particle positions and velocities using improved integration.
        
        Args:
            dt: Time step in seconds
        """
        for particle in self.particles:
            if particle["fixed"]:
                continue
                
            # Get current state
            pos = particle["position"]
            vel = particle["velocity"]
            force = particle["force"]
            mass = particle["mass"]
            
            # Calculate acceleration (F = ma, so a = F/m)
            acc = force / mass
            
            # Apply dampening for smoother motion
            vel *= self.velocity_dampening
            
            # Update velocity (semi-implicit Euler)
            vel = vel + acc * dt
            
            # Clamp velocity to maximum
            speed = np.linalg.norm(vel)
            if speed > self.max_velocity:
                vel = vel * (self.max_velocity / speed)
            
            # Update position
            pos = pos + vel * dt
            
            # Store updated state
            particle["position"] = pos
            particle["velocity"] = vel
    
    def _handle_edge_collisions(self):
        """Handle collisions with screen edges with improved effects."""
        combined_bounds = self.screen_manager.get_combined_bounds()
        
        had_collision = False
        collision_type = None
        
        for particle in self.particles:
            pos = particle["position"]
            vel = particle["velocity"]
            radius = particle["radius"]
            
            # Check collision with each edge
            # Left edge
            if pos[0] - radius < combined_bounds["left"]:
                # Create cling effect - slow down more on horizontal surfaces
                old_vel_x = vel[0]
                pos[0] = combined_bounds["left"] + radius
                vel[0] = -vel[0] * self.edge_bounce
                
                # Apply vertical friction when hitting sides
                vel[1] *= 0.9
                
                had_collision = True
                collision_type = "left"
            
            # Right edge
            if pos[0] + radius > combined_bounds["right"]:
                old_vel_x = vel[0]
                pos[0] = combined_bounds["right"] - radius
                vel[0] = -vel[0] * self.edge_bounce
                
                # Apply vertical friction when hitting sides
                vel[1] *= 0.9
                
                had_collision = True
                collision_type = "right"
            
            # Top edge
            if pos[1] - radius < combined_bounds["top"]:
                old_vel_y = vel[1]
                pos[1] = combined_bounds["top"] + radius
                vel[1] = -vel[1] * self.edge_bounce
                
                # Apply horizontal friction when hitting top/bottom
                vel[0] *= 0.9
                
                had_collision = True
                collision_type = "top"
            
            # Bottom edge
            if pos[1] + radius > combined_bounds["bottom"]:
                old_vel_y = vel[1]
                pos[1] = combined_bounds["bottom"] - radius
                vel[1] = -vel[1] * self.edge_bounce
                
                # Apply horizontal friction when hitting top/bottom
                vel[0] *= 0.9
                
                had_collision = True
                collision_type = "bottom"
            
            # Apply stickiness if colliding
            if had_collision:
                # Stickiness varies with mood
                effective_stickiness = self.stickiness
                if self.mood == "sleepy":
                    effective_stickiness *= 2.0
                elif self.mood == "excited":
                    effective_stickiness *= 0.5
                    
                if random.random() < effective_stickiness:
                    # Reduce velocity to simulate sticking
                    vel *= 0.5
                    
                    # Magical effect: occasionally stick strongly to edges
                    if random.random() < 0.2:
                        vel *= 0.2  # Much stronger sticking
                
                self.last_edge_collision = collision_type
                
                # Notify of collision if we have events
                if self.events and particle["type"] == "core":
                    self.events.emit("collision", {
                        "type": "edge",
                        "edge": collision_type,
                        "particle": particle["id"],
                        "velocity": np.linalg.norm(vel)
                    })
    
    def _handle_particle_collisions(self):
        """Handle collisions between particles with improved dynamics."""
        particle_count = len(self.particles)
        
        for i in range(particle_count):
            for j in range(i + 1, particle_count):
                p1 = self.particles[i]
                p2 = self.particles[j]
                
                # Calculate vector between particles
                pos1 = p1["position"]
                pos2 = p2["position"]
                direction = pos2 - pos1
                
                # Calculate distance between particles
                distance = np.linalg.norm(direction)
                
                # Minimum distance for collision (sum of radii)
                min_distance = p1["radius"] + p2["radius"]
                
                # If particles are intersecting
                if distance < min_distance and distance > 0.001:
                    # Normalize direction vector
                    direction = direction / distance
                    
                    # Calculate overlap
                    overlap = min_distance - distance
                    
                    # Calculate correction vector - heavier particles move less
                    p1_ratio = p2["mass"] / (p1["mass"] + p2["mass"])
                    p2_ratio = p1["mass"] / (p1["mass"] + p2["mass"])
                    
                    correction1 = direction * overlap * p1_ratio
                    correction2 = direction * overlap * p2_ratio
                    
                    # Move particles apart if they're not fixed
                    if not p1["fixed"]:
                        p1["position"] -= correction1
                    if not p2["fixed"]:
                        p2["position"] += correction2
                    
                    # Handle collision response (adjust velocities)
                    if not (p1["fixed"] and p2["fixed"]):
                        # Calculate relative velocity
                        v1 = p1["velocity"]
                        v2 = p2["velocity"]
                        rel_vel = v2 - v1
                        
                        # Calculate relative velocity along the collision normal
                        normal_vel = np.dot(rel_vel, direction)
                        
                        # Only resolve if particles are moving toward each other
                        if normal_vel < 0:
                            # Calculate restitution (bounciness)
                            restitution = self.elasticity
                            
                            # Impulse-based collision response
                            j_numerator = -(1 + restitution) * normal_vel
                            j_denominator = (1 / p1["mass"]) + (1 / p2["mass"])
                            j = j_numerator / j_denominator
                            
                            # Apply impulse
                            if not p1["fixed"]:
                                p1["velocity"] -= (j / p1["mass"]) * direction
                            if not p2["fixed"]:
                                p2["velocity"] += (j / p2["mass"]) * direction
                            
                            # Magical effect: add slight rotation effect
                            if random.random() < 0.3:
                                # Perpendicular direction for rotation
                                perp = np.array([-direction[1], direction[0]], dtype=float)
                                rot_strength = min(0.1, abs(normal_vel) * 0.05)
                                
                                if not p1["fixed"]:
                                    p1["velocity"] += perp * rot_strength
                                if not p2["fixed"]:
                                    p2["velocity"] -= perp * rot_strength
    
    def _apply_position_constraints(self):
        """Apply additional position constraints to maintain slime shape."""
        # Get core particle
        core = self.particles[0]
        core_pos = core["position"]
        
        # Find maximum allowed distance from core (based on slime size and stretch)
        max_radius = self.config.get("outer_radius", 90) * (1.5 + self.stretch_factor)
        
        # Check each non-core particle
        for particle in self.particles[1:]:
            pos = particle["position"]
            
            # Calculate distance to core
            to_core = core_pos - pos
            dist = np.linalg.norm(to_core)
            
            # If too far from core, pull back
            if dist > max_radius:
                # Normalize direction
                if dist > 0.001:
                    to_core = to_core / dist
                    
                    # Move particle toward core
                    particle["position"] = core_pos - to_core * max_radius
                    
                    # Adjust velocity to prevent further stretching
                    vel = particle["velocity"]
                    radial_vel = np.dot(vel, -to_core)
                    
                    # If moving away from core, dampen that component
                    if radial_vel < 0:
                        particle["velocity"] = vel - to_core * radial_vel * 0.8
    
    def _on_mood_change(self, data):
        """Handle mood change events."""
        new_mood = data.get("mood", "calm")
        if new_mood != self.mood:
            self.mood = new_mood
            self._adjust_behavior()
            self.logger.debug(f"Physics adjusted for mood: {new_mood}")
    
    def get_particles(self) -> List[Dict[str, Any]]:
        """
        Get the current particle state.
        
        Returns:
            List of particle data (position, radius, etc.)
        """
        return self.particles
    
    def set_avoidance_zone(self, rect: Optional[Dict[str, int]]):
        """
        Set a zone that the slime should avoid (e.g., active window).
        
        Args:
            rect: Dictionary with left, top, right, bottom coordinates
        """
        if rect is None:
            self.avoidance_zones = []
        else:
            # Keep only the most recent avoidance zone
            self.avoidance_zones = [rect]
    
    def apply_force(self, particle_id: int, force: Tuple[float, float]):
        """
        Apply an external force to a specific particle.
        
        Args:
            particle_id: ID of the particle to apply force to
            force: Force vector as (x, y) tuple
        """
        if 0 <= particle_id < len(self.particles):
            self.particles[particle_id]["force"] += np.array(force, dtype=float)
    
    def set_fixed(self, particle_id: int, fixed: bool):
        """
        Set whether a particle is fixed in place or free to move.
        
        Args:
            particle_id: ID of the particle to modify
            fixed: Whether the particle should be fixed
        """
        if 0 <= particle_id < len(self.particles):
            self.particles[particle_id]["fixed"] = fixed
    
    def apply_magical_impulse(self):
        """Apply a magical, ethereal impulse to the slime."""
        if len(self.particles) == 0:
            return
            
        # Get core particle
        core = self.particles[0]
        
        # Create a magical upward-biased impulse
        angle = random.uniform(-math.pi * 0.7, -math.pi * 0.3)  # Mostly upward
        strength = 3.0 + random.uniform(0, 2.0)
        
        impulse = np.array([
            math.cos(angle) * strength,
            math.sin(angle) * strength
        ], dtype=float)
        
        # Apply to core with high strength
        core["force"] += impulse * 2.0
        
        # Apply varied impulses to other particles
        for particle in self.particles[1:]:
            # Variation in angle
            p_angle = angle + random.uniform(-0.5, 0.5)
            p_strength = strength * random.uniform(0.5, 1.5)
            
            p_impulse = np.array([
                math.cos(p_angle) * p_strength,
                math.sin(p_angle) * p_strength
            ], dtype=float)
            
            particle["force"] += p_impulse
        
        self.logger.debug("Applied magical impulse")