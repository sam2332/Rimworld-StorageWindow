using RimWorld;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using UnityEngine;
using Verse;
using Verse.AI;
using Verse.AI.Group;
using Verse.Sound;

namespace StorageWindow
{
    public class Building_StorageWindow : Building_Storage
    {
        private int ticksUntilAutoForward = 300; // Check every 300 ticks (5 seconds) - much slower
        private int ticksSinceLastJobCreated = 0; // Track time since last job to avoid spam
        private const int ITEMS_HELD_THRESHOLD = 5; // After 5 seconds, start auto-forwarding
        private const int MIN_TICKS_BETWEEN_JOBS = 300; // Minimum 5 seconds between creating jobs

        public override void SpawnSetup(Map map, bool respawningAfterLoad)
        {
            base.SpawnSetup(map, respawningAfterLoad);
            this.Rotation = WindowRotationAt(base.Position, map);
            
            // Set default priority to Low to encourage pass-through behavior
            if (!respawningAfterLoad && this.settings != null)
            {
                this.settings.Priority = StoragePriority.Low;
            }
        }

        protected override void Tick()
        {
            base.Tick();
            
            // Track time since last job
            if (ticksSinceLastJobCreated < MIN_TICKS_BETWEEN_JOBS)
            {
                ticksSinceLastJobCreated++;
            }
            
            // Auto-forward items to better storage periodically, but not too often
            if (--ticksUntilAutoForward <= 0)
            {
                ticksUntilAutoForward = 300; // Reset timer (5 seconds)
                
                // Only try if enough time has passed since last job creation
                if (ticksSinceLastJobCreated >= MIN_TICKS_BETWEEN_JOBS)
                {
                    TryAutoForwardItems();
                }
            }
        }

        private void TryAutoForwardItems()
        {
            if (slotGroup?.HeldThings == null || !slotGroup.HeldThings.Any())
                return;

            // Get a copy of the items to avoid collection modification issues
            var itemsToForward = slotGroup.HeldThings.ToList();
            
            foreach (Thing item in itemsToForward)
            {
                // Skip if item is reserved by anyone (more comprehensive check)
                if (Map.reservationManager.FirstRespectedReserver(item, null) != null)
                    continue;
                
                // Skip if item is forbidden for player faction
                if (item.IsForbidden(Map.mapPawns.FreeColonists.FirstOrDefault()))
                    continue;

                // Try to find better storage for this item
                StoragePriority currentPriority = this.settings.Priority;
                if (StoreUtility.TryFindBestBetterStorageFor(item, null, Map, currentPriority, Faction.OfPlayer, out IntVec3 foundCell, out IHaulDestination haulDestination))
                {
                    // CRITICAL FIX: Make sure we're not trying to haul to ourselves!
                    if (haulDestination == this || foundCell == this.Position)
                    {
                        continue; // Skip this item, it would just create a loop
                    }
                    
                    // Found better storage - create a haul job for any available colonist
                    if (TryCreateAutoForwardJob(item, foundCell, haulDestination))
                    {
                        // Successfully created a job, reset the timer and break to avoid creating multiple jobs
                        ticksSinceLastJobCreated = 0;
                        break; // Only process one item per attempt to avoid performance issues
                    }
                }
            }
        }

        private bool TryCreateAutoForwardJob(Thing item, IntVec3 foundCell, IHaulDestination haulDestination)
        {
            // Find an available colonist to do the hauling
            Pawn hauler = FindAvailableHauler(item);
            if (hauler == null) 
                return false;

            // Double-check that the hauler can still reach and reserve the item
            if (!hauler.CanReach(item, PathEndMode.ClosestTouch, Danger.Deadly) ||
                !hauler.CanReserve(item, 1, -1, null, false))
            {
                return false;
            }

            Job haulJob;
            if (haulDestination is ISlotGroupParent)
            {
                haulJob = HaulAIUtility.HaulToCellStorageJob(hauler, item, foundCell, false);
            }
            else
            {
                // Handle other types of haul destinations
                Thing destThing = haulDestination as Thing;
                if (destThing != null)
                {
                    haulJob = HaulAIUtility.HaulToContainerJob(hauler, item, destThing);
                }
                else
                {
                    return false; // Can't handle this destination type
                }
            }

            if (haulJob != null)
            {
                haulJob.playerForced = false; // This is automatic, not player-forced
                haulJob.haulOpportunisticDuplicates = false; // Don't try to optimize with other items
                
                // Use a more appropriate job tag for automatic hauling
                bool jobAccepted = hauler.jobs.TryTakeOrderedJob(haulJob, JobTag.MiscWork);
                return jobAccepted;
            }
            
            return false;
        }

        private Pawn FindAvailableHauler(Thing item)
        {
            // Find colonists who can haul and are available
            return Map.mapPawns.FreeColonists
                .Where(p => !p.Downed && 
                           !p.Dead && 
                           p.workSettings?.WorkIsActive(WorkTypeDefOf.Hauling) == true &&
                           !p.jobs.curJob?.def?.alwaysShowWeapon == true && // Skip pawns with combat jobs
                           p.CanReach(item, PathEndMode.ClosestTouch, Danger.Deadly) && // Use Deadly to match game's hauling logic
                           HaulAIUtility.PawnCanAutomaticallyHaulFast(p, item, false) &&
                           p.Position.DistanceToSquared(item.Position) <= 900) // Max distance of 30 tiles (30^2 = 900)
                .OrderBy(p => p.Position.DistanceToSquared(item.Position))
                .FirstOrDefault();
        }

        // Override to provide pass-through specific behavior hints
        public override string GetInspectString()
        {
            var baseString = base.GetInspectString();
            var sb = new StringBuilder(baseString);
            
            if (!string.IsNullOrEmpty(baseString))
                sb.AppendLine();
                
            sb.AppendLine("Pass-through window: Items will auto-forward to better storage");
            
            if (slotGroup?.HeldThings?.Any() == true)
            {
                int nextCheckIn = (300 - (300 - ticksUntilAutoForward)) / 60; // Convert to seconds
                int timeSinceLastJob = ticksSinceLastJobCreated / 60; // Convert to seconds
                
                sb.AppendLine($"Items will be moved to higher priority storage when colonists are available");
                
                if (ticksSinceLastJobCreated < MIN_TICKS_BETWEEN_JOBS)
                {
                    int cooldownRemaining = (MIN_TICKS_BETWEEN_JOBS - ticksSinceLastJobCreated) / 60;
                    sb.AppendLine($"Next auto-forward attempt in {Math.Max(1, cooldownRemaining)} seconds");
                }
                else
                {
                    sb.AppendLine($"Next auto-forward check in {Math.Max(1, nextCheckIn)} seconds");
                }
            }
            
            return sb.ToString().TrimEnd();
        }

        private static Rot4 WindowRotationAt(IntVec3 loc, Map map)
        {
            int horizontalQuality = AlignQualityAgainst(loc + IntVec3.East, map) + AlignQualityAgainst(loc + IntVec3.West, map);
            int verticalQuality = AlignQualityAgainst(loc + IntVec3.North, map) + AlignQualityAgainst(loc + IntVec3.South, map);

            // Default to North/South if the qualities are equal.
            return horizontalQuality >= verticalQuality ? Rot4.North : Rot4.East;
        }

        private static int AlignQualityAgainst(IntVec3 c, Map map)
        {
            if (!c.InBounds(map))
            {
                return 0;
            }

            List<Thing> thingList = c.GetThingList(map);
            foreach (Thing thing in thingList)
            {
                // Check if the Thing is a building categorized as a wall.
                if (thing.def != null && thing.def.defName == "Wall")
                {
                    return 1; // Strong alignment with walls.
                }
            }

            return 0; // No alignment.
        }
    }
}
