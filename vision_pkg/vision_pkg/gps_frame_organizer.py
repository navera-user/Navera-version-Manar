"""
GPS Frame Organizer
─────────────────────────────────────────────────────────────────────────────
Organizes received image frames into GPS/no-GPS folders based on CSV metadata.

Usage:
    organizer = FrameOrganizer(
        frames_gps_dir="~/isaac_ros_common/vision_pkg/vision_pkg/dataset/frames_gps",
        frames_nogps_dir="~/isaac_ros_common/vision_pkg/vision_pkg/dataset/frames_nogps"
    )
    organizer.process_frame(filename, img_bytes, lat, lon)
"""

import math
from pathlib import Path


def is_nan(value) -> bool:
    """Check if value is NaN (handles None, float NaN, string 'nan', etc.)"""
    if value is None:
        return True
    try:
        return math.isnan(float(value))
    except (TypeError, ValueError):
        return str(value).lower().strip() in ("nan", "none", "null", "")


class FrameOrganizer:
    """Organizes frames into GPS/no-GPS folders based on GPS coordinates."""
    
    def __init__(self, frames_gps_dir: str, frames_nogps_dir: str):
        """
        Initialize organizer with folder paths.
        
        Args:
            frames_gps_dir: Directory for frames with valid GPS coordinates
            frames_nogps_dir: Directory for frames without valid GPS coordinates
        """
        self.gps_dir = Path(frames_gps_dir).expanduser()
        self.nogps_dir = Path(frames_nogps_dir).expanduser()
        
        # Create directories if they don't exist
        self.gps_dir.mkdir(parents=True, exist_ok=True)
        self.nogps_dir.mkdir(parents=True, exist_ok=True)
    
    def process_frame(self, filename: str, img_bytes: bytes, lat, lon) -> dict:
        """
        Save image frame to appropriate folder based on GPS validity.
        
        Args:
            filename: Original image filename (e.g., "frame_0001.jpg")
            img_bytes: Image data as bytes
            lat: Latitude (float or any value that might be NaN)
            lon: Longitude (float or any value that might be NaN)
        
        Returns:
            dict with keys:
                - 'saved': bool (True if saved successfully)
                - 'path': str (path where image was saved)
                - 'folder': str ('gps' or 'nogps')
                - 'message': str (log message)
        """
        has_gps = not (is_nan(lat) or is_nan(lon))
        
        target_dir = self.gps_dir if has_gps else self.nogps_dir
        folder_label = "GPS" if has_gps else "NO GPS"
        target_path = target_dir / filename
        
        try:
            target_path.write_bytes(img_bytes)
            message = f"Saved {filename} → {folder_label} folder"
            print(message)
            
            return {
                "saved": True,
                "path": str(target_path),
                "folder": "gps" if has_gps else "nogps",
                "message": message
            }
        
        except Exception as e:
            message = f"ERROR saving {filename}: {e}"
            print(message)
            
            return {
                "saved": False,
                "path": str(target_path),
                "folder": "gps" if has_gps else "nogps",
                "message": message
            }


def process_csv_and_organize_frames(
    csv_path: str,
    frames_dir: str,
    frames_gps_dir: str,
    frames_nogps_dir: str,
    lat_column: str = "lat",
    lon_column: str = "lon",
    filename_column: str = "filename"
) -> dict:
    """
    Process CSV file and organize images based on GPS coordinates.
    
    This function:
    1. Reads CSV file with image metadata
    2. For each row, looks for corresponding image file in frames_dir
    3. Copies image to appropriate GPS/no-GPS folder
    4. Returns summary statistics
    
    Args:
        csv_path: Path to CSV file with columns: filename, lat, lon
        frames_dir: Directory containing original image files
        frames_gps_dir: Target directory for GPS-tagged frames
        frames_nogps_dir: Target directory for frames without GPS
        lat_column: CSV column name for latitude (default: "lat")
        lon_column: CSV column name for longitude (default: "lon")
        filename_column: CSV column name for filename (default: "filename")
    
    Returns:
        dict with keys:
            - 'total': int (total frames processed)
            - 'saved_gps': int (frames saved to GPS folder)
            - 'saved_nogps': int (frames saved to no-GPS folder)
            - 'failed': int (frames that failed to save)
            - 'errors': list[str] (error messages)
    """
    try:
        import csv
    except ImportError:
        raise ImportError("csv module is required")
    
    csv_file = Path(csv_path).expanduser()
    frames_source_dir = Path(frames_dir).expanduser()
    organizer = FrameOrganizer(frames_gps_dir, frames_nogps_dir)
    
    stats = {
        "total": 0,
        "saved_gps": 0,
        "saved_nogps": 0,
        "failed": 0,
        "errors": []
    }
    
    if not csv_file.exists():
        stats["errors"].append(f"CSV file not found: {csv_path}")
        return stats
    
    try:
        with open(csv_file, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            if reader.fieldnames is None or filename_column not in reader.fieldnames:
                error = f"CSV missing '{filename_column}' column. Available: {reader.fieldnames}"
                stats["errors"].append(error)
                return stats
            
            for row in reader:
                stats["total"] += 1
                
                try:
                    filename = row.get(filename_column, "").strip()
                    lat = row.get(lat_column, "")
                    lon = row.get(lon_column, "")
                    
                    if not filename:
                        stats["errors"].append(f"Row {stats['total']}: empty filename")
                        stats["failed"] += 1
                        continue
                    
                    # Find image file
                    img_path = frames_source_dir / filename
                    if not img_path.exists():
                        stats["errors"].append(f"Image not found: {filename}")
                        stats["failed"] += 1
                        continue
                    
                    # Read image bytes
                    img_bytes = img_path.read_bytes()
                    
                    # Process and organize
                    result = organizer.process_frame(filename, img_bytes, lat, lon)
                    
                    if result["saved"]:
                        if result["folder"] == "gps":
                            stats["saved_gps"] += 1
                        else:
                            stats["saved_nogps"] += 1
                    else:
                        stats["failed"] += 1
                        stats["errors"].append(result["message"])
                
                except Exception as e:
                    stats["errors"].append(f"Row {stats['total']}: {e}")
                    stats["failed"] += 1
    
    except Exception as e:
        stats["errors"].append(f"CSV processing error: {e}")
    
    return stats
