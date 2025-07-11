#!/usr/bin/env python3
"""
Helper script to convert image file to base64 for watermark configuration.
This is useful when you want to store your watermark image directly in MongoDB
without worrying about file storage on platforms like Render/Heroku.
"""

import base64
import sys
import os
from PIL import Image

def convert_image_to_base64(image_path: str) -> str:
    """Convert image file to base64 string."""
    try:
        # Verify file exists
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image file not found: {image_path}")
        
        # Open and validate image
        with Image.open(image_path) as img:
            # Convert to PNG format if needed (for consistency)
            if img.format != 'PNG':
                print(f"Converting {img.format} to PNG format...")
                png_path = image_path.rsplit('.', 1)[0] + '_converted.png'
                img.save(png_path, 'PNG')
                image_path = png_path
        
        # Convert to base64
        with open(image_path, "rb") as img_file:
            base64_data = base64.b64encode(img_file.read()).decode('utf-8')
        
        return base64_data
        
    except Exception as e:
        print(f"Error converting image: {e}")
        return None

def save_base64_to_file(base64_data: str, output_file: str = "watermark_base64.txt"):
    """Save base64 data to a text file."""
    try:
        with open(output_file, "w") as f:
            f.write(base64_data)
        print(f"✅ Base64 data saved to: {output_file}")
        return True
    except Exception as e:
        print(f"Error saving base64 data: {e}")
        return False

def main():
    if len(sys.argv) != 2:
        print("Usage: python convert_image_to_base64.py <image_path>")
        print("Example: python convert_image_to_base64.py watermark.png")
        sys.exit(1)
    
    image_path = sys.argv[1]
    
    print(f"🔄 Converting image to base64: {image_path}")
    
    base64_data = convert_image_to_base64(image_path)
    
    if base64_data:
        print(f"✅ Successfully converted image to base64!")
        print(f"📊 Base64 data length: {len(base64_data)} characters")
        
        # Save to file
        output_file = f"{os.path.splitext(image_path)[0]}_base64.txt"
        save_base64_to_file(base64_data, output_file)
        
        print("\n" + "="*60)
        print("📋 COPY THIS BASE64 DATA TO YOUR WATERMARK CONFIG:")
        print("="*60)
        print(base64_data[:100] + "..." if len(base64_data) > 100 else base64_data)
        print("="*60)
        
        print("\n💡 How to use this base64 data:")
        print("1. Copy the base64 data from the text file")
        print("2. In TGCF web UI, go to Plugins > Watermark")
        print("3. Go to the 'Base64' tab")
        print("4. Paste the base64 data in the text area")
        print("5. Save the configuration")
        print("\n🎯 Benefits:")
        print("✅ Image persists across Render/Heroku deployments")
        print("✅ No need to upload files every time")
        print("✅ Stored directly in MongoDB")
        print("✅ Works on any platform (local, cloud, etc.)")
        
    else:
        print("❌ Failed to convert image to base64")
        sys.exit(1)

if __name__ == "__main__":
    main()
