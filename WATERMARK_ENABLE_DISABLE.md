# Per-Connection Watermark Enable/Disable Feature

## Overview
This feature allows you to enable or disable the watermark plugin for specific connections. Each connection has a simple checkbox to control whether the global watermark settings are applied to that connection.

## How It Works

### 1. Global Watermark Settings
- Configure your watermark settings in the **Plugins** page (image, position, frame rate, etc.)
- These settings are used by all connections that have watermarks enabled

### 2. Per-Connection Control
- Each connection has a checkbox: "Enable watermark plugin for this connection"
- **Checked (default)**: Watermark plugin will be applied using global settings
- **Unchecked**: Watermark plugin will be skipped for this connection

### 3. Usage Steps
1. Go to **Plugins** page and configure your watermark settings globally
2. Go to **Connections** page
3. For each connection, check or uncheck the watermark enable checkbox
4. Save the configuration

## Benefits

✅ **Simple Control**: One checkbox per connection  
✅ **Global Settings**: Configure watermark once, use everywhere  
✅ **Selective Application**: Enable/disable per connection as needed  
✅ **MongoDB Storage**: Settings automatically saved to database  
✅ **No Complexity**: No per-connection image uploads or settings  

## Example Use Cases

1. **Mixed Content**: Enable watermarks for some channels, disable for others
2. **Source Filtering**: Watermark only messages from specific sources
3. **Testing**: Temporarily disable watermarks for certain connections
4. **Copyright Protection**: Apply watermarks selectively based on content sensitivity

## Technical Details

- **Storage**: Checkbox state stored in MongoDB as `watermark_enabled` boolean
- **Plugin Logic**: TgcfMark plugin checks the flag before processing
- **Default Value**: `true` (watermark enabled by default)
- **Fallback**: If setting missing, defaults to enabled

This keeps the watermark feature simple while giving you the control to enable/disable it per connection.
