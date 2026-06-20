/**
 * PURE VORONOI SYSTEM
 *
 * Uses Voronoi at ALL levels for truly irregular polygons
 * Ultra-conservative parameters to prevent escapes
 */

class VoronoiPure {
  constructor(worldSize = 300) {
    this.worldSize = worldSize;
    this.worldHalf = worldSize / 2;
  }

  // Hash function for deterministic random values from strings
  _hashString(str) {
    if (!str) return 0.5;
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash; // Convert to 32bit integer
    }
    return (Math.abs(hash) % 1000) / 1000;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // LEVEL 1: CLUSTER VORONOI
  // ═══════════════════════════════════════════════════════════════════════════

  generateClusters(names, weights) {
    console.log('\n━━━ CLUSTER VORONOI (MAXIMUM IRREGULARITY + GAPS) ━━━');
    console.log(`Generating ${names.length} clusters\n`);

    if (!window.d3?.Delaunay) {
      console.error('❌ d3-delaunay not available');
      return {};
    }

    // Generate seeds with DETERMINISTIC placement (clusters don't move between refreshes)
    const seeds = [];
    const maxW = Math.max(...weights);

    names.forEach((name, i) => {
      // Base position in circle
      const baseAngle = (Math.PI * 2 * i) / names.length;
      const w = weights[i] / maxW;
      const baseRadius = this.worldSize * 0.25 * (0.3 + 0.7 * w);

      // DETERMINISTIC offset: hash cluster name for stable placement
      const nameHash = this._hashString(name);

      // Angle offset: deterministic per cluster
      const angleOffset = (nameHash - 0.5) * 1.0; // Up to ±0.5 radians
      const radiusVariation = 0.5 + nameHash; // 50%-150%

      const x = Math.cos(baseAngle + angleOffset) * (baseRadius * radiusVariation);
      const z = Math.sin(baseAngle + angleOffset) * (baseRadius * radiusVariation);

      // Round to 0.01 for determinism
      const seedX = Math.round(x * 100) / 100;
      const seedZ = Math.round(z * 100) / 100;

      seeds.push([seedX, seedZ]);
      console.log(`  ${name}: seed (${seedX.toFixed(2)}, ${seedZ.toFixed(2)})`);
    });

    // Create Voronoi
    const bounds = [-this.worldHalf, -this.worldHalf, this.worldHalf, this.worldHalf];
    const delaunay = d3.Delaunay.from(seeds);
    const voronoi = delaunay.voronoi(bounds);

    const clusters = {};

    names.forEach((name, i) => {
      const cell = voronoi.cellPolygon(i);
      if (!cell || cell.length < 3) return;

      let polygon = Array.from(cell);
      const originalArea = this._area(polygon);
      const centroid = this._centroid(polygon);

      // SHRINK polygon toward centroid to create gap between clusters
      const shrinkFactor = 0.92; // Shrink to 92% (8% gap)
      polygon = polygon.map(([x, z]) => {
        const dx = x - centroid.x;
        const dz = z - centroid.z;
        return [
          centroid.x + dx * shrinkFactor,
          centroid.z + dz * shrinkFactor
        ];
      });

      const area = this._area(polygon);

      clusters[name] = { polygon, centroid, area };

      console.log(`  ✓ ${name}: ${polygon.length}v, area=${originalArea.toFixed(0)} → ${area.toFixed(0)} (shrunk ${(100 - shrinkFactor * 100).toFixed(0)}%)`);
    });

    console.log('━━━━━━━━━━━━━━━━━━━━\n');
    return clusters;
  }

