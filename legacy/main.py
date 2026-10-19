#!/usr/bin/env python
"""
Kovrycha Desktop Slime Assistant
Main Entry Point

This script initializes and starts the Kovrycha application.
Run this script to launch Kovrycha.
"""

import os
import sys
import argparse
import logging
import traceback
from typing import Dict, Any

from kovrycha import Kovrycha


def setup_arg_parser() -> argparse.ArgumentParser:
    """Set up command line argument parser."""
    parser = argparse.ArgumentParser(
        description="Kovrycha - The Desktop Slime Assistant",
        epilog="An ethereal, magical desktop companion that roams your screen."
    )
    
    parser.add_argument(
        '--config', '-c',
        help='Path to configuration file',
        type=str,
        default=None
    )
    
    parser.add_argument(
        '--debug', '-d',
        help='Enable debug mode with verbose logging',
        action='store_true'
    )
    
    parser.add_argument(
        '--log', '-l',
        help='Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
    )
    
    parser.add_argument(
        '--log-file',
        help='Path to log file (default is ~/.kovrycha/kovrycha.log)',
        type=str,
        default=None
    )
    
    parser.add_argument(
        '--version', '-v',
        help='Show version information and exit',
        action='store_true'
    )
    
    parser.add_argument(
        '--minimize', '-m',
        help='Start minimized to system tray',
        action='store_true'
    )
    
    return parser


def setup_logging(args: argparse.Namespace) -> None:
    """Set up logging based on command line arguments."""
    # Determine log level
    log_level = getattr(logging, args.log.upper(), logging.INFO)
    if args.debug:
        log_level = logging.DEBUG
    
    # Determine log file path
    if args.log_file:
        log_path = args.log_file
    else:
        log_dir = os.path.join(os.path.expanduser("~"), ".kovrycha")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "kovrycha.log")
    
    # Set up root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Set up console handler
    console = logging.StreamHandler()
    console.setLevel(log_level)
    console.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    root_logger.addHandler(console)
    
    # Set up file handler with rotation
    try:
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            log_path, maxBytes=1024*1024*5, backupCount=5  # 5MB, 5 backups
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        root_logger.addHandler(file_handler)
    except Exception as e:
        logging.warning(f"Could not set up file logging: {e}")
        # Still try to create a basic file handler
        try:
            file_handler = logging.FileHandler(log_path)
            file_handler.setLevel(log_level)
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            root_logger.addHandler(file_handler)
        except Exception as e2:
            logging.error(f"Could not set up any file logging: {e2}")


def show_version() -> None:
    """Display version information."""
    # Version information
    version = "1.0.0"
    release_date = "March 2025"
    
    print(f"Kovrycha Desktop Slime Assistant v{version}")
    print(f"Released: {release_date}")
    print("An ethereal, magical desktop companion that roams your screen.")
    print("\nCreated by Claude AI")
    
    # System information
    import platform
    print(f"\nSystem: {platform.system()} {platform.version()}")
    print(f"Python: {platform.python_version()}")
    
    try:
        # Try to get more detailed Windows version
        if platform.system() == "Windows":
            import ctypes
            class OSVERSIONINFOEXW(ctypes.Structure):
                _fields_ = [
                    ("dwOSVersionInfoSize", ctypes.c_ulong),
                    ("dwMajorVersion", ctypes.c_ulong),
                    ("dwMinorVersion", ctypes.c_ulong),
                    ("dwBuildNumber", ctypes.c_ulong),
                    ("dwPlatformId", ctypes.c_ulong),
                    ("szCSDVersion", ctypes.c_wchar * 128),
                    ("wServicePackMajor", ctypes.c_ushort),
                    ("wServicePackMinor", ctypes.c_ushort),
                    ("wSuiteMask", ctypes.c_ushort),
                    ("wProductType", ctypes.c_byte),
                    ("wReserved", ctypes.c_byte)
                ]
            
            os_info = OSVERSIONINFOEXW()
            os_info.dwOSVersionInfoSize = ctypes.sizeof(os_info)
            retcode = ctypes.windll.Ntdll.RtlGetVersion(ctypes.byref(os_info))
            
            if retcode == 0:  # Success
                print(f"Windows: {os_info.dwMajorVersion}.{os_info.dwMinorVersion}.{os_info.dwBuildNumber}")
    except Exception:
        pass  # Just use the basic version info


def main() -> int:
    """Main entry point for the application."""
    # Parse command line arguments
    parser = setup_arg_parser()
    args = parser.parse_args()
    
    # Show version and exit if requested
    if args.version:
        show_version()
        return 0
    
    # Set up logging
    setup_logging(args)
    
    # Create logger for main script
    logger = logging.getLogger("Kovrycha.Main")
    logger.info("Starting Kovrycha")
    
    try:
        # Create and start Kovrycha
        slime = Kovrycha(config_path=args.config)
        
        # Enable debug mode if requested
        if args.debug:
            slime.state["debug_mode"] = True
            slime._enable_debug_logging()
            logger.info("Debug mode enabled")
        
        # Start minimized if requested
        if args.minimize:
            slime.state["minimized"] = True
            logger.info("Starting minimized")
        
        # Start the application (blocks until exit)
        slime.start()
        
        # Clean exit
        logger.info("Kovrycha exited cleanly")
        return 0
        
    except KeyboardInterrupt:
        logger.info("Kovrycha terminated by user (KeyboardInterrupt)")
        return 0
        
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        
        # Show error dialog if we can import tkinter
        try:
            import tkinter as tk
            from tkinter import messagebox
            
            root = tk.Tk()
            root.withdraw()  # Hide the main window
            
            error_msg = f"Kovrycha encountered a fatal error:\n\n{str(e)}\n\n"
            error_msg += "Please check the log file for details."
            
            messagebox.showerror("Kovrycha Error", error_msg)
            
        except ImportError:
            # Tkinter not available, just print to console
            print(f"\nFATAL ERROR: {e}")
            print("\nStack trace:")
            traceback.print_exc()
            
        return 1


if __name__ == "__main__":
    # Run main function and exit with its return code
    sys.exit(main())