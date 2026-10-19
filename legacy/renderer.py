"""
Kovrycha - Desktop Slime Assistant (Enhanced)
Renderer Module - Fixed Version

This module handles the visual representation of Kovrycha,
creating a translucent overlay and rendering the slime using OpenGL.
Focus on creating an ethereal, magical appearance with advanced effects.
"""

import os
import time
import logging
import numpy as np
import math
import random
from typing import Dict, Tuple, List, Any, Optional

import win32api
import win32con
import win32gui
import win32ui
from ctypes import windll, c_void_p, c_int, byref, sizeof

# Define OpenGL WGL constants that are not in win32con
WGL_CONTEXT_MAJOR_VERSION_ARB = 0x2091
WGL_CONTEXT_MINOR_VERSION_ARB = 0x2092
WGL_CONTEXT_FLAGS_ARB = 0x2094
WGL_CONTEXT_DEBUG_BIT_ARB = 0x0001
WGL_CONTEXT_FORWARD_COMPATIBLE_BIT_ARB = 0x0002
WGL_CONTEXT_PROFILE_MASK_ARB = 0x9126
WGL_CONTEXT_CORE_PROFILE_BIT_ARB = 0x00000001

# Import OpenGL after constants are defined
from OpenGL.GL import *
from OpenGL.WGL import *
from OpenGL.GL import shaders


