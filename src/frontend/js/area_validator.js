/**
 * AREA VALIDATOR
 *
 * Comprehensive validation system ensuring:
 * 1. Hierarchical containment (children strictly within parents)
 * 2. No overlaps between same-level elements
 * 3. Area consistency between Grid and Voronoi
 * 4. All elements within safe boundaries
 */

class AreaValidator {
  constructor(areaManager) {
    this.areaManager = areaManager;
    this.validationLog = [];
    this.passCount = 0;
    this.failCount = 0;
  }

  /**
   * Main validation: hierarchical containment checking.
   * Validates: agents in clusters, buildings in agents.
   *
   * @param {object} clusters - {clusterId: {polygon, area, ...}}
   * @param {object} agents - {agentId: {polygon, cluster, area, ...}}
   * @param {object} buildings - {buildingId: {polygon, agent, area, ...}}
   * @returns {object} {total, passed, failed[], warnings[]}
   */
  validateHierarchy(clusters, agents, buildings) {
    console.log('\n╔═══════════════════════════════════════╗');
    console.log('║  HIERARCHICAL CONTAINMENT VALIDATION  ║');
    console.log('╚═══════════════════════════════════════╝\n');

    const results = {
      total: 0,
      passed: 0,
      failed: [],
      warnings: []
    };

    // ═══════════════════════════════════════════════════════════════════
    // LEVEL 1: Agents contained in Clusters
    // ═══════════════════════════════════════════════════════════════════

    console.log('📦 Level 1: Agents → Clusters\n');

    for (const [clusterId, clusterData] of Object.entries(clusters || {})) {
      if (!clusterData.polygon) continue;

      const clusterPoly = clusterData.polygon;
      const clusterArea = clusterData.area || this._area(clusterPoly);
      let levelPassed = 0;
      let levelTotal = 0;

      for (const [agentId, agentData] of Object.entries(agents || {})) {
        if (agentData.cluster !== clusterId) continue;
        if (!agentData.polygon) continue;

        const agentPoly = agentData.polygon;
        const agentArea = agentData.area || this._area(agentPoly);
        const containment = this._checkContainment(agentPoly, clusterPoly);

        results.total++;
        levelTotal++;

        if (containment.contained) {
          results.passed++;
          levelPassed++;
        } else {
          results.failed.push({
            type: 'AGENT_NOT_IN_CLUSTER',
            child: agentId,
            parent: clusterId,
            outsideVertices: containment.outsideVertices,
            totalVertices: containment.totalVertices,
            childArea: Math.round(agentArea * 100) / 100,
            parentArea: Math.round(clusterArea * 100) / 100,
            coverage: ((agentArea / clusterArea) * 100).toFixed(1)
          });
        }
      }

      if (levelTotal > 0) {
        const statusEmoji = levelPassed === levelTotal ? '✓' : '✗';
        console.log(`  ${statusEmoji} ${clusterId}: ${levelPassed}/${levelTotal} agents contained`);
      }
    }

    // ═══════════════════════════════════════════════════════════════════
    // LEVEL 2: Buildings contained in Agents
    // ═══════════════════════════════════════════════════════════════════

    console.log('\n🏢 Level 2: Buildings → Agents\n');

    for (const [agentId, agentData] of Object.entries(agents || {})) {
      if (!agentData.polygon) continue;

      const agentPoly = agentData.polygon;
      const agentArea = agentData.area || this._area(agentPoly);
      let levelPassed = 0;
      let levelTotal = 0;

      for (const [buildingId, buildingData] of Object.entries(buildings || {})) {
        if (buildingData.agent !== agentId) continue;
        if (!buildingData.polygon) continue;

        const buildingPoly = buildingData.polygon;
        const buildingArea = buildingData.area || this._area(buildingPoly);
        const containment = this._checkContainment(buildingPoly, agentPoly);

        results.total++;
        levelTotal++;

        if (containment.contained) {
          results.passed++;
          levelPassed++;
        } else {
          results.failed.push({
            type: 'BUILDING_NOT_IN_AGENT',
            child: buildingId,
            parent: agentId,
            outsideVertices: containment.outsideVertices,
            totalVertices: containment.totalVertices,
            childArea: Math.round(buildingArea * 100) / 100,
            parentArea: Math.round(agentArea * 100) / 100,
            coverage: ((buildingArea / agentArea) * 100).toFixed(1)
          });
        }
      }

      if (levelTotal > 0) {
        const statusEmoji = levelPassed === levelTotal ? '✓' : '✗';
        console.log(`  ${statusEmoji} ${agentId}: ${levelPassed}/${levelTotal} buildings contained`);
      }
    }

    // Summary
    console.log(`\n📊 Total: ${results.passed}/${results.total} checks passed`);

    if (results.failed.length > 0) {
      console.warn(`\n⚠️  ${results.failed.length} CONTAINMENT VIOLATIONS:`);
      results.failed.forEach((f, i) => {
        console.warn(`  ${i + 1}. ${f.type}: ${f.child} not fully in ${f.parent}`);
        console.warn(`     Vertices outside: ${f.outsideVertices}/${f.totalVertices}`);
        console.warn(`     Child area: ${f.childArea}, Parent area: ${f.parentArea} (${f.coverage}% coverage)`);
      });
    }

    this.passCount += results.passed;
    this.failCount += results.failed.length;

    return results;
  }

