import React, { useEffect, useRef, useCallback, useState } from "react";
import * as d3 from "d3";

// ── Known molecule name lookup ───────────────────────────────────────────────
const KNOWN_MOLECULES = {
  "CC(=O)Oc1ccccc1C(=O)O": "Aspirin",
  "CC(=O)Nc1ccc(O)cc1": "Paracetamol",
  "Oc1ccccc1C(=O)O": "Salicylic acid",
  "OC(=O)c1ccccc1O": "Salicylic acid",
  "Nc1ccccc1": "Aniline",
  "Oc1ccccc1": "Phenol",
  "c1ccccc1": "Benzene",
  "CCO": "Ethanol",
  "CC(=O)O": "Acetic acid",
  "CC(=O)Cl": "Acetyl chloride",
  "OB(O)c1ccccc1": "Phenylboronic acid",
  "O=Cc1ccccc1": "Benzaldehyde",
  "CC(=O)c1ccccc1": "Acetophenone",
  "COC(=O)c1ccccc1": "Methyl benzoate",
  "OCc1ccccc1": "Benzyl alcohol",
  "O=[N+]([O-])c1ccccc1": "Nitrobenzene",
  "Cc1ccccc1": "Toluene",
  "CC(C)Cc1ccc(cc1)C(C)C(=O)O": "Ibuprofen",
  "CCN(CC)CC(=O)Nc1c(C)cccc1C": "Lidocaine",
  "CN(C)C(=N)NC(=N)N": "Metformin",
};

// ── Colour palette matching app theme ───────────────────────────────────────
const COLORS = {
  target:       { fill: "#7c3aed", stroke: "#a78bfa", text: "#f5f3ff" },
  intermediate: { fill: "#0d9488", stroke: "#2dd4bf", text: "#f0fdfa" },
  leaf:         { fill: "#15803d", stroke: "#4ade80", text: "#f0fdf4" },
  best:         { edge: "#f59e0b", width: 3 },
  normal:       { edge: "#6d28d9", width: 1.5 },
  highlight:    { edge: "#22d3ee", width: 2.5 },
};

const NODE_RADIUS  = 22;
const NODE_SPACING = { x: 180, y: 110 };

// ── Helpers ─────────────────────────────────────────────────────────────────
function getMoleculeName(smiles) {
  if (!smiles) return "?";
  if (KNOWN_MOLECULES[smiles]) return KNOWN_MOLECULES[smiles];
  return smiles.length > 18 ? smiles.slice(0, 17) + "…" : smiles;
}

/**
 * Convert a flat API route object into a d3-hierarchy-compatible tree.
 *
 * API shape:
 *   { target, steps: [{product, reactants, reaction_type, depth}], starting_materials }
 *
 * Strategy: walk steps sorted by depth (ascending). For each step, the
 * *product* is a node whose children are the *reactants*.
 * We build a map {smiles → node} and stitch them together.
 */
function routeToTree(route) {
  if (!route) return null;
  const steps = (route.steps || []).slice().sort((a, b) => a.depth - b.depth);
  const target = route.target || route.target_smiles || "";
  const startingMaterials = new Set(route.starting_materials || []);

  const nodeMap = {};

  const getOrCreate = (smiles, type) => {
    if (!nodeMap[smiles]) {
      nodeMap[smiles] = {
        id: smiles,
        smiles,
        label: getMoleculeName(smiles),
        type: type || (startingMaterials.has(smiles) ? "leaf" : "intermediate"),
        children: [],
        _collapsed: false,
        _childrenCache: null,
      };
    }
    return nodeMap[smiles];
  };

  // Root
  const root = getOrCreate(target, "target");

  // Add child links from each step
  steps.forEach((step) => {
    const productSmiles = step.product || target;
    const parentNode = getOrCreate(productSmiles, productSmiles === target ? "target" : "intermediate");
    parentNode._reactionType = step.reaction_type || step.transform || "";

    (step.reactants || []).forEach((reactantSmiles) => {
      const childType = startingMaterials.has(reactantSmiles) ? "leaf" : "intermediate";
      const childNode = getOrCreate(reactantSmiles, childType);
      // Avoid duplicates
      if (!parentNode.children.find((c) => c.smiles === reactantSmiles)) {
        parentNode.children.push(childNode);
      }
    });
  });

  return root;
}