  _convexHull(points) {
    // Graham scan for convex hull
    if (points.length < 3) return points;

    // Remove duplicates
    const unique = [];
    const seen = new Set();
    points.forEach(([x, z]) => {
      const key = `${x.toFixed(2)},${z.toFixed(2)}`;
      if (!seen.has(key)) {
        seen.add(key);
        unique.push([x, z]);
      }
    });

    if (unique.length < 3) return unique;

    // Find lowest point
    let lowest = unique[0];
    unique.forEach(p => {
      if (p[1] < lowest[1] || (p[1] === lowest[1] && p[0] < lowest[0])) {
        lowest = p;
      }
    });

    // Sort by polar angle
    const sorted = unique.slice();
    sorted.sort((a, b) => {
      if (a === lowest) return -1;
      if (b === lowest) return 1;

      const angleA = Math.atan2(a[1] - lowest[1], a[0] - lowest[0]);
      const angleB = Math.atan2(b[1] - lowest[1], b[0] - lowest[0]);

      return angleA - angleB;
    });

    // Build hull
    const hull = [sorted[0], sorted[1]];

    for (let i = 2; i < sorted.length; i++) {
      let top = hull[hull.length - 1];
      let nextToTop = hull[hull.length - 2];

      while (hull.length >= 2) {
        const cross = (top[0] - nextToTop[0]) * (sorted[i][1] - nextToTop[1]) -
                     (top[1] - nextToTop[1]) * (sorted[i][0] - nextToTop[0]);

        if (cross > 0) break;

        hull.pop();
        if (hull.length >= 2) {
          top = hull[hull.length - 1];
          nextToTop = hull[hull.length - 2];
        }
      }

      hull.push(sorted[i]);
    }

    return hull;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // LEVEL 2: AGENT VORONOI (with ultra-conservative parameters)
  // ═══════════════════════════════════════════════════════════════════════════

  generateAgents(names, weights, clusterPolygon, clusterCentroid) {
    console.log('\n━━━ AGENT VORONOI (IRREGULAR + NORMALIZED WEIGHTS) ━━━');
    console.log(`Generating ${names.length} agents\n`);

    if (names.length === 0) return {};
    if (!window.d3?.Delaunay) return {};

    // ═══ WEIGHT NORMALIZATION (AREA-AWARE) ═══
    const clusterArea = this._area(clusterPolygon);
    const totalWeight = weights.reduce((sum, w) => sum + w, 0);
    const avgWeight = totalWeight / weights.length;

    console.log(`Cluster area: ${clusterArea.toFixed(0)}, Total weight: ${totalWeight.toFixed(1)}, Avg weight: ${avgWeight.toFixed(1)}`);

    // NEW: Area-aware normalization
    // Target: 65% of cluster area for agents (35% gaps/safety margin)
    const targetAgentArea = clusterArea * 0.65;
    const areaPerWeight = clusterArea / totalWeight;

    let normalizationFactor = 1.0;
    // If area per weight unit is too small, weights are too high → normalize down
    if (areaPerWeight < 8.0) {
      normalizationFactor = Math.sqrt(clusterArea / (totalWeight * 12));
      console.log(`⚠️ AGGRESSIVE normalization by ${normalizationFactor.toFixed(3)} (area/weight ratio too low)`);
    } else if (avgWeight > 3.0) {
      normalizationFactor = 3.0 / avgWeight;
      console.log(`⚠️ Moderate normalization by ${normalizationFactor.toFixed(3)} (high avg weight)`);
    }

    const normalizedWeights = weights.map(w => Math.max(0.5, w * normalizationFactor)); // Min 0.5 per agent
    const maxW = Math.max(...normalizedWeights, 1.0);
    console.log(`Normalized weights: [${normalizedWeights.map(w => w.toFixed(2)).join(', ')}]\n`);

    // Calculate safe area with 20% safety margin
    const inradius = this._inradius(clusterPolygon, clusterCentroid);
    const safeInradius = inradius * 0.80; // 20% safety margin from edge
    console.log(`Inradius: ${inradius.toFixed(1)}, Safe inradius (80%): ${safeInradius.toFixed(1)}`);

    // MORE AGGRESSIVE factors for 100% containment
    let factor = 0.30;
    if (names.length >= 8) factor = 0.04; // Extra aggressive
    else if (names.length >= 6) factor = 0.06;
    else if (names.length >= 5) factor = 0.08;
    else if (names.length >= 4) factor = 0.10;
    else if (names.length >= 3) factor = 0.15;
    else if (names.length >= 2) factor = 0.25;

    const maxRadius = safeInradius * factor;
    console.log(`Factor: ${factor} (${names.length} agents), max_radius: ${maxRadius.toFixed(1)} (using safe inradius)\n`);

    // Generate seeds with DETERMINISTIC placement (using NORMALIZED weights)
    const seeds = [];

    names.forEach((name, i) => {
      const baseAngle = (Math.PI * 2 * i) / names.length;
      const w = normalizedWeights[i] / maxW;
      const baseR = maxRadius * (0.5 + 0.5 * w);

      // DETERMINISTIC offset: hash agent name for consistent placement
      const nameHash = this._hashString(name);

      // Angle offset: deterministic per agent
      const angleOffset = (nameHash - 0.5) * 0.5; // ±0.25 radians

      // Radius variation: deterministic, weight-based
      const radiusVariation = 0.6 + (nameHash * 0.6); // 60%-120%

      const x = clusterCentroid.x + Math.cos(baseAngle + angleOffset) * (baseR * radiusVariation);
      const z = clusterCentroid.z + Math.sin(baseAngle + angleOffset) * (baseR * radiusVariation);

      // Round to 0.01 precision for deterministic results
      const seedX = Math.round(x * 100) / 100;
      const seedZ = Math.round(z * 100) / 100;

      seeds.push([seedX, seedZ]);

      const inside = this._pointIn([seedX, seedZ], clusterPolygon);
      console.log(`  ${name}: (${seedX.toFixed(2)}, ${seedZ.toFixed(2)}) ${inside ? '✓' : '✗'}`);
    });

    // Create Voronoi
    const clusterBounds = this._bounds(clusterPolygon);
    const bounds = [
      clusterBounds.minX - 5,
      clusterBounds.minZ - 5,
      clusterBounds.maxX + 5,
      clusterBounds.maxZ + 5
    ];

    const delaunay = d3.Delaunay.from(seeds);
    const voronoi = delaunay.voronoi(bounds);

    console.log('\nClipping to cluster:\n');

    const agents = {};

    names.forEach((name, i) => {
      let cell = voronoi.cellPolygon(i);
      if (!cell || cell.length < 3) {
        console.error(`  ❌ ${name}: invalid cell`);
        return;
      }

      let polygon = Array.from(cell);

      // Clip to cluster
      polygon = this._clip(polygon, clusterPolygon);

      if (!polygon || polygon.length < 3) {
        console.error(`  ❌ ${name}: clip failed`);
        return;
      }

      // AGGRESSIVE push-back of vertices outside
      let adjusted = 0;
      for (let iter = 0; iter < 10; iter++) {
        let hadOutside = false;

        polygon = polygon.map(([x, z]) => {
          if (!this._pointIn([x, z], clusterPolygon)) {
            hadOutside = true;
            adjusted++;
            const dx = x - clusterCentroid.x;
            const dz = z - clusterCentroid.z;
            return [x - dx * 0.3, z - dz * 0.3]; // Push 30% toward center
          }
          return [x, z];
        });

        if (!hadOutside) break;
      }

      // Final check
      const allInside = polygon.every(([x, z]) => this._pointIn([x, z], clusterPolygon));

      // AGGRESSIVE SHRINK agent polygon to create large safety gap for 100% containment
      const agentCentroid = this._centroid(polygon);
      const shrinkFactor = 0.65; // 35% shrink (aggressive for 100% containment)
      polygon = polygon.map(([x, z]) => {
        const dx = x - agentCentroid.x;
        const dz = z - agentCentroid.z;
        return [
          agentCentroid.x + dx * shrinkFactor,
          agentCentroid.z + dz * shrinkFactor
        ];
      });

      // VALIDATE AND REPAIR: Guarantee polygon stays within cluster bounds
      const repairResult = this._validateAndRepair(polygon, clusterPolygon, agentCentroid);
      polygon = repairResult.polygon;
      const finalCentroid = repairResult.centroid;
      if(repairResult.repaired){
        adjusted += 1000; // Mark as heavily adjusted
        console.log(`    → Repaired: clipped to cluster bounds`);
      }

      const area = this._area(polygon);

      agents[name] = { polygon, centroid: finalCentroid, area };

      console.log(`  ${allInside ? '✓' : '✗'} ${name}: ${polygon.length}v, area=${area.toFixed(0)} (shrunk 22%) ${adjusted > 0 ? `(adj ${adjusted})` : ''}`);
    });

    console.log('━━━━━━━━━━━━━━━━━━━━\n');

    // Validate no overlaps
    this.validateNoOverlaps(agents, 'agent');

    return agents;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // LEVEL 3: NEIGHBORHOOD VORONOI (emotions within agent)
  // ═══════════════════════════════════════════════════════════════════════════

  generateNeighborhoods(emotionKeys, emotionCounts, parentPolygon, parentCentroid) {
    console.log('\n━━━ NEIGHBORHOOD VORONOI (EMOTIONS + NORMALIZED) ━━━');
    console.log(`Generating ${emotionKeys.length} neighborhoods\n`);

    if (emotionKeys.length === 0) return {};
    if (!window.d3?.Delaunay) return {};

    // ═══ WEIGHT NORMALIZATION ═══
    const totalCount = emotionCounts.reduce((sum, c) => sum + c, 0);
    const avgCount = totalCount / emotionCounts.length;
    const parentArea = this._area(parentPolygon);

    console.log(`Total count: ${totalCount}, Avg: ${avgCount.toFixed(1)}, Parent area: ${parentArea.toFixed(0)}`);

    // Normalize if needed
    let normalizationFactor = 1.0;
    if (avgCount > 5.0) {
      normalizationFactor = 5.0 / avgCount;
      console.log(`⚠️ High emotion count! Normalizing by ${normalizationFactor.toFixed(2)}`);
    }

    const normalizedCounts = emotionCounts.map(c => c * normalizationFactor);
    const maxCount = Math.max(...normalizedCounts);
    console.log(`Normalized counts: [${normalizedCounts.map(c => c.toFixed(1)).join(', ')}]\n`);

    // Calculate safe area
    const inradius = this._inradius(parentPolygon, parentCentroid);
    console.log(`Parent inradius: ${inradius.toFixed(1)}`);

    // ULTRA-ULTRA-CONSERVATIVE factors for neighborhoods (NEVER escape agent)
    let factor = 0.45; // Reduced from 0.50
    if (emotionKeys.length >= 4) factor = 0.25; // Reduced from 0.30
    else if (emotionKeys.length >= 3) factor = 0.35; // Reduced from 0.40

    const maxRadius = inradius * factor;
    console.log(`Factor: ${factor} (${emotionKeys.length} emotions), max_radius: ${maxRadius.toFixed(1)}\n`);

    // Generate seeds with MAXIMUM JITTER (using normalized counts)
    const seeds = [];

    emotionKeys.forEach((key, i) => {
      const baseAngle = (Math.PI * 2 * i) / emotionKeys.length;
      const w = normalizedCounts[i] / maxCount;
      const baseR = maxRadius * (0.5 + 0.5 * w);

      // HEAVY random offset
      const angleOffset = (Math.random() - 0.5) * 0.8;
      const radiusVariation = 0.4 + Math.random() * 1.2;

      const x = parentCentroid.x + Math.cos(baseAngle + angleOffset) * (baseR * radiusVariation);
      const z = parentCentroid.z + Math.sin(baseAngle + angleOffset) * (baseR * radiusVariation);

      seeds.push([x, z]);

      const inside = this._pointIn([x, z], parentPolygon);
      console.log(`  ${key}: (${x.toFixed(1)}, ${z.toFixed(1)}) ${inside ? '✓' : '✗'}`);
    });

    // Create Voronoi
    const parentBounds = this._bounds(parentPolygon);
    const bounds = [
      parentBounds.minX - 5,
      parentBounds.minZ - 5,
      parentBounds.maxX + 5,
      parentBounds.maxZ + 5
    ];

    const delaunay = d3.Delaunay.from(seeds);
    const voronoi = delaunay.voronoi(bounds);

    console.log('\nClipping to parent:\n');

    const neighborhoods = {};

    emotionKeys.forEach((key, i) => {
      let cell = voronoi.cellPolygon(i);
      if (!cell || cell.length < 3) {
        console.error(`  ❌ ${key}: invalid cell`);
        return;
      }

      let polygon = Array.from(cell);

      // Clip to parent polygon
      polygon = this._clip(polygon, parentPolygon);

      if (!polygon || polygon.length < 3) {
        console.error(`  ❌ ${key}: clip failed`);
        return;
      }

      // AGGRESSIVE push-back of vertices outside
      let adjusted = 0;
      for (let iter = 0; iter < 15; iter++) {
        let hadOutside = false;

        polygon = polygon.map(([x, z]) => {
          if (!this._pointIn([x, z], parentPolygon)) {
            hadOutside = true;
            adjusted++;
            const dx = x - parentCentroid.x;
            const dz = z - parentCentroid.z;
            return [x - dx * 0.3, z - dz * 0.3];
          }
          return [x, z];
        });

        if (!hadOutside) break;
      }

      // Final check
      const allInside = polygon.every(([x, z]) => this._pointIn([x, z], parentPolygon));

      // SHRINK neighborhood polygon to create gaps
      const neighborhoodCentroid = this._centroid(polygon);
      const shrinkFactor = 0.85; // 15% gap between neighborhoods
      polygon = polygon.map(([x, z]) => {
        const dx = x - neighborhoodCentroid.x;
        const dz = z - neighborhoodCentroid.z;
        return [
          neighborhoodCentroid.x + dx * shrinkFactor,
          neighborhoodCentroid.z + dz * shrinkFactor
        ];
      });

      const area = this._area(polygon);
      const centroid = this._centroid(polygon);

      neighborhoods[key] = { polygon, centroid, area };

      console.log(`  ${allInside ? '✓' : '✗'} ${key}: ${polygon.length}v, area=${area.toFixed(0)} (shrunk 15%) ${adjusted > 0 ? `(adj ${adjusted})` : ''}`);
    });

    console.log('━━━━━━━━━━━━━━━━━━━━\n');

    // Validate no overlaps
    this.validateNoOverlaps(neighborhoods, 'neighborhood');

    return neighborhoods;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // LEVEL 4: BUILDING VORONOI (buildings within agent)
  // ═══════════════════════════════════════════════════════════════════════════

  generateBuildings(buildingIds, buildingWeights, parentPolygon, parentCentroid) {
    console.log('\n━━━ BUILDING VORONOI (DYNAMIC + NORMALIZED) ━━━');
    console.log(`Generating ${buildingIds.length} buildings\n`);

    if (buildingIds.length === 0) return {};
    if (!window.d3?.Delaunay) return {};

    // ═══ WEIGHT NORMALIZATION (AREA-AWARE) ═══
    const parentArea = this._area(parentPolygon);
    const totalWeight = buildingWeights.reduce((sum, w) => sum + w, 0);
    const avgWeight = totalWeight / buildingWeights.length;

    console.log(`Agent area: ${parentArea.toFixed(0)}, Total weight: ${totalWeight.toFixed(1)}, Avg weight: ${avgWeight.toFixed(1)}`);

    // NEW: Area-aware normalization for buildings
    // Target: 70% of agent area for buildings (30% gaps/safety)
    const areaPerWeight = parentArea / totalWeight;

    let normalizationFactor = 1.0;
    // More aggressive normalization for buildings to guarantee containment
    if (areaPerWeight < 5.0) {
      normalizationFactor = Math.sqrt(parentArea / (totalWeight * 8));
      console.log(`⚠️ AGGRESSIVE building normalization by ${normalizationFactor.toFixed(3)}`);
    } else if (avgWeight > 2.0) {
      normalizationFactor = 2.0 / avgWeight;
      console.log(`⚠️ Moderate normalization by ${normalizationFactor.toFixed(3)}`);
    }

    const normalizedWeights = buildingWeights.map(w => Math.max(0.3, w * normalizationFactor)); // Min 0.3
    const maxWeight = Math.max(...normalizedWeights, 1.0);
    console.log(`Normalized weights: [${normalizedWeights.map(w => w.toFixed(2)).join(', ')}]\n`);

    // Calculate safe area with 20% safety margin
    const inradius = this._inradius(parentPolygon, parentCentroid);
    const safeInradius = inradius * 0.80; // 20% safety margin from edge
    console.log(`Inradius: ${inradius.toFixed(1)}, Safe inradius (80%): ${safeInradius.toFixed(1)}`);

    // EXTRA-AGGRESSIVE factors for buildings (100% containment guarantee)
    let factor = 0.20;
    if (buildingIds.length >= 8) factor = 0.03; // Extra aggressive
    else if (buildingIds.length >= 5) factor = 0.08;
    else if (buildingIds.length >= 3) factor = 0.15;

    const maxRadius = safeInradius * factor;
    console.log(`Factor: ${factor} (${buildingIds.length} buildings), max_radius: ${maxRadius.toFixed(1)} (using safe inradius)\n`);

    // Generate seeds with DETERMINISTIC placement (grid-based, not random)
    // Uses building ID to derive deterministic offset per building
    const seeds = [];

    buildingIds.forEach((id, i) => {
      const baseAngle = (Math.PI * 2 * i) / buildingIds.length;
      const w = normalizedWeights[i] / maxWeight;
      const baseR = maxRadius * (0.5 + 0.5 * w);

      // DETERMINISTIC placement: hash building ID for consistent offset
      // Simulate building index (e.g., "b0", "b1", "b2") to get repeatable values
      const idHash = this._hashString(id);

      // Angle offset: deterministic per building (small jitter only)
      const angleOffset = (idHash - 0.5) * 0.3; // Reduced variance from 0.8 to 0.3

      // Radius variation: deterministic, weight-based placement
      const radiusVariation = 0.7 + (idHash * 0.5); // Maps to [0.7, 1.2] deterministically

      const x = parentCentroid.x + Math.cos(baseAngle + angleOffset) * (baseR * radiusVariation);
      const z = parentCentroid.z + Math.sin(baseAngle + angleOffset) * (baseR * radiusVariation);

      // Round to 0.01 precision for deterministic results across multiple renders
      const seedX = Math.round(x * 100) / 100;
      const seedZ = Math.round(z * 100) / 100;

      seeds.push([seedX, seedZ]);

      const inside = this._pointIn([seedX, seedZ], parentPolygon);
      console.log(`  ${id}: (${seedX.toFixed(2)}, ${seedZ.toFixed(2)}) ${inside ? '✓' : '✗'} [weight=${w.toFixed(2)}]`);
    });

    // Create Voronoi
    const parentBounds = this._bounds(parentPolygon);
    const bounds = [
      parentBounds.minX - 5,
      parentBounds.minZ - 5,
      parentBounds.maxX + 5,
      parentBounds.maxZ + 5
    ];

    const delaunay = d3.Delaunay.from(seeds);
    const voronoi = delaunay.voronoi(bounds);

    console.log('\nClipping to parent:\n');

    const buildings = {};

    buildingIds.forEach((id, i) => {
      let cell = voronoi.cellPolygon(i);
      if (!cell || cell.length < 3) {
        console.error(`  ❌ ${id}: invalid cell`);
        return;
      }

      let polygon = Array.from(cell);

      // Clip to parent polygon
      polygon = this._clip(polygon, parentPolygon);

      if (!polygon || polygon.length < 3) {
        console.error(`  ❌ ${id}: clip failed`);
        return;
      }

      // AGGRESSIVE push-back of vertices outside (20 iterations for buildings)
      let adjusted = 0;
      for (let iter = 0; iter < 20; iter++) {
        let hadOutside = false;

        polygon = polygon.map(([x, z]) => {
          if (!this._pointIn([x, z], parentPolygon)) {
            hadOutside = true;
            adjusted++;
            const dx = x - parentCentroid.x;
            const dz = z - parentCentroid.z;
            return [x - dx * 0.3, z - dz * 0.3];
          }
          return [x, z];
        });

        if (!hadOutside) break;
      }

      // Final check
      const allInside = polygon.every(([x, z]) => this._pointIn([x, z], parentPolygon));

      // AGGRESSIVE SHRINK building polygon for 100% containment
      const buildingCentroid = this._centroid(polygon);
      const shrinkFactor = 0.60; // 40% shrink (aggressive for 100% containment)
      polygon = polygon.map(([x, z]) => {
        const dx = x - buildingCentroid.x;
        const dz = z - buildingCentroid.z;
        return [
          buildingCentroid.x + dx * shrinkFactor,
          buildingCentroid.z + dz * shrinkFactor
        ];
      });

      // VALIDATE AND REPAIR: Guarantee polygon stays within agent bounds
      const buildingCentroid2 = this._centroid(polygon);
      const repairResult = this._validateAndRepair(polygon, parentPolygon, buildingCentroid2);
      polygon = repairResult.polygon;
      const finalCentroid = repairResult.centroid;
      if(repairResult.repaired){
        adjusted += 1000;
        console.log(`    → Repaired: clipped to agent bounds`);
      }

      const area = this._area(polygon);

      buildings[id] = { polygon, centroid: finalCentroid, area };

      console.log(`  ${allInside ? '✓' : '✗'} ${id}: ${polygon.length}v, area=${area.toFixed(0)} (shrunk 18%) ${adjusted > 0 ? `(adj ${adjusted})` : ''}`);
    });

    console.log('━━━━━━━━━━━━━━━━━━━━\n');

    // Validate no overlaps
    this.validateNoOverlaps(buildings, 'building');

    return buildings;
  }

  /**
   * Validates and repairs a Voronoi polygon to guarantee containment
   * @param {Array} polygon - Polygon vertices [[x,z], ...]
   * @param {Array} parentPolygon - Parent container polygon
   * @param {Object} centroid - Polygon centroid {x, z}
   * @returns {Object} {polygon, centroid, repaired: boolean}
   */
  _validateAndRepair(polygon, parentPolygon, centroid) {
    if(!polygon || polygon.length < 3) return {polygon, centroid, repaired: false};

    // Check all vertices
    let needsRepair = false;
    for(const [x, z] of polygon){
      if(!this._pointIn([x, z], parentPolygon)){
        needsRepair = true;
        break;
      }
    }

    if(!needsRepair) return {polygon, centroid, repaired: false};

    // Repair: Clip to parent polygon using Sutherland-Hodgman
    console.warn(`  ⚠️ Polygon needs repair - clipping to parent`);
    let repairedPoly = this._clip(polygon, parentPolygon);

    if(!repairedPoly || repairedPoly.length < 3){
      console.error(`  ❌ Clip failed! Falling back to aggressive shrink`);
      // Fallback: Shrink toward centroid aggressively (50%)
      repairedPoly = polygon.map(([x, z]) => {
        const dx = x - centroid.x;
        const dz = z - centroid.z;
        return [
          centroid.x + dx * 0.50, // Shrink to 50%
          centroid.z + dz * 0.50
        ];
      });
    }

    // Recalculate centroid
    const newCx = repairedPoly.reduce((sum, p) => sum + p[0], 0) / repairedPoly.length;
    const newCz = repairedPoly.reduce((sum, p) => sum + p[1], 0) / repairedPoly.length;

    return {
      polygon: repairedPoly,
      centroid: {x: newCx, z: newCz},
      repaired: true
    };
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // GEOMETRY UTILITIES
  // ═══════════════════════════════════════════════════════════════════════════

  _area(poly) {
    let sum = 0;
    for (let i = 0; i < poly.length; i++) {
      const j = (i + 1) % poly.length;
      sum += poly[i][0] * poly[j][1] - poly[j][0] * poly[i][1];
    }
    return Math.abs(sum / 2);
  }

  _centroid(poly) {
    let cx = 0, cz = 0, area = 0;
    for (let i = 0; i < poly.length; i++) {
      const j = (i + 1) % poly.length;
      const cross = poly[i][0] * poly[j][1] - poly[j][0] * poly[i][1];
      area += cross;
      cx += (poly[i][0] + poly[j][0]) * cross;
      cz += (poly[i][1] + poly[j][1]) * cross;
    }
    area /= 2;
    return { x: cx / (6 * area), z: cz / (6 * area) };
  }

  _bounds(poly) {
    let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
    poly.forEach(([x, z]) => {
      minX = Math.min(minX, x);
      maxX = Math.max(maxX, x);
      minZ = Math.min(minZ, z);
      maxZ = Math.max(maxZ, z);
    });
    return { minX, maxX, minZ, maxZ };
  }

  _pointIn(pt, poly) {
    const [x, z] = pt;
    let inside = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const [xi, zi] = poly[i];
      const [xj, zj] = poly[j];
      if (((zi > z) !== (zj > z)) && (x < (xj - xi) * (z - zi) / (zj - zi) + xi)) {
        inside = !inside;
      }
    }
    return inside;
  }

  _inradius(poly, center) {
    let minDist = Infinity;
    for (let i = 0; i < poly.length; i++) {
      const j = (i + 1) % poly.length;
      const [x1, z1] = poly[i];
      const [x2, z2] = poly[j];

      const dx = x2 - x1;
      const dz = z2 - z1;
      const len2 = dx * dx + dz * dz;

      let t = 0;
      if (len2 > 0) {
        t = Math.max(0, Math.min(1, ((center.x - x1) * dx + (center.z - z1) * dz) / len2));
      }

      const nearX = x1 + t * dx;
      const nearZ = z1 + t * dz;
      const dist = Math.sqrt((center.x - nearX) ** 2 + (center.z - nearZ) ** 2);

      minDist = Math.min(minDist, dist);
    }
    return minDist;
  }

  _polygonsOverlap(poly1, poly2) {
    // Check if two polygons overlap using Separating Axis Theorem (SAT)
    // Simple version: check if any vertex of poly1 is inside poly2 or vice versa
    for(let pt of poly1) {
      if(this._pointIn(pt, poly2)) return true;
    }
    for(let pt of poly2) {
      if(this._pointIn(pt, poly1)) return true;
    }
    return false;
  }

  validateNoOverlaps(elements, elementType = 'element') {
    // elements: {[id]: {polygon, ...}}
    const keys = Object.keys(elements);
    let overlapCount = 0;

    for(let i = 0; i < keys.length; i++) {
      for(let j = i + 1; j < keys.length; j++) {
        const poly1 = elements[keys[i]].polygon;
        const poly2 = elements[keys[j]].polygon;
        if(poly1 && poly2 && this._polygonsOverlap(poly1, poly2)) {
          console.warn(`⚠️ OVERLAP detected between ${elementType} ${keys[i]} and ${keys[j]}`);
          overlapCount++;
        }
      }
    }

    if(overlapCount === 0) {
      console.log(`✓ No overlaps detected among ${keys.length} ${elementType}s`);
    }
    return overlapCount;
  }

  _clip(subject, clip) {
    let output = subject.slice();

    for (let i = 0; i < clip.length; i++) {
      if (output.length === 0) break;

      const input = output;
      output = [];

      const A = clip[i];
      const B = clip[(i + 1) % clip.length];

      for (let j = 0; j < input.length; j++) {
        const S = input[j];
        const E = input[(j + 1) % input.length];

        const sIn = this._inside(S, A, B);
        const eIn = this._inside(E, A, B);

        if (eIn) {
          if (!sIn) {
            const isect = this._intersect(S, E, A, B);
            if (isect) output.push(isect);
          }
          output.push(E);
        } else if (sIn) {
          const isect = this._intersect(S, E, A, B);
          if (isect) output.push(isect);
        }
      }
    }

    return output;
  }

  _inside(pt, edgeA, edgeB) {
    return (edgeB[0] - edgeA[0]) * (pt[1] - edgeA[1]) -
           (edgeB[1] - edgeA[1]) * (pt[0] - edgeA[0]) >= 0;
  }

  _intersect(p1, p2, p3, p4) {
    const denom = (p1[0] - p2[0]) * (p3[1] - p4[1]) -
                  (p1[1] - p2[1]) * (p3[0] - p4[0]);
    if (Math.abs(denom) < 1e-10) return null;

    const t = ((p1[0] - p3[0]) * (p3[1] - p4[1]) -
               (p1[1] - p3[1]) * (p3[0] - p4[0])) / denom;

    return [
      p1[0] + t * (p2[0] - p1[0]),
      p1[1] + t * (p2[1] - p1[1])
    ];
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // TESTS
  // ═══════════════════════════════════════════════════════════════════════════

  runTests() {
    console.log('\n╔═══════════════════════════╗');
    console.log('║  VORONOI PURE - TESTS    ║');
    console.log('╚═══════════════════════════╝\n');

    const sq = [[0,0], [10,0], [10,10], [0,10]];
    let pass = 0;

    // Area
    if (Math.abs(this._area(sq) - 100) < 0.1) {
      console.log('✓ Area');
      pass++;
    } else console.log('✗ Area');

    // Centroid
    const c = this._centroid(sq);
    if (Math.abs(c.x - 5) < 0.1 && Math.abs(c.z - 5) < 0.1) {
      console.log('✓ Centroid');
      pass++;
    } else console.log('✗ Centroid');

    // Point in polygon
    if (this._pointIn([5, 5], sq) && !this._pointIn([15, 5], sq)) {
      console.log('✓ Point in polygon');
      pass++;
    } else console.log('✗ Point in polygon');

    console.log(`\n${pass}/3 passed\n`);
    console.log('═══════════════════════════\n');
    return pass === 3;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // CONTAINMENT VALIDATION (for dynamic simulation)
  // ═══════════════════════════════════════════════════════════════════════════

  validateContainment(clusterPolygons, agentPolygons, buildingPolygons, clusterNames) {
    console.log('\n╔════════════════════════════════════════════╗');
    console.log('║  MATHEMATICAL CONTAINMENT VALIDATION       ║');
    console.log('╚════════════════════════════════════════════╝\n');

    let totalTests = 0;
    let passedTests = 0;

    // 1. Validate agents are inside their clusters
    console.log('1️⃣  AGENTS → CLUSTERS Containment:\n');
    Object.entries(agentPolygons).forEach(([agentId, agentPoly]) => {
      // Find agent's cluster
      let clusterName = null;
      for (const [cName, cData] of Object.entries(clusterPolygons)) {
        if (clusterNames && clusterNames[agentId]) {
          if (cName === clusterNames[agentId]) {
            clusterName = cName;
            break;
          }
        }
      }

      if (!clusterName && Object.keys(clusterPolygons).length > 0) {
        clusterName = Object.keys(clusterPolygons)[0];
      }

      if (!clusterName) return;

      const clusterPoly = clusterPolygons[clusterName].polygon;
      const agentArea = this._area(agentPoly);
      const clusterArea = this._area(clusterPoly);

      // Check all vertices of agent are inside cluster
      let verticesInside = 0;
      agentPoly.forEach(([x, z]) => {
        if (this._pointIn([x, z], clusterPoly)) verticesInside++;
        totalTests++;
      });

      const allInside = verticesInside === agentPoly.length;
      if (allInside) passedTests += agentPoly.length;

      console.log(`  ${allInside ? '✓' : '✗'} ${agentId} in ${clusterName}: ${verticesInside}/${agentPoly.length} vertices inside`);
      console.log(`     Agent area: ${agentArea.toFixed(1)}, Cluster area: ${clusterArea.toFixed(1)} (${(agentArea/clusterArea*100).toFixed(1)}%)`);
    });

    // 2. Validate buildings are inside their agents
    console.log('\n2️⃣  BUILDINGS → AGENTS Containment:\n');
    Object.entries(buildingPolygons).forEach(([agentId, buildings]) => {
      const agentPoly = agentPolygons[agentId];
      if (!agentPoly) return;

      const agentArea = this._area(agentPoly);
      let totalBuildingArea = 0;

      Object.entries(buildings).forEach(([buildingId, bData]) => {
        const buildingPoly = bData.polygon;
        const buildingArea = this._area(buildingPoly);
        totalBuildingArea += buildingArea;

        // Check all vertices of building are inside agent
        let verticesInside = 0;
        buildingPoly.forEach(([x, z]) => {
          if (this._pointIn([x, z], agentPoly)) verticesInside++;
          totalTests++;
        });

        const allInside = verticesInside === buildingPoly.length;
        if (allInside) passedTests += buildingPoly.length;

        const status = allInside ? '✓' : '✗';
        console.log(`  ${status} ${agentId}/${buildingId}: ${verticesInside}/${buildingPoly.length} vertices inside (area: ${buildingArea.toFixed(1)})`);
      });

      const coveragePercent = (totalBuildingArea / agentArea * 100).toFixed(1);
      console.log(`     Total building coverage in ${agentId}: ${coveragePercent}% of agent area`);
    });

    // Summary
    console.log('\n╔════════════════════════════════════════════╗');
    console.log(`║  RESULT: ${passedTests}/${totalTests} tests passed (${(passedTests/totalTests*100).toFixed(1)}%)     ║`);
    console.log('╚════════════════════════════════════════════╝\n');

    return {
      totalTests,
      passedTests,
      passRate: passedTests / totalTests,
      allPassed: passedTests === totalTests
    };
  }
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = VoronoiPure;
}
