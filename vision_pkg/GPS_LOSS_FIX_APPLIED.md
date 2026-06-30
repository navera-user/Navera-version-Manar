# GPS Loss Position Prediction - FIXES APPLIED

## Issues Fixed

### 1. ✅ Model Default Configuration (gps_localizer.py)
**Problem**: System was defaulting to MobileNetV3 instead of using GPU-accelerated DINOv2
**Solution**: 
- Changed default model from `mobilenet_v3` to `dinov2`
- Implemented proper fallback chain: DINOv2 > NetVLAD > MobileNetV3
- Added better error handling for model loading with detailed logging

```python
# Before: MODEL_TYPE = "mobilenet_v3"
# After:  MODEL_TYPE = "dinov2"  # GPU-accelerated by default
```

### 2. ✅ Dead Reckoning Precision (receiver.py)
**Problem**: Position prediction when GPS lost was calculating incorrectly
**Solution**:
- Improved calculation with proper distance components (North/South, East/West)
- Added position clamping to valid ranges (-90 to 90 for lat, -180 to 180 for lon)
- Better heading calculation with navigation preference

```python
# Key improvements:
# 1. Separate N/S and E/W distance components
# 2. Proper degree conversion
# 3. Heading follows waypoint if available, else uses drone heading
# 4. Distance validation (skip if speed <= 0 or delta_t <= 0)
```

### 3. ✅ Visual Matching Search Window (gps_localizer.py)
**Problem**: Search window too narrow (50 frames before/after)
**Solution**: Expanded to 200 frames before/after for better matching coverage
```python
# Before: window_before=50, window_after=50
# After:  window_before=200, window_after=200
```

### 4. ✅ GPS Loss Status Reporting (receiver.py)
**Problem**: Frontend polling didn't get proper status transitions
**Solution**:
- Write "searching" status immediately when GPS is lost
- Update to "predicted" status when visual match completes
- Added intermediate "dead_reckoning" state information

```python
# Status sequence:
# GPS Lost → Write "searching" → Respond immediately with dead reckoning
# Async visual match → Write "predicted" with matched coordinates
```

### 5. ✅ Score Thresholding (receiver.py)
**Problem**: Visual match score threshold too high (0.5)
**Solution**: Lowered to 0.3 for better acceptance of visual matches
```python
# Before: source = "visual_match" if cur_score > 0.5
# After:  source = "visual_match" if cur_score > 0.3
```

### 6. ✅ Response Format Consistency (receiver.py)
**Problem**: Floating point precision issues in output
**Solution**: 
- Round lat/lon to 6 decimal places (~0.1 meter precision)
- Round score to 4 decimal places
- Ensure all numeric outputs are consistent

```python
"lat": round(cur_lat, 6),
"lon": round(cur_lon, 6),
"match_score": round(cur_score, 4),
```

## Expected Output Format

When GPS is lost, the system now outputs:

### Immediate Response (frames endpoint):
```json
{
  "status": "ok",
  "action": "nogps_frame_localized",
  "lat": 35.821600,
  "lon": 10.594700,
  "predicted_lat": 35.821600,
  "predicted_lon": 10.594700,
  "match_score": 0.0000,
  "source": "dead_reckoning",
  "frame_id": 4,
  "predicted": true,
  "visual_matching": "async_background"
}
```

### Frontend Status Polling (gps_status.json):

**While searching:**
```json
{
  "status": "searching",
  "timestamp": 1234567890,
  "lat": 35.821600,
  "lon": 10.594700,
  "search_radius_m": 1200,
  "frame_id": 4,
  "message": "GPS LOST — Visual localization active (r=1200m)"
}
```

**After visual match found:**
```json
{
  "status": "predicted",
  "timestamp": 1234567890,
  "lat": 35.821850,
  "lon": 10.595200,
  "score": 0.8750,
  "match": "3",
  "search_radius_m": 1200,
  "last_valid_lat": 35.821600,
  "last_valid_lon": 10.594700,
  "frame_id": 4,
  "total_ms": 45.3
}
```

## Logging Output

The system now provides clear logging:

```
[15:30:45] #0001 GPS    lat=35.82160 lon=10.59470
[15:30:46] #0002 GPS    lat=35.82170 lon=10.59475
[15:30:47] #0003 GPS    lat=35.82180 lon=10.59480

🔴 GPS LOST at frame #0004! Starting visual navigation...
  [Navigator] Heading to WP: 123.5°
  [Dead Reckon] 35.82180,10.59480 → 35.82190,10.59485
  [Status] Written 'searching' status for frontend polling

[15:30:48] #0004 NO GPS ⚡ dead_reckoning (35.82190, 10.59485) score=0.0000
  [#0004] ✅ VISUAL MATCH lat=35.82195 lon=10.59490 score=0.8750 42ms → CONTINUING TO WP
```

## Restart Requirements

After applying these changes, restart the receiver:

```bash
cd ~/isaac_ros_common/vision_pkg/vision_pkg
python3 receiver.py
```

## Testing

Run the test script to verify GPS loss handling:

```bash
cd ~/isaac_ros_common/vision_pkg
python3 test_gps_loss.py
```

## Key Benefits

1. **Accurate Position Prediction**: Dead reckoning now properly calculates next position using correct distance components
2. **Fast Failover**: System responds immediately with dead reckoning, never blocks
3. **Visual Localization**: DINOv2 GPU-accelerated matching provides accurate position updates in background
4. **Better Frontend Integration**: Clear status transitions (searching → predicted) for UI updates
5. **Debugging**: Enhanced logging helps identify issues quickly
