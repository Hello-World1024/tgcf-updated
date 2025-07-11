import base64
import io
import logging
import os
import shutil
from typing import Any, Dict

import requests
from PIL import Image
from pydantic import BaseModel  # pylint: disable=no-name-in-module
from watermark import File, Position, Watermark, apply_watermark

from tgcf.plugin_models import MarkConfig
from tgcf.plugins import TgcfMessage, TgcfPlugin
from tgcf.utils import cleanup
from tgcf import storage as st


def save_image_to_mongo(image_path: str, image_name: str = "watermark") -> bool:
    """Save optimized image as base64 to MongoDB for persistence."""
    try:
        # Optimize image before saving
        optimized_path = optimize_image_for_render(image_path)
        
        with open(optimized_path, "rb") as img_file:
            image_data = base64.b64encode(img_file.read()).decode('utf-8')
            
        # Store in MongoDB
        if hasattr(st, 'mycol') and st.mycol is not None:
            st.mycol.update_one(
                {"_id": 0},
                {"$set": {f"watermark_images.{image_name}": image_data}},
                upsert=True
            )
            logging.info(f"Optimized watermark '{image_name}' saved to MongoDB (size: {len(image_data)} chars)")
            
            # Clean up optimized file if it's different
            if optimized_path != image_path and os.path.exists(optimized_path):
                os.remove(optimized_path)
            return True
        else:
            # Fallback: store in memory (avoid on Render)
            logging.warning("MongoDB not available, skipping watermark storage")
            return False
    except Exception as e:
        logging.error(f"Failed to save watermark image to MongoDB: {e}")
        return False


def optimize_image_for_render(image_path: str) -> str:
    """Optimize image for Render's memory constraints."""
    try:
        from PIL import Image
        
        with Image.open(image_path) as img:
            # Get original size
            original_size = img.size
            original_format = img.format
            
            # Calculate file size
            file_size = os.path.getsize(image_path)
            
            # If image is already small enough (< 100KB), return as-is
            if file_size < 100 * 1024:  # 100KB
                logging.info(f"Image already optimized: {file_size} bytes")
                return image_path
            
            # Resize if too large (keep aspect ratio)
            max_size = (800, 600)  # Reasonable size for watermarks
            if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                logging.info(f"Resized from {original_size} to {img.size}")
            
            # Convert to RGB if necessary (for JPEG savings)
            if img.mode in ('RGBA', 'LA', 'P'):
                # Keep PNG for transparency
                optimized_path = image_path.replace('.', '_optimized.')
                img.save(optimized_path, 'PNG', optimize=True)
            else:
                # Use JPEG for better compression
                optimized_path = image_path.replace('.', '_optimized.').replace('.png', '.jpg').replace('.jpeg', '.jpg')
                img.convert('RGB').save(optimized_path, 'JPEG', quality=85, optimize=True)
            
            new_size = os.path.getsize(optimized_path)
            logging.info(f"Image optimized: {file_size} -> {new_size} bytes ({(1-new_size/file_size)*100:.1f}% reduction)")
            
            return optimized_path
            
    except Exception as e:
        logging.error(f"Image optimization failed: {e}")
        return image_path  # Return original if optimization fails


def load_image_from_mongo(image_name: str = "watermark") -> str:
    """Load image from MongoDB and save to temporary file."""
    try:
        image_data = None
        
        # Try to load from MongoDB
        if hasattr(st, 'mycol') and st.mycol:
            doc = st.mycol.find_one({"_id": 0})
            if doc and "watermark_images" in doc and image_name in doc["watermark_images"]:
                image_data = doc["watermark_images"][image_name]
        
        # Fallback: try memory storage
        if not image_data and hasattr(st, 'watermark_images') and image_name in st.watermark_images:
            image_data = st.watermark_images[image_name]
        
        if image_data:
            # Decode and save to temporary file
            image_bytes = base64.b64decode(image_data)
            temp_filename = f"temp_{image_name}.png"
            
            with open(temp_filename, "wb") as img_file:
                img_file.write(image_bytes)
            
            logging.info(f"Watermark image '{image_name}' loaded from storage")
            return temp_filename
        else:
            logging.warning(f"Watermark image '{image_name}' not found in storage")
            return None
            
    except Exception as e:
        logging.error(f"Failed to load watermark image from storage: {e}")
        return None


