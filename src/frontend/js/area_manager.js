/**
 * AREA MANAGER
 *
 * Single source of truth for all area calculations across Grid and Voronoi layouts.
 * Grid calculations are authoritative; Voronoi adapts to match them.
 *
 * Three-level hierarchy:
 *  Level 1 (Clusters): City districts from agent groups
 *  Level 2 (Agents):   Individual agent territories
 *  Level 3 (Buildings): Specific metric visualizations
 */

class AreaManager {
  constructor() {
    // Grid constants (authoritative source)
    this.PLOT = 7.0;                 // Base agent plot size
    this.AGENT_GAP = 0.4;            // Gap between agents within cluster
    this.CGAP = 3.5;                 // Gap between clusters
    this.BUILDING_PAD = 0.07;        // Gap between buildings within agent
    this.CLUSTER_OUTER_PAD = 1.2;    // Padding inside cluster before agents
    this.BARRIO_PAD = 0.12;          // Gap between neighborhoods (emotions)

    // Caching
    this.clusterAreas = new Map();
    this.agentAreas = new Map();
    this.buildingAreas = new Map();

    // Validation thresholds
    this.AREA_TOLERANCE = 0.15;      // 15% tolerance between Grid and Voronoi
    this.MIN_BUILDING_AREA = 0.1;
    this.MAX_BUILDING_AREA = 50.0;
  }

  /**
   * Calculate cluster area from agent count and weights.
   * This is the Grid formula and is authoritative.
   *
   * @param {number} agentCount - Number of agents in cluster
   * @param {number[]} agentWeights - Individual agent weights [turn_count, interactions, etc.]
   * @returns {object} {width, height, area, cols, rows, actScale}
   */
  calculateClusterArea(agentCount, agentWeights) {
    if (agentCount <= 0) {
      return {
        width: this.PLOT,
        height: this.PLOT,
        area: this.PLOT * this.PLOT,
        cols: 1,
        rows: 1,
        actScale: 1.0
      };
    }

    // Total and average weight
    const totalWeight = agentWeights.reduce((s, w) => s + w, 0) || agentCount;
    const avgWeight = totalWeight / agentCount;

    // Grid dimensions (square-ish)
    const cols = Math.ceil(Math.sqrt(agentCount));
    const rows = Math.ceil(agentCount / cols);

    // Activity scaling factor based on average weight
    const actScale = Math.max(1.0, Math.sqrt(avgWeight));

    // Cluster dimensions
    const width = (cols * this.PLOT + 2) * actScale;
    const height = (rows * this.PLOT + 2) * actScale;
    const area = width * height;

    return {
      width: Math.round(width * 100) / 100,
      height: Math.round(height * 100) / 100,
      area: Math.round(area * 100) / 100,
      cols,
      rows,
      actScale: Math.round(actScale * 1000) / 1000
    };
  }

  /**
   * Calculate agent area from its weight within a cluster.
   * Allocation is proportional to agent weight (activity).
   *
   * @param {number} agentWeight - Activity weight of agent
   * @param {object} clusterArea - Result from calculateClusterArea()
   * @param {number} totalWeight - Sum of all agent weights in cluster
   * @returns {object} {area, minWidth, minHeight}
   */
  calculateAgentArea(agentWeight, clusterArea, totalWeight) {
    if (totalWeight <= 0 || !clusterArea) {
      const baseArea = this.PLOT * this.PLOT;
      return {
        area: baseArea * 0.4 * 0.4,
        minWidth: this.PLOT * 0.4,
        minHeight: this.PLOT * 0.4
      };
    }

    // Proportional fraction of cluster area
    const fraction = agentWeight / totalWeight;
    const clusterUsableArea = clusterArea.area * 0.82; // 82% usable
    const allocatedArea = clusterUsableArea * fraction;

    // Minimum area constraint (40% of base plot)
    const minArea = (this.PLOT * 0.4) * (this.PLOT * 0.4);
    const actualArea = Math.max(minArea, allocatedArea);

    return {
      area: Math.round(actualArea * 100) / 100,
      minWidth: Math.round(this.PLOT * 0.4 * 100) / 100,
      minHeight: Math.round(this.PLOT * 0.4 * 100) / 100
    };
  }