// ── Main component ───────────────────────────────────────────────────────────
const RetrosynthesisTree = ({ routes = [], selectedRoute = 0, onRouteSelect }) => {
  const svgRef    = useRef(null);
  const wrapRef   = useRef(null);
  const treeCache = useRef({});  // cache compiled trees per route index
  const [tooltip, setTooltip] = useState({ visible: false, x: 0, y: 0, text: "" });
  const [svgHeight, setSvgHeight] = useState(480);

  // ── Build / cache hierarchical data for a route ─────────────────────────
  const getTreeData = useCallback((idx) => {
    if (!routes[idx]) return null;
    if (!treeCache.current[idx]) {
      treeCache.current[idx] = routeToTree(routes[idx]);
    }
    return treeCache.current[idx];
  }, [routes]);

  // ── D3 render ────────────────────────────────────────────────────────────
  const render = useCallback(() => {
    const svg    = d3.select(svgRef.current);
    const width  = wrapRef.current?.clientWidth || 800;
    const margin = { top: 50, right: 40, bottom: 40, left: 40 };

    svg.selectAll("*").remove();

    const root = getTreeData(selectedRoute);
    if (!root) {
      svg.append("text")
        .attr("x", width / 2).attr("y", 120)
        .attr("text-anchor", "middle")
        .attr("fill", "#a78bfa").attr("font-size", "14px")
        .text("No route data available");
      return;
    }

    // ── Collapse helpers ──────────────────────────────────────────────────
    function collapse(d) {
      if (d.children?.length) {
        d._childrenCache = d.children;
        d.children = null;
        d._collapsed = true;
      }
    }
    function expand(d) {
      if (d._childrenCache) {
        d.children = d._childrenCache;
        d._childrenCache = null;
        d._collapsed = false;
      }
    }

    // Build d3 hierarchy — children may be null when collapsed
    function buildHierarchy(node) {
      const obj = { ...node };
      if (node._collapsed || !node.children?.length) {
        obj.children = node._collapsed ? undefined : undefined;
      } else {
        obj.children = node.children.map(buildHierarchy);
      }
      return obj;
    }

    const hierarchyRoot = d3.hierarchy(buildHierarchy(root));
    const nodeCount = hierarchyRoot.descendants().length;
    const treeHeight = Math.max(
      480,
      Math.ceil(hierarchyRoot.height + 1) * NODE_SPACING.y + margin.top + margin.bottom
    );
    setSvgHeight(treeHeight);

    const treeLayout = d3.tree()
      .size([width - margin.left - margin.right, treeHeight - margin.top - margin.bottom])
      .nodeSize([NODE_SPACING.x, NODE_SPACING.y]);

    treeLayout(hierarchyRoot);

    // Shift so leftmost node is within view
    const leaves = hierarchyRoot.leaves();
    const minX = d3.min(leaves, (d) => d.x);
    const maxX = d3.max(leaves, (d) => d.x);
    const offsetX = width / 2 - (minX + maxX) / 2;

    const g = svg
      .attr("width", width)
      .attr("height", treeHeight)
      .append("g")
      .attr("transform", `translate(${margin.left + offsetX},${margin.top})`);

    // ── Edges ─────────────────────────────────────────────────────────────
    const linkGenerator = d3.linkVertical()
      .x((d) => d.x)
      .y((d) => d.y);

    const isBest = selectedRoute === 0;

    g.selectAll(".link")
      .data(hierarchyRoot.links())
      .enter().append("path")
      .attr("class", "link")
      .attr("d", linkGenerator)
      .attr("fill", "none")
      .attr("stroke", isBest ? COLORS.best.edge : COLORS.normal.edge)
      .attr("stroke-width", isBest ? COLORS.best.width : COLORS.normal.width)
      .attr("stroke-opacity", 0.7)
      .attr("stroke-dasharray", isBest ? "none" : "6 3");

    // Edge reaction-type labels (midpoint of each link)
    g.selectAll(".edge-label")
      .data(hierarchyRoot.links())
      .enter().append("text")
      .attr("class", "edge-label")
      .attr("x", (d) => (d.source.x + d.target.x) / 2)
      .attr("y", (d) => (d.source.y + d.target.y) / 2 - 6)
      .attr("text-anchor", "middle")
      .attr("fill", "#c4b5fd")
      .attr("font-size", "9px")
      .attr("font-family", "monospace")
      .text((d) => {
        const rxn = d.target.data._reactionType || "";
        return rxn.length > 20 ? rxn.slice(0, 18) + "…" : rxn;
      });

    // ── Nodes ─────────────────────────────────────────────────────────────
    const nodeGroups = g.selectAll(".node")
      .data(hierarchyRoot.descendants())
      .enter().append("g")
      .attr("class", "node")
      .attr("transform", (d) => `translate(${d.x},${d.y})`)
      .style("cursor", "pointer");

    // Shadow / glow
    const defs = svg.append("defs");
    ["target", "intermediate", "leaf"].forEach((t) => {
      const f = defs.append("filter").attr("id", `glow-${t}`);
      f.append("feGaussianBlur").attr("stdDeviation", "3").attr("result", "coloredBlur");
      const merge = f.append("feMerge");
      merge.append("feMergeNode").attr("in", "coloredBlur");
      merge.append("feMergeNode").attr("in", "SourceGraphic");
    });

    // Outer glow ring (best route only)
    if (isBest) {
      nodeGroups.append("circle")
        .attr("r", NODE_RADIUS + 5)
        .attr("fill", "none")
        .attr("stroke", (d) => COLORS[d.data.type]?.stroke || "#a78bfa")
        .attr("stroke-width", 1)
        .attr("stroke-opacity", 0.35);
    }

    // Main circle
    nodeGroups.append("circle")
      .attr("r", NODE_RADIUS)
      .attr("fill", (d) => COLORS[d.data.type]?.fill || COLORS.intermediate.fill)
      .attr("stroke", (d) => COLORS[d.data.type]?.stroke || COLORS.intermediate.stroke)
      .attr("stroke-width", 2)
      .attr("filter", (d) => `url(#glow-${d.data.type})`);

    // Collapse indicator ring
    nodeGroups.filter((d) => d.data._collapsed)
      .append("circle")
      .attr("r", NODE_RADIUS - 5)
      .attr("fill", "none")
      .attr("stroke", "#f59e0b")
      .attr("stroke-width", 1.5)
      .attr("stroke-dasharray", "4 2");

    // Label inside node (short name)
    nodeGroups.append("text")
      .attr("text-anchor", "middle")
      .attr("dy", "0.35em")
      .attr("fill", (d) => COLORS[d.data.type]?.text || "#fff")
      .attr("font-size", "8px")
      .attr("font-family", "monospace")
      .attr("pointer-events", "none")
      .text((d) => {
        const lbl = d.data.label || "";
        return lbl.length > 10 ? lbl.slice(0, 9) + "…" : lbl;
      });

    // Type badge below node
    nodeGroups.append("text")
      .attr("text-anchor", "middle")
      .attr("dy", NODE_RADIUS + 12)
      .attr("fill", "#d8b4fe")
      .attr("font-size", "7px")
      .attr("font-family", "sans-serif")
      .text((d) => {
        if (d.data.type === "target") return "TARGET";
        if (d.data.type === "leaf")   return "START";
        return d.data._collapsed ? "▶ expand" : (d.children ? "▼" : "");
      });

    // ── Interactions ──────────────────────────────────────────────────────
    nodeGroups
      .on("mouseenter", function (event, d) {
        d3.select(this).select("circle")
          .transition().duration(150)
          .attr("r", NODE_RADIUS + 4);
        setTooltip({
          visible: true,
          x: event.clientX + 12,
          y: event.clientY - 10,
          text: d.data.smiles || d.data.label,
        });
      })
      .on("mousemove", (event) => {
        setTooltip((prev) => ({ ...prev, x: event.clientX + 12, y: event.clientY - 10 }));
      })
      .on("mouseleave", function () {
        d3.select(this).select("circle")
          .transition().duration(150)
          .attr("r", NODE_RADIUS);
        setTooltip((prev) => ({ ...prev, visible: false }));
      })
      .on("click", (event, d) => {
        // Toggle collapse on non-leaf nodes
        if (d.data.type === "leaf") return;
        const rawNode = d.data;
        if (rawNode._collapsed) {
          expand(rawNode);
        } else {
          collapse(rawNode);
        }
        render();  // Re-render with updated collapse state
      });

  }, [selectedRoute, getTreeData]);  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    render();
  }, [render]);

  // Re-render on window resize
  useEffect(() => {
    const observer = new ResizeObserver(render);
    if (wrapRef.current) observer.observe(wrapRef.current);
    return () => observer.disconnect();
  }, [render]);

  if (!routes.length) return null;

  return (
    <div className="w-full">
      {/* Route selector tabs */}
      {routes.length > 1 && (
        <div className="flex flex-wrap gap-2 mb-4">
          {routes.map((route, idx) => (
            <button
              key={idx}
              onClick={() => onRouteSelect?.(idx)}
              className={[
                "px-4 py-1.5 rounded-full text-xs font-semibold transition-all duration-200",
                selectedRoute === idx
                  ? "bg-purple-600 text-white shadow-lg shadow-purple-900/40 scale-105"
                  : "bg-white/10 text-purple-300 hover:bg-purple-700/30 hover:text-white",
              ].join(" ")}
            >
              Route {idx + 1}
              <span className="ml-1.5 opacity-70">
                {route.num_steps || route.steps?.length || 0}s
                {route.score != null ? ` · ${Math.round(route.score)}pts` : ""}
              </span>
            </button>
          ))}
        </div>
      )}

      {/* Legend */}
      <div className="flex flex-wrap gap-4 mb-3 text-xs text-purple-200/70">
        {[
          { color: COLORS.target.fill,       border: COLORS.target.stroke,       label: "Target" },
          { color: COLORS.intermediate.fill, border: COLORS.intermediate.stroke, label: "Intermediate" },
          { color: COLORS.leaf.fill,         border: COLORS.leaf.stroke,         label: "Starting material" },
        ].map(({ color, border, label }) => (
          <span key={label} className="flex items-center gap-1.5">
            <span
              className="inline-block w-3 h-3 rounded-full"
              style={{ background: color, border: `2px solid ${border}` }}
            />
            {label}
          </span>
        ))}
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-5 h-0.5 bg-amber-400" />
          Best route
        </span>
        <span className="opacity-60 italic">Click node to expand/collapse</span>
      </div>

      {/* SVG container */}
      <div
        ref={wrapRef}
        className="w-full overflow-x-auto rounded-xl border border-purple-500/20 bg-black/30 backdrop-blur-sm"
        style={{ minHeight: 200 }}
      >
        <svg
          ref={svgRef}
          width="100%"
          height={svgHeight}
          style={{ display: "block" }}
        />
      </div>

      {/* Tooltip (portal-free, positioned fixed) */}
      {tooltip.visible && (
        <div
          style={{
            position: "fixed",
            left: tooltip.x,
            top: tooltip.y,
            zIndex: 9999,
            pointerEvents: "none",
          }}
          className="max-w-xs bg-gray-900/95 border border-purple-500/40 text-purple-100 text-xs font-mono px-3 py-2 rounded-lg shadow-xl backdrop-blur-md"
        >
          {tooltip.text}
        </div>
      )}
    </div>
  );
};

export default RetrosynthesisTree;