  /**
   * Check for overlaps between same-level elements.
   *
   * @param {object} elements - {id: {polygon, area, ...}}
   * @param {string} level - Name of level ("CLUSTERS", "AGENTS", "BUILDINGS")
   * @returns {object} {total_pairs, overlaps[], clean: boolean}
   */
  validateNoOverlaps(elements, level) {
    console.log(`\n━━━ OVERLAP CHECK: ${level} ━━━\n`);

    const results = {
      total_pairs: 0,
      overlaps: [],
      clean: true
    };

    const ids = Object.keys(elements || {});

    // Check all pairs
    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        const idA = ids[i];
        const idB = ids[j];
        const elemA = elements[idA];
        const elemB = elements[idB];

        if (!elemA.polygon || !elemB.polygon) continue;

        results.total_pairs++;
        const overlap = this._checkOverlap(elemA.polygon, elemB.polygon);

        if (overlap.overlaps) {
          results.overlaps.push({
            element_a: idA,
            element_b: idB,
            vertex_count_overlaps: overlap.vertexOverlaps,
            area_a: Math.round(elemA.area * 100) / 100,
            area_b: Math.round(elemB.area * 100) / 100
          });
          results.clean = false;
        }
      }
    }

    const statusEmoji = results.clean ? '✓' : '✗';
    console.log(`${statusEmoji} ${results.total_pairs} pairs checked, ${results.overlaps.length} overlaps detected`);

    if (!results.clean) {
      console.warn('\n⚠️  OVERLAP VIOLATIONS:');
      results.overlaps.forEach((o, i) => {
        console.warn(`  ${i + 1}. ${o.element_a} ↔ ${o.element_b}`);
        console.warn(`     Overlapping vertices: ${o.vertex_count_overlaps}`);
        console.warn(`     Areas: ${o.area_a} vs ${o.area_b}`);
      });
    }

    return results;
  }

  /**
   * Validate area consistency between Grid and Voronoi.
   *
   * @param {object} gridAreas - Grid area calculations
   * @param {object} voronoiElements - Voronoi elements with areas
   * @returns {object} {total, within_tolerance, tolerance_pct, mismatches[]}
   */
  validateAreaConsistency(gridAreas, voronoiElements) {
    console.log('\n━━━ AREA CONSISTENCY (Grid ↔ Voronoi) ━━━\n');

    const tolerance = this.areaManager?.AREA_TOLERANCE || 0.15;
    const results = {
      total: 0,
      within_tolerance: 0,
      tolerance_pct: tolerance * 100,
      mismatches: []
    };

    for (const [id, gridArea] of Object.entries(gridAreas || {})) {
      if (!voronoiElements || !voronoiElements[id]) continue;

      const voronoiArea = voronoiElements[id].area;
      if (!voronoiArea) continue;

      const diff = Math.abs(voronoiArea - gridArea) / gridArea;

      results.total++;

      if (diff <= tolerance) {
        results.within_tolerance++;
      } else {
        results.mismatches.push({
          id,
          gridArea: Math.round(gridArea * 100) / 100,
          voronoiArea: Math.round(voronoiArea * 100) / 100,
          diffPercent: (diff * 100).toFixed(1),
          direction: voronoiArea > gridArea ? 'larger' : 'smaller'
        });
      }
    }

    const statusEmoji = results.mismatches.length === 0 ? '✓' : '⚠️';
    console.log(`${statusEmoji} ${results.within_tolerance}/${results.total} within ${results.tolerance_pct.toFixed(0)}% tolerance`);

    if (results.mismatches.length > 0) {
      console.warn('\nArea mismatches:');
      results.mismatches.forEach((m, i) => {
        console.warn(`  ${i + 1}. ${m.id}: Grid=${m.gridArea}, Voronoi=${m.voronoiArea} (${m.direction} by ${m.diffPercent}%)`);
      });
    }

    return results;
  }

  /**
   * Get total validation stats.
   * @returns {object} {passes, failures, rate_percent}
   */
  getStats() {
    const total = this.passCount + this.failCount;
    const rate = total === 0 ? 100 : (this.passCount / total) * 100;

    return {
      passes: this.passCount,
      failures: this.failCount,
      total,
      rate_percent: rate.toFixed(1)
    };
  }

  /**
   * Reset validation counters.
   */
  resetStats() {
    this.passCount = 0;
    this.failCount = 0;
  }

  // ═══════════════════════════════════════════════════════════════════
  // PRIVATE HELPERS
  // ═══════════════════════════════════════════════════════════════════

  /**
   * Check if all vertices of childPoly are inside parentPoly.
   * @private
   */
  _checkContainment(childPoly, parentPoly) {
    let outsideVertices = 0;

    for (const [x, z] of childPoly) {
      if (!this._pointInPolygon([x, z], parentPoly)) {
        outsideVertices++;
      }
    }

    return {
      contained: outsideVertices === 0,
      outsideVertices,
      totalVertices: childPoly.length
    };
  }

  /**
   * Check if two polygons overlap (vertex-based).
   * @private
   */
  _checkOverlap(polyA, polyB) {
    let overlapCount = 0;

    // Check polyA vertices in polyB
    for (const [x, z] of polyA) {
      if (this._pointInPolygon([x, z], polyB)) {
        overlapCount++;
      }
    }

    // Check polyB vertices in polyA
    for (const [x, z] of polyB) {
      if (this._pointInPolygon([x, z], polyA)) {
        overlapCount++;
      }
    }

    return {
      overlaps: overlapCount > 0,
      vertexOverlaps: overlapCount
    };
  }

  /**
   * Point-in-polygon test using ray casting algorithm.
   * @private
   */
  _pointInPolygon(pt, poly) {
    let inside = false;

    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const xi = poly[i][0];
      const zi = poly[i][1];
      const xj = poly[j][0];
      const zj = poly[j][1];

      const intersect =
        ((zi > pt[1]) !== (zj > pt[1])) &&
        pt[0] < ((xj - xi) * (pt[1] - zi)) / (zj - zi) + xi;

      if (intersect) inside = !inside;
    }

    return inside;
  }

  /**
   * Calculate polygon area using Shoelace formula.
   * @private
   */
  _area(polygon) {
    if (!polygon || polygon.length < 3) return 0;

    let area = 0;
    for (let i = 0; i < polygon.length; i++) {
      const x1 = polygon[i][0];
      const z1 = polygon[i][1];
      const x2 = polygon[(i + 1) % polygon.length][0];
      const z2 = polygon[(i + 1) % polygon.length][1];

      area += x1 * z2 - x2 * z1;
    }

    return Math.abs(area) / 2;
  }
}

// Export for use in index.html
if (typeof window !== 'undefined') {
  window.AreaValidator = AreaValidator;
}
