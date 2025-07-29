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
        private int ticksUntilAutoForward = 60; // Check every 60 ticks (1 second)
        private const int ITEMS_HELD_THRESHOLD = 5; // After 5 seconds, start auto-forwarding

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
            
            // Auto-forward items to better storage periodically
            if (--ticksUntilAutoForward <= 0)
            {
                ticksUntilAutoForward = 60; // Reset timer
                TryAutoForwardItems();
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
                // Skip if item is reserved or being hauled
                if (Map.reservationManager.IsReservedByAnyoneOf(item, Faction.OfPlayer))
                    continue;

                // Try to find better storage for this item
                StoragePriority currentPriority = this.settings.Priority;
                if (StoreUtility.TryFindBestBetterStorageFor(item, null, Map, currentPriority, Faction.OfPlayer, out IntVec3 foundCell, out IHaulDestination haulDestination))
                {
                    // Found better storage - create a haul job for any available colonist
                    TryCreateAutoForwardJob(item, foundCell, haulDestination);
                    break; // Only process one item per tick to avoid performance issues
                }
            }
        }

        private void TryCreateAutoForwardJob(Thing item, IntVec3 foundCell, IHaulDestination haulDestination)
        {
            // Find an available colonist to do the hauling
            Pawn hauler = FindAvailableHauler(item);
            if (hauler == null) 
                return;

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
                    return; // Can't handle this destination type
                }
            }

            if (haulJob != null)
            {
                haulJob.playerForced = false; // This is automatic, not player-forced
                hauler.jobs.TryTakeOrderedJob(haulJob, JobTag.MiscWork);
            }
        }

        private Pawn FindAvailableHauler(Thing item)
        {
            // Find colonists who can haul and are available
            return Map.mapPawns.FreeColonists
                .Where(p => !p.Downed && 
                           !p.Dead && 
                           p.workSettings?.WorkIsActive(WorkTypeDefOf.Hauling) == true &&
                           p.CanReach(item, PathEndMode.Touch, Danger.None) &&
                           HaulAIUtility.PawnCanAutomaticallyHaulFast(p, item, false))
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
                sb.AppendLine($"Items will be moved to higher priority storage when colonists are available");
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