  /**
   * Calculate building area (footprint) based on metrics.
   * Width and depth form the footprint; height is separate.
   *
   * @param {object} buildingMetrics - {h, w, d} building dimensions
   * @param {object} agentArea - Result from calculateAgentArea()
   * @param {number} buildingCount - Total buildings in this agent
   * @returns {object} {footprint, height, width, depth}
   */
  calculateBuildingArea(buildingMetrics, agentArea, buildingCount) {
    if (!buildingMetrics || !agentArea || buildingCount <= 0) {
      return {
        footprint: 0.36,  // 0.6 × 0.6
        height: 0.3,
        width: 0.6,
        depth: 0.6
      };
    }

    const h = Math.max(0.3, buildingMetrics.h || 0.3);
    const w = Math.max(0.6, buildingMetrics.w || 0.6);
    const d = Math.max(0.6, buildingMetrics.d || 0.6);

    // Base footprint from width × depth
    const baseFootprint = w * d;

    // Available agent area (82% usable, distributed among buildings)
    const usableArea = agentArea.area * 0.82;
    const maxFootprintPerBuilding = usableArea / buildingCount * 0.9; // 90% of allocated

    const footprint = Math.min(baseFootprint, maxFootprintPerBuilding);

    return {
      footprint: Math.round(footprint * 100) / 100,
      height: Math.round(h * 100) / 100,
      width: Math.round(w * 100) / 100,
      depth: Math.round(d * 100) / 100
    };
  }

  /**
   * Calculate scale factor for Voronoi to match Grid areas.
   * Voronoi is scaled up/down so total area matches Grid.
   *
   * @param {number} gridClusterArea - Total cluster area in Grid
   * @param {number} voronoiClusterArea - Total cluster area in Voronoi
   * @returns {number} Scale factor (e.g., 1.015 = scale up 1.5%)
   */
  getVoronoiScaleFactor(gridClusterArea, voronoiClusterArea) {
    if (voronoiClusterArea <= 0) return 1.0;
    return Math.sqrt(gridClusterArea / voronoiClusterArea);
  }

  /**
   * Validate area consistency between Grid and Voronoi.
   * Checks that areas are within tolerance (default 15%).
   *
   * @param {object} gridAreas - Grid area calculations {cluster: {...}, agents: {...}}
   * @param {object} voronoiElements - Voronoi elements {polygon, area}
   * @returns {object} {total, within_tolerance, mismatches[]}
   */
  validateAreaConsistency(gridAreas, voronoiElements) {
    const results = {
      total: 0,
      within_tolerance: 0,
      tolerance: this.AREA_TOLERANCE,
      mismatches: []
    };

    for (const [id, gridArea] of Object.entries(gridAreas || {})) {
      if (!voronoiElements || !voronoiElements[id]) continue;

      const voronoiArea = voronoiElements[id].area;
      const diff = Math.abs(voronoiArea - gridArea) / gridArea;

      results.total++;

      if (diff <= results.tolerance) {
        results.within_tolerance++;
      } else {
        results.mismatches.push({
          id,
          gridArea: Math.round(gridArea * 100) / 100,
          voronoiArea: Math.round(voronoiArea * 100) / 100,
          diffPercent: (diff * 100).toFixed(1)
        });
      }
    }

    return results;
  }

  /**
   * Cache cluster area calculation.
   * @param {string} clusterId - Cluster identifier
   * @param {object} areaInfo - Result from calculateClusterArea()
   */
  cacheClusterArea(clusterId, areaInfo) {
    this.clusterAreas.set(clusterId, areaInfo);
  }

  /**
   * Retrieve cached cluster area.
   * @param {string} clusterId - Cluster identifier
   * @returns {object|null} Area info or null if not cached
   */
  getClusterArea(clusterId) {
    return this.clusterAreas.get(clusterId) || null;
  }

  /**
   * Cache agent area calculation.
   * @param {string} agentId - Agent identifier
   * @param {object} areaInfo - Result from calculateAgentArea()
   */
  cacheAgentArea(agentId, areaInfo) {
    this.agentAreas.set(agentId, areaInfo);
  }

  /**
   * Retrieve cached agent area.
   * @param {string} agentId - Agent identifier
   * @returns {object|null} Area info or null if not cached
   */
  getAgentArea(agentId) {
    return this.agentAreas.get(agentId) || null;
  }

  /**
   * Clear all caches (useful for re-rendering).
   */
  clearCaches() {
    this.clusterAreas.clear();
    this.agentAreas.clear();
    this.buildingAreas.clear();
  }

  /**
   * Get debug summary of all cached areas.
   * @returns {string} Human-readable summary
   */
  getDebugSummary() {
    const clusterTotal = Array.from(this.clusterAreas.values())
      .reduce((s, ca) => s + ca.area, 0);

    const agentCount = this.agentAreas.size;
    const agentTotal = Array.from(this.agentAreas.values())
      .reduce((s, aa) => s + aa.area, 0);

    return `
Area Manager Cache:
  Clusters: ${this.clusterAreas.size} (total area: ${clusterTotal.toFixed(1)})
  Agents: ${agentCount} (total area: ${agentTotal.toFixed(1)})
  Building footprints: ${this.buildingAreas.size}
  Tolerance threshold: ${(this.AREA_TOLERANCE * 100).toFixed(0)}%
    `.trim();
  }
}

// Export for use in index.html
if (typeof window !== 'undefined') {
  window.AreaManager = AreaManager;
}