class SlimeRenderer:
    """
    Enhanced renderer for Kovrycha slime, using OpenGL for efficient procedural rendering.
    Creates a transparent, click-through overlay window that spans across monitors.
    Implements advanced visual effects for a magical, ethereal appearance.
    """
    
    def __init__(self, screen_manager, physics_engine, config: Dict[str, Any], events=None):
        self.logger = logging.getLogger("Kovrycha.Renderer")
        self.screen_manager = screen_manager
        self.physics = physics_engine
        self.config = config
        self.events = events
        
        # Rendering state
        self.window_handle = None
        self.gl_context = None
        self.device_context = None
        self.gl_initialized = False
        self.shader_program = None
        self.vao = None
        self.vbo = None
        self.running = True
        self.last_render_time = 0
        self.frame_count = 0
        self.fps = 0
        self.fps_update_time = 0
        
        # Visual configuration
        self.base_color = config.get("base_color", (0.5, 0.1, 0.9))  # Deep purple
        self.accent_colors = config.get("accent_colors", [
            (0.1, 0.8, 0.3),  # Green accent
            (0.9, 0.2, 0.7)   # Pink accent
        ])
        self.current_color = self.base_color
        self.color_state = 0.0  # Transition between colors
        self.pulse_speed = config.get("pulse_speed", 0.5)
        self.glow_intensity = config.get("glow_intensity", 0.7)
        self.quality = config.get("quality", "high")
        self.effects_level = config.get("effects_level", 2)
        
        # Animation state
        self.time = 0.0
        self.pulse = 0.0
        self.ripple_effects = []
        
        # Register event handlers
        if self.events:
            self.events.register("pulse", self._on_pulse_event)
            self.events.register("mood_change", self._on_mood_change)
        
        self.logger.info("Renderer initialized")
    
    def initialize(self):
        """Initialize the renderer and create the overlay window."""
        self.logger.info("Creating overlay window")
        
        try:
            # Register window class
            wc = win32gui.WNDCLASS()
            wc.style = win32con.CS_HREDRAW | win32con.CS_VREDRAW | win32con.CS_OWNDC
            wc.lpfnWndProc = self._wnd_proc
            wc.cbWndExtra = 0
            wc.hInstance = win32api.GetModuleHandle(None)
            wc.hIcon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)
            wc.hCursor = win32gui.LoadCursor(0, win32con.IDC_ARROW)
            wc.hbrBackground = win32gui.GetStockObject(win32con.BLACK_BRUSH)
            wc.lpszClassName = "KovrychaSurface"
            
            # Register class
            win32gui.RegisterClass(wc)
            
            # Get primary monitor dimensions
            primary = self.screen_manager.get_primary_monitor()
            
            # Extended window styles for layered, transparent, click-through window
            ex_style = (
                win32con.WS_EX_LAYERED |     # For transparency
                win32con.WS_EX_TOPMOST |     # Always on top
                win32con.WS_EX_TRANSPARENT | # Click-through
                win32con.WS_EX_NOACTIVATE    # Don't activate when clicked
            )
            
            # Create the window
            self.window_handle = win32gui.CreateWindowEx(
                ex_style,
                wc.lpszClassName,
                "Kovrycha",
                win32con.WS_POPUP,  # No border, title bar, or buttons
                primary["left"], primary["top"],  # Position
                primary["width"], primary["height"],  # Size
                0, 0,  # No parent window or menu
                wc.hInstance,
                None
            )
            
            if not self.window_handle:
                raise Exception("Failed to create window")
            
            # Make the window transparent (black becomes transparent)
            win32gui.SetLayeredWindowAttributes(
                self.window_handle,
                win32api.RGB(0, 0, 0),  # Color key (black)
                0,  # Alpha (not used with LWA_COLORKEY)
                win32con.LWA_COLORKEY
            )
            
            # Initialize OpenGL
            self._init_opengl()
            
            # Show the window
            win32gui.ShowWindow(self.window_handle, win32con.SW_SHOW)
            win32gui.UpdateWindow(self.window_handle)
            
            self.logger.info("Overlay window created successfully")
            
        except Exception as e:
            self.logger.error(f"Error creating overlay window: {e}", exc_info=True)
            if self.events:
                self.events.emit("app_error", {
                    "thread": "renderer", 
                    "error": str(e),
                    "fatal": True
                })
            raise
    
    def _init_opengl(self):
        """Initialize OpenGL with advanced context and resources."""
        try:
            # Get device context
            self.device_context = win32gui.GetDC(self.window_handle)
            
            # Setup pixel format for OpenGL
            pfd = win32gui.PIXELFORMATDESCRIPTOR()
            pfd.dwFlags = win32con.PFD_DRAW_TO_WINDOW | win32con.PFD_SUPPORT_OPENGL | win32con.PFD_DOUBLEBUFFER
            pfd.iPixelType = win32con.PFD_TYPE_RGBA
            pfd.cColorBits = 32
            pfd.cDepthBits = 24
            pfd.cStencilBits = 8
            pfd.iLayerType = win32con.PFD_MAIN_PLANE
            
            pixel_format = win32gui.ChoosePixelFormat(self.device_context, pfd)
            win32gui.SetPixelFormat(self.device_context, pixel_format, pfd)
            
            # Create standard OpenGL context
            self.gl_context = wglCreateContext(self.device_context)
            wglMakeCurrent(self.device_context, self.gl_context)
            
            # Try to create modern OpenGL context (if supported)
            try:
                # Check if we can get the wglCreateContextAttribsARB function
                wglCreateContextAttribsARB = wglGetProcAddress(b"wglCreateContextAttribsARB")
                
                if wglCreateContextAttribsARB:
                    # Define attributes for modern context
                    attribs = [
                        WGL_CONTEXT_MAJOR_VERSION_ARB, 3,
                        WGL_CONTEXT_MINOR_VERSION_ARB, 3,
                        WGL_CONTEXT_FLAGS_ARB, WGL_CONTEXT_FORWARD_COMPATIBLE_BIT_ARB,
                        WGL_CONTEXT_PROFILE_MASK_ARB, WGL_CONTEXT_CORE_PROFILE_BIT_ARB,
                        0
                    ]
                    
                    # Convert to ctypes array
                    attribs_array = (c_int * len(attribs))(*attribs)
                    
                    # Create modern context
                    modern_context = wglCreateContextAttribsARB(self.device_context, 0, attribs_array)
                    
                    if modern_context:
                        # Release standard context and use modern one
                        wglMakeCurrent(None, None)
                        wglDeleteContext(self.gl_context)
                        self.gl_context = modern_context
                        wglMakeCurrent(self.device_context, self.gl_context)
                        self.logger.info("Created modern OpenGL context")
            except Exception as e:
                self.logger.warning(f"Could not create modern OpenGL context: {e}")
                self.logger.info("Using standard OpenGL context")
            
            # Initialize OpenGL state
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            
            # Create shader program
            self._create_shaders()
            
            # Create VAO and VBO for quad rendering
            self._create_buffers()
            
            self.gl_initialized = True
            self.logger.info(f"OpenGL initialized: {glGetString(GL_VERSION).decode()}")
            
        except Exception as e:
            self.logger.error(f"Error initializing OpenGL: {e}", exc_info=True)
            if hasattr(self, 'gl_context') and self.gl_context:
                wglMakeCurrent(None, None)
                wglDeleteContext(self.gl_context)
            if self.events:
                self.events.emit("app_error", {
                    "thread": "renderer", 
                    "error": f"OpenGL error: {str(e)}",
                    "fatal": True
                })
            raise
    
    def _create_buffers(self):
        """Create VAO and VBO for quad rendering."""
        # Create full-screen quad vertices (NDC)
        vertices = np.array([
            # positions
            -1.0, -1.0,
             1.0, -1.0,
             1.0,  1.0,
             1.0,  1.0,
            -1.0,  1.0,
            -1.0, -1.0
        ], dtype=np.float32)
        
        # Generate VAO and VBO
        self.vao = glGenVertexArrays(1)
        self.vbo = glGenBuffers(1)
        
        # Bind VAO first
        glBindVertexArray(self.vao)
        
        # Bind and set VBO
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)
        
        # Configure vertex attributes
        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 2 * sizeof(c_float), c_void_p(0))
        glEnableVertexAttribArray(0)
        
        # Unbind
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        glBindVertexArray(0)
    
    def _create_shaders(self):
        """Create advanced GLSL shaders for rendering the slime with ethereal effects."""
        vertex_shader = """
        #version 330 core
        layout(location = 0) in vec2 aPos;
        
        out vec2 TexCoords;
        
        void main() {
            TexCoords = (aPos + 1.0) / 2.0;
            gl_Position = vec4(aPos, 0.0, 1.0);
        }
        """
        
        fragment_shader = """
        #version 330 core
        out vec4 FragColor;
        in vec2 TexCoords;
        
        uniform vec2 resolution;
        uniform float time;
        uniform vec3 baseColor;
        uniform vec3 accentColor1;
        uniform vec3 accentColor2;
        uniform float colorState;
        uniform float pulseValue;
        uniform float glowIntensity;
        uniform int effectsLevel;
        uniform vec4 metaballs[32];  // xyz = position, w = radius
        uniform int metaballCount;
        uniform vec3 ripples[10];    // xy = position, z = age
        uniform int rippleCount;
        uniform int mood;            // 0=calm, 1=playful, 2=sleepy, 3=excited
        
        // Noise function for organic look
        float hash(vec2 p) {
            return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
        }
        
        // Improved metaball field function
        float metaballField(vec2 pos) {
            float sum = 0.0;
            
            for (int i = 0; i < metaballCount; i++) {
                vec2 metaPos = metaballs[i].xy / resolution;
                float radius = metaballs[i].w / 100.0;
                
                // Improved falloff function (smoother boundaries)
                float dist = distance(pos, metaPos);
                sum += radius * radius / (dist * dist + 0.01);
            }
            
            return sum;
        }
        
        // Ripple effect function
        float rippleEffect(vec2 pos) {
            float ripple = 0.0;
            
            for (int i = 0; i < rippleCount; i++) {
                vec2 ripplePos = ripples[i].xy / resolution;
                float age = ripples[i].z;
                
                // Ripple radius based on age
                float radius = age * 0.2;
                float falloff = 1.0 - min(1.0, age * 0.5);
                
                // Calculate ripple value
                float dist = distance(pos, ripplePos);
                float ring = smoothstep(radius - 0.01, radius, dist) - 
                             smoothstep(radius, radius + 0.01, dist);
                
                ripple += ring * falloff * 0.3;
            }
            
            return ripple;
        }
        
        // Edge glow effect
        float edgeGlow(float field, float threshold) {
            // Create a subtle glow at the edges
            float edge = smoothstep(threshold, threshold + 0.1, field);
            return (1.0 - edge) * 0.5;
        }
        
        void main() {
            // Convert to fragment coordinates
            vec2 pos = TexCoords;
            
            // Calculate metaball field
            float field = metaballField(pos);
            
            // Threshold for rendering (base visibility boundary)
            float threshold = 1.0;
            
            // Early discard for efficiency
            if (field < threshold - 0.2) {
                discard;  // Outside the slime with extra margin
            }
            
            // Interpolate between colors based on colorState
            vec3 color;
            if (colorState < 0.5) {
                // Interpolate between base color and accent color 1
                float t = colorState * 2.0;
                color = mix(baseColor, accentColor1, t);
            } else {
                // Interpolate between accent color 1 and accent color 2
                float t = (colorState - 0.5) * 2.0;
                color = mix(accentColor1, accentColor2, t);
            }
            
            // Add mood-based color modulation
            if (mood == 1) {  // Playful
                // Slightly brighter and more saturated
                color *= 1.1;
            } else if (mood == 2) {  // Sleepy
                // Darker and less saturated
                color *= 0.8;
                color = mix(color, vec3(length(color)), 0.2);  // Desaturate a bit
            } else if (mood == 3) {  // Excited
                // Vibrant and pulsating
                color *= 1.0 + 0.2 * sin(time * 5.0);
            }
            
            // Add pulsing glow effect
            float pulse = pulseValue;
            float glow = min(1.0, field - threshold);
            color += glow * glowIntensity * pulse * 0.3;
            
            // Add edge highlight for ethereal effect
            float edge = edgeGlow(field, threshold);
            color += edge * (0.8 + 0.2 * sin(time * 2.0));
            
            // Add ripple effects if enabled
            if (effectsLevel >= 2 && rippleCount > 0) {
                float ripple = rippleEffect(pos);
                color += ripple * vec3(0.5, 0.7, 1.0);
            }
            
            // Add subtle noise texture for organic feel
            if (effectsLevel >= 1) {
                float noise = hash(pos * 20.0 + time * 0.1) * 0.03;
                color += noise;
            }
            
            // Magical inner glow effect
            if (effectsLevel >= 3) {
                // Inner light that moves around based on time
                vec2 lightPos = vec2(
                    0.5 + 0.2 * sin(time * 0.7),
                    0.5 + 0.2 * cos(time * 0.5)
                );
                float innerGlow = max(0.0, 1.0 - distance(pos, lightPos) * 2.0);
                innerGlow = pow(innerGlow, 3.0) * 0.3;
                color += innerGlow * mix(vec3(1.0, 0.7, 0.9), vec3(0.7, 1.0, 0.9), sin(time) * 0.5 + 0.5);
            }
            
            // Calculate alpha based on field strength with smoother falloff
            float alpha = smoothstep(threshold - 0.1, threshold + 0.5, field);
            alpha = min(0.9, alpha); // Cap maximum opacity for translucency
            
            // Output final color
            FragColor = vec4(color, alpha);
        }
        """
        
        # Compile shaders
        try:
            vertex = shaders.compileShader(vertex_shader, GL_VERTEX_SHADER)
            fragment = shaders.compileShader(fragment_shader, GL_FRAGMENT_SHADER)
            
            # Create shader program
            self.shader_program = shaders.compileProgram(vertex, fragment)
            
            # Initialize uniforms
            self._update_shader_uniforms()
            
            self.logger.info("Shaders compiled successfully")
            
        except Exception as e:
            self.logger.error(f"Shader compilation error: {e}", exc_info=True)
            if self.events:
                self.events.emit("app_error", {
                    "thread": "renderer", 
                    "error": f"Shader error: {str(e)}"
                })
            raise
    
    def _update_shader_uniforms(self):
        """Update all shader uniforms."""
        if not self.shader_program:
            return
            
        # Use the shader program
        glUseProgram(self.shader_program)
        
        # Monitor size
        primary = self.screen_manager.get_primary_monitor()
        resolution = (primary["width"], primary["height"])
        
        # Update static uniforms
        glUniform2f(glGetUniformLocation(self.shader_program, "resolution"), *resolution)
        glUniform3f(glGetUniformLocation(self.shader_program, "baseColor"), *self.base_color)
        glUniform3f(glGetUniformLocation(self.shader_program, "accentColor1"), *self.accent_colors[0])
        glUniform3f(glGetUniformLocation(self.shader_program, "accentColor2"), *self.accent_colors[1])
        glUniform1f(glGetUniformLocation(self.shader_program, "colorState"), self.color_state)
        glUniform1f(glGetUniformLocation(self.shader_program, "glowIntensity"), self.glow_intensity)
        glUniform1i(glGetUniformLocation(self.shader_program, "effectsLevel"), self.effects_level)
        
        # Mood value (0=calm, 1=playful, 2=sleepy, 3=excited)
        mood_values = {"calm": 0, "playful": 1, "sleepy": 2, "excited": 3}
        mood_value = mood_values.get("calm", 0)  # Default to calm
        glUniform1i(glGetUniformLocation(self.shader_program, "mood"), mood_value)
    
    def _update_ripples(self):
        """Update ripple effects."""
        # Update existing ripples
        updated_ripples = []
        for ripple in self.ripple_effects:
            # Increment age
            ripple[2] += 0.05
            
            # Keep only active ripples
            if ripple[2] < 2.0:
                updated_ripples.append(ripple)
                
        self.ripple_effects = updated_ripples
        
        # Randomly add new ripples based on mood
        if random.random() < 0.01:
            # Get a random particle position
            particles = self.physics.get_particles()
            if particles:
                particle = random.choice(particles)
                pos = particle["position"]
                
                # Add new ripple at this position
                self.ripple_effects.append([pos[0], pos[1], 0.0])
                
                # Limit number of ripples
                if len(self.ripple_effects) > 10:
                    self.ripple_effects.pop(0)
    
    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        """Window procedure to handle window messages."""
        if msg == win32con.WM_DESTROY:
            self.running = False
            win32gui.PostQuitMessage(0)
            return 0
        
        elif msg == win32con.WM_SIZE:
            if self.gl_initialized:
                width = win32api.LOWORD(lparam)
                height = win32api.HIWORD(lparam)
                glViewport(0, 0, width, height)
        
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)
    
    def update_color(self, color_state: float):
        """
        Update the color transition state.
        
        Args:
            color_state: Value between 0.0 and 1.0 indicating the color transition
                        (0.0 = purple, 0.5 = green, 1.0 = pink)
        """
        self.color_state = max(0.0, min(1.0, color_state))
        
        if self.shader_program:
            glUseProgram(self.shader_program)
            glUniform1f(
                glGetUniformLocation(self.shader_program, "colorState"), 
                self.color_state
            )
    
    def _on_pulse_event(self, data: Dict[str, Any]):
        """Handle pulse events for animation."""
        self.pulse = data.get("value", 0.0)
        
        if self.shader_program:
            glUseProgram(self.shader_program)
            glUniform1f(
                glGetUniformLocation(self.shader_program, "pulseValue"), 
                self.pulse
            )
    
    def _on_mood_change(self, data: Dict[str, Any]):
        """Handle mood change events."""
        mood = data.get("mood", "calm")
        
        if self.shader_program:
            glUseProgram(self.shader_program)
            
            # Mood value (0=calm, 1=playful, 2=sleepy, 3=excited)
            mood_values = {"calm": 0, "playful": 1, "sleepy": 2, "excited": 3}
            mood_value = mood_values.get(mood, 0)
            
            glUniform1i(glGetUniformLocation(self.shader_program, "mood"), mood_value)
    
    def render_frame(self):
        """Render a single frame of the slime animation."""
        if not self.gl_initialized or not self.running:
            return False
        
        try:
            # Calculate FPS
            current_time = time.time()
            self.frame_count += 1
            
            if current_time - self.fps_update_time >= 1.0:
                self.fps = self.frame_count
                self.frame_count = 0
                self.fps_update_time = current_time
                
            # Update time
            self.time = current_time
                
            # Clear the window
            glClearColor(0.0, 0.0, 0.0, 0.0)
            glClear(GL_COLOR_BUFFER_BIT)
            
            # Use the shader program
            glUseProgram(self.shader_program)
            
            # Update time uniform
            glUniform1f(
                glGetUniformLocation(self.shader_program, "time"),
                self.time
            )
            
            # Update ripple effects
            self._update_ripples()
            
            # Update metaball positions from physics engine
            particles = self.physics.get_particles()
            metaball_count = min(32, len(particles))
            
            # Prepare metaball data
            metaball_data = np.zeros(32 * 4, dtype=np.float32)
            for i, particle in enumerate(particles[:metaball_count]):
                pos = particle["position"]
                radius = particle["radius"]
                metaball_data[i*4:i*4+4] = [pos[0], pos[1], 0.0, radius]
                
            # Update metaball uniform
            glUniform4fv(
                glGetUniformLocation(self.shader_program, "metaballs"),
                32,
                metaball_data
            )
            glUniform1i(
                glGetUniformLocation(self.shader_program, "metaballCount"),
                metaball_count
            )
            
            # Update ripple data
            ripple_data = np.zeros(10 * 3, dtype=np.float32)
            for i, ripple in enumerate(self.ripple_effects[:10]):
                ripple_data[i*3:i*3+3] = ripple
                
            # Update ripple uniform
            glUniform3fv(
                glGetUniformLocation(self.shader_program, "ripples"),
                10,
                ripple_data
            )
            glUniform1i(
                glGetUniformLocation(self.shader_program, "rippleCount"),
                len(self.ripple_effects)
            )
            
            # Draw fullscreen quad
            glBindVertexArray(self.vao)
            glDrawArrays(GL_TRIANGLES, 0, 6)
            glBindVertexArray(0)
            
            # Swap buffers
            SwapBuffers(self.device_context)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error in render frame: {e}", exc_info=True)
            if self.events:
                self.events.emit("app_error", {"thread": "renderer", "error": str(e)})
            return False
    
    def run(self):
        """Run the main rendering loop."""
        self.logger.info("Starting render loop")
        
        try:
            # Main message loop
            while self.running:
                # Process all available messages
                while True:
                    msg = win32gui.PeekMessage(self.window_handle, 0, 0, 0)
                    if msg[0] == 0:
                        break
                    win32gui.TranslateMessage(msg)
                    win32gui.DispatchMessage(msg)
                
                # Render frame
                if not self.render_frame():
                    break
                
                # Cap frame rate to reduce resource usage
                target_fps = self.config.get("fps_limit", 60)
                time.sleep(max(0, 1.0/target_fps - (time.time() - self.time)))
                
        except Exception as e:
            self.logger.error(f"Error in render loop: {e}", exc_info=True)
            if self.events:
                self.events.emit("app_error", {"thread": "renderer", "error": str(e)})
        
        self.logger.info("Render loop stopped")
    
    def cleanup(self):
        """Clean up OpenGL resources and destroy the window."""
        self.logger.info("Cleaning up renderer resources")
        
        self.running = False
        
        try:
            # Make sure the OpenGL context is current before cleanup
            if self.device_context and self.gl_context:
                wglMakeCurrent(self.device_context, self.gl_context)
            
            # Clean up OpenGL resources
            if self.gl_initialized:
                if self.vao:
                    glDeleteVertexArrays(1, [self.vao])
                if self.vbo:
                    glDeleteBuffers(1, [self.vbo])
                if self.shader_program:
                    glDeleteProgram(self.shader_program)
            
            # Release OpenGL context
            if self.device_context and self.gl_context:
                wglMakeCurrent(None, None)
                wglDeleteContext(self.gl_context)
            
            # Release device context
            if self.window_handle and self.device_context:
                win32gui.ReleaseDC(self.window_handle, self.device_context)
            
            # Destroy window
            if self.window_handle:
                win32gui.DestroyWindow(self.window_handle)
                
        except Exception as e:
            self.logger.error(f"Error during renderer cleanup: {e}", exc_info=True)
        
        self.logger.info("Renderer resources cleaned up")