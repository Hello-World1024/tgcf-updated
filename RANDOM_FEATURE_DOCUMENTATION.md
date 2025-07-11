# Random Message Posting Feature Documentation

## Overview

The Random Message Posting feature allows TGCF to automatically post random messages from your source chat history in live mode. This feature works **parallel** to normal live forwarding and is **independent** of the "Forwards per day" limit.

## Key Features

✅ **Parallel Operation**: Works alongside normal live forwarding without interference  
✅ **Independent Limits**: Has its own daily limits separate from regular forwarding  
✅ **Configurable Timing**: Set custom delays between message batches  
✅ **Batch Processing**: Post multiple messages at once for better engagement  
✅ **Source Selection**: Choose which source chats should have random posting  
✅ **Message Deduplication**: Automatically avoids reposting the same messages  
✅ **Plugin Support**: All configured plugins (filters, watermarks, etc.) apply to random messages  
✅ **Visual Indicators**: Random messages are marked with "📱 Random from archive"

## Configuration

### Web UI Configuration

1. **Navigate to Run Page** (🏃 Run):
   - Select "live" mode
   - Scroll down to "Random Message Posting" section
   - Enable the feature with the checkbox

2. **Settings Available**:
   - **Enable Random Message Posting**: Main toggle for the feature
   - **Delay Between Batches**: Time to wait between posting message batches (60-86400 seconds)
   - **Messages Per Batch**: Number of messages to post in each batch (1-50)
   - **Daily Random Message Limit**: Maximum random messages per day per source (0 for unlimited)
   - **Active Sources**: Select which configured source chats should have random posting

3. **Advanced Settings** (🔬 Advanced page):
   - Additional configuration options
   - Reset daily counters button
   - Detailed technical settings

### Configuration Fields

```json
{
  "live": {
    "random_enabled": false,          // Enable/disable the feature
    "random_delay": 300,              // Delay between batches (seconds)
    "random_count": 5,                // Messages per batch
    "random_total_limit": 0,          // Daily limit per source (0 = unlimited)
    "random_active_sources": []       // List of active source IDs
  }
}
```

## How It Works

1. **Message Collection**: 
   - Fetches recent messages from configured source chats
   - Filters out service messages and empty messages
   - Maintains a history of used messages to avoid duplicates

2. **Random Selection**:
   - Randomly selects messages from the available pool
   - Ensures messages haven't been posted before
   - Applies configured batch size

3. **Processing**:
   - Applies all configured plugins (filters, watermarks, etc.)
   - Adds visual indicator "📱 Random from archive"
   - Sends to all configured destinations

4. **Timing Control**:
   - Waits for configured delay between batches
   - Respects daily limits per source
   - Runs continuously in background

## MongoDB Auto-Storage

All random message data is automatically stored in MongoDB:

### Configuration Storage
- Random settings are stored in the main configuration document
- Changes through web UI are automatically persisted
- No manual intervention required

### Runtime Data Storage
- **Message Counters**: Daily count of random messages posted per source
- **Message History**: List of used message IDs to prevent duplicates
- **Automatic Cleanup**: Old message IDs are automatically pruned to prevent memory bloat

### Environment Variables
Required environment variables in `.env`:
```
PASSWORD=your_password
MONGO_CON_STR=mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true&w=majority
```

## Usage Examples

### Basic Setup
1. Configure your regular forwarding connections
2. Enable random posting in Run page
3. Set delay to 1800 seconds (30 minutes)
4. Set 3 messages per batch
5. Select your active sources
6. Start live mode

### Advanced Setup
1. Set daily limit to 50 messages per source
2. Use shorter delays (300 seconds) for more frequent posting
3. Configure watermarks for random messages
4. Use filters to control which messages get randomly posted

## Technical Details

### File Structure
```
tgcf/
├── random_handler.py           # Main random message handler
├── config.py                   # Configuration with random settings
├── live.py                     # Integration with live mode
├── storage.py                  # Storage for counters and history
└── web_ui/pages/
    ├── 5_🏃_Run.py             # Main UI for random settings
    └── 6_🔬_Advanced.py        # Advanced random settings
```

### Architecture
- **RandomMessageHandler**: Async handler for posting random messages
- **Parallel Processing**: Runs alongside normal live forwarding
- **MongoDB Integration**: Automatic storage of all settings and data
- **Plugin System**: Full integration with existing plugin system

## Deployment

### Docker Deployment
```bash
# Build the image
docker build -t tgcf-random .

# Run with environment variables
docker run -d -p 8501:8501 --env-file .env tgcf-random
```

### Environment Setup
Ensure `.env` file contains:
```
PASSWORD=your_secure_password
MONGO_CON_STR=your_mongodb_connection_string
```

## Monitoring and Troubleshooting

### Logs
Random message posting activities are logged with:
- Start/stop of random handlers
- Message posting success/failure
- Daily limit notifications
- Error handling

### Common Issues
1. **No messages being posted**: Check if sources are active and have recent messages
2. **Daily limits reached**: Check logs for limit notifications
3. **MongoDB connection**: Ensure MONGO_CON_STR is correctly set
4. **Plugin conflicts**: Random messages follow same plugin rules as regular messages

### Reset Counters
Use the "Reset Daily Random Counters" button in Advanced settings to reset daily limits.

## Testing

Run the included test script to verify implementation:
```bash
python test_random_feature.py
```

This tests:
- Configuration structure
- Serialization/deserialization
- MongoDB compatibility
- Handler functions

## Support

For issues or questions:
1. Check the logs for error messages
2. Verify MongoDB connection
3. Ensure source chats have accessible message history
4. Review plugin configurations that might filter random messages

---

**Note**: This feature is designed to work seamlessly with existing TGCF functionality. All regular forwarding rules, plugins, and limitations continue to apply to random messages.