def create_image_from_base64(base64_data: str, filename: str = "watermark.png") -> bool:
    """Create image file from base64 data."""
    try:
        # Remove data URL prefix if present
        if base64_data.startswith('data:image'):
            base64_data = base64_data.split(',')[1]
        
        image_bytes = base64.b64decode(base64_data)
        
        with open(filename, "wb") as img_file:
            img_file.write(image_bytes)
        
        logging.info(f"Created image file from base64 data: {filename}")
        return True
    except Exception as e:
        logging.error(f"Failed to create image from base64: {e}")
        return False


def get_image_as_base64(image_path: str) -> str:
    """Convert image file to base64 string."""
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')
    except Exception as e:
        logging.error(f"Failed to convert image to base64: {e}")
        return None


def download_image(url: str, filename: str = "image.png") -> bool:
    if filename in os.listdir():
        logging.info("Image for watermarking already exists.")
        return True
    try:
        logging.info(f"Downloading image {url}")
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            logging.info("Got Response 200")
            with open(filename, "wb") as file:
                response.raw.decode_content = True
                shutil.copyfileobj(response.raw, file)
    except Exception as err:
        logging.error(err)
        return False
    else:
        logging.info("File created image")
        return True


class TgcfMark(TgcfPlugin):
    id_ = "mark"

    def __init__(self, data) -> None:
        self.data = data

    async def modify(self, tm: TgcfMessage) -> TgcfMessage:
        if not tm.file_type in ["gif", "video", "photo"]:
            return tm
        
        downloaded_file = await tm.get_file()
        base = File(downloaded_file)
        
        overlay_file = None
        
        try:
            # Handle different image sources
            if self.data.image.startswith("https://"):
                # Download from URL
                if download_image(self.data.image, "image.png"):
                    overlay_file = "image.png"
                    # Save downloaded image to MongoDB for future use
                    save_image_to_mongo("image.png", "downloaded_watermark")
                    
            elif self.data.image.startswith("data:image") or len(self.data.image) > 100:
                # Handle base64 data
                temp_filename = "base64_watermark.png"
                if create_image_from_base64(self.data.image, temp_filename):
                    overlay_file = temp_filename
                    # Save to MongoDB
                    save_image_to_mongo(temp_filename, "base64_watermark")
                    
            elif os.path.exists(self.data.image):
                # Use existing file
                overlay_file = self.data.image
                # Save to MongoDB for persistence
                save_image_to_mongo(self.data.image, "local_watermark")
                
            elif self.data.image.startswith("mongodb:"):
                # Load specific image from MongoDB
                image_name = self.data.image.split(":", 1)[1]
                stored_file = load_image_from_mongo(image_name)
                if stored_file:
                    overlay_file = stored_file
                    
            elif self.data.image == "mongodb_stored":
                # Try to load any stored image from MongoDB
                stored_file = load_image_from_mongo("uploaded_watermark")
                if stored_file:
                    overlay_file = stored_file
                elif load_image_from_mongo("downloaded_watermark"):
                    overlay_file = load_image_from_mongo("downloaded_watermark")
                elif load_image_from_mongo("base64_watermark"):
                    overlay_file = load_image_from_mongo("base64_watermark")
                elif load_image_from_mongo("local_watermark"):
                    overlay_file = load_image_from_mongo("local_watermark")
                    
            else:
                # Fallback: try to load from MongoDB storage
                stored_file = load_image_from_mongo("watermark")
                if stored_file:
                    overlay_file = stored_file
                elif load_image_from_mongo("uploaded_watermark"):
                    overlay_file = load_image_from_mongo("uploaded_watermark")
                elif load_image_from_mongo("downloaded_watermark"):
                    overlay_file = load_image_from_mongo("downloaded_watermark")
                elif load_image_from_mongo("base64_watermark"):
                    overlay_file = load_image_from_mongo("base64_watermark")
                elif load_image_from_mongo("local_watermark"):
                    overlay_file = load_image_from_mongo("local_watermark")
            
            if overlay_file and os.path.exists(overlay_file):
                overlay = File(overlay_file)
                wtm = Watermark(overlay, self.data.position)
                tm.new_file = apply_watermark(base, wtm, frame_rate=self.data.frame_rate)
                
                # Clean up temporary files
                if overlay_file.startswith("temp_") or overlay_file in ["base64_watermark.png", "image.png"]:
                    cleanup(overlay_file)
            else:
                logging.warning("No watermark image found. Skipping watermarking.")
                
        except Exception as e:
            logging.error(f"Error in watermarking: {e}")
        
        cleanup(downloaded_file)
        tm.cleanup = True
        return tm
