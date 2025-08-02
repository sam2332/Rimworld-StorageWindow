# StorageWindow Mod - Implementation Summary

## Version History

### Performance & Behavior Fix - Auto-Forward Timing Issues

**Date**: Current Session  
**Critical Issues Fixed**: 
- **Problem**: Pawns were repeatedly picking up and dropping items due to too-frequent auto-forwarding attempts
- **Root Cause**: Auto-forward system was running every 1 second (60 ticks) with no cooldown between job creations
- **Solution**: Implemented proper timing controls and job spacing to prevent spam behavior

**Key Changes**:
```csharp
// Increased interval from 60 to 300 ticks (1 second → 5 seconds)
private int ticksUntilAutoForward = 300;

// Added cooldown tracking to prevent job spam
private int ticksSinceLastJobCreated = 0;
private const int MIN_TICKS_BETWEEN_JOBS = 300; // Minimum 5 seconds between creating jobs

// Only create jobs if enough time has passed since last attempt
if (ticksSinceLastJobCreated >= MIN_TICKS_BETWEEN_JOBS)
{
    TryAutoForwardItems();
}
```

**Additional Improvements**:
- Better reservation checking using `FirstRespectedReserver` instead of `IsReservedByAnyoneOf`
- More comprehensive hauler validation with distance limits (30 tiles max)
- Proper job return value handling to track successful job creation
- Enhanced user feedback showing next auto-forward timing

### Critical Bug Fix - Infinite Hauling Loop

**Date**: Previous Session  
**Critical Issue Fixed**: 
- **Problem**: Pawns would pick up items from storage windows and immediately put them back in the same window, creating an infinite loop
- **Root Cause**: `StoreUtility.TryFindBestBetterStorageFor` was returning the same storage window as a valid destination
- **Solution**: Added explicit check to prevent hauling to the same storage window that currently holds the item

**Code Changes**:
```csharp
// CRITICAL FIX: Make sure we're not trying to haul to ourselves!
if (haulDestination == this || foundCell == this.Position)
{
    continue; // Skip this item, it would just create a loop
}
```

### Mod Renaming & RimWorld 1.6 Update

**Date**: Current Session  
**Updates Made**:

1. **Mod Renaming from PassThroughWindow to StorageWindow**
   - Updated all namespace references from `PassThroughWindow` to `StorageWindow`
   - Renamed class from `Building_PassThroughWindow` to `Building_StorageWindow`
   - Updated defName in XML from `PassThroughWindow` to `StorageWindow`
   - Renamed all project files and assemblies to use StorageWindow naming
   - Updated AssemblyInfo and project configuration files

2. **Version Compatibility Update**
   - Updated `About.xml` supportedVersions from 1.5 to 1.6
   - Updated `Project.csproj` assembly name from "ModTemplate" to "StorageWindow"
   - Added 1.6 storage group support in `StorageWindow.xml`

3. **Major Routing Optimization Implementation**
   - **Problem Identified**: Storage windows were acting as final storage destinations rather than intermediate transit points
   - **Solution Implemented**: Smart auto-forwarding system based on RimWorld's hauling AI

### Key Features Added

#### Auto-Forwarding System
- **Low Priority Default**: Pass-through windows now default to "Low" storage priority, making them less attractive than proper storage
- **Automatic Item Transfer**: Items placed in pass-through windows are automatically moved to better storage when:
  - Higher priority storage becomes available
  - Colonists with hauling enabled are free
  - Better storage location is accessible

#### Technical Implementation Details

**Building_StorageWindow.cs Enhancements**:
- `Tick()` override: Runs auto-forward check every 60 ticks (1 second)
- `TryAutoForwardItems()`: Scans held items and finds better storage destinations
- `TryCreateAutoForwardJob()`: Creates hauling jobs for available colonists
- `FindAvailableHauler()`: Intelligently selects the best colonist for the job
- `GetInspectString()`: Provides user feedback about storage window behavior

**XML Configuration Updates**:
- Added `defaultStorageSettings` with Low priority in `StorageWindow.xml`
- Maintains backward compatibility with existing installations

### How It Works

1. **Initial Placement**: Items are hauled to pass-through windows as intermediate storage
2. **Priority Routing**: RimWorld's hauling system prefers higher-priority destinations
3. **Auto-Forward Trigger**: Every second, the window checks for better storage options
4. **Smart Selection**: System finds the best available storage considering:
   - Storage priority (Critical > Important > Normal > Preferred > Low)
   - Distance from current location
   - Item acceptance filters
   - Colonist availability and pathfinding

### Benefits for Players

- **Improved Flow**: Items naturally flow through windows to final destinations
- **Reduced Micromanagement**: No need to manually set priorities or manage transfers
- **Better Pathfinding**: Colonists use windows as stepping stones for efficient item routing
- **Flexible Usage**: Can still be used as regular storage if desired by changing priority

### Performance Considerations

- **Throttled Processing**: Only one item processed per tick to avoid performance impact
- **Smart Filtering**: Skips reserved items and unreachable destinations
- **Efficient Algorithms**: Uses RimWorld's existing optimized hauling system

### Future Enhancement Potential

- Configurable auto-forward delay
- Priority-based forwarding logic
- Integration with storage group preferences
- Advanced routing algorithms for complex base layouts

---
*This implementation follows RimWorld 1.6 best practices and maintains compatibility with existing mods through careful use of reflection and standard game interfaces.*
