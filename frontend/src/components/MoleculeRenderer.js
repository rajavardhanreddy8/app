import React, { useState, useEffect, useRef } from "react";

/**
 * MoleculeRenderer
 * Renders a 2D SVG structure for a SMILES string using RDKit-JS (CDN).
 *
 * Props
 * -----
 * smiles    {string}  SMILES to render
 * size      {number}  Canvas size in px (default 200)
 * className {string}  Extra CSS classes for the wrapper div
 */

// Singleton promise so we only init RDKit once
let rdkitReady = null;

function getRDKit() {
  if (rdkitReady) return rdkitReady;
  rdkitReady = new Promise((resolve, reject) => {
    // Already loaded synchronously (CDN deferred)
    if (window.RDKit) {
      resolve(window.RDKit);
      return;
    }

    // Wait for RDKit_minimal.js to finish its async init
    const MAX_WAIT = 15000;
    const POLL = 200;
    let elapsed = 0;

    const interval = setInterval(() => {
      if (window.RDKit) {
        clearInterval(interval);
        resolve(window.RDKit);
      } else if (window.initRDKitModule) {
        // If we have the factory but not the instance, init it now
        clearInterval(interval);
        window
          .initRDKitModule()
          .then((RDKit) => {
            window.RDKit = RDKit;
            resolve(RDKit);
          })
          .catch(reject);
      } else if (elapsed >= MAX_WAIT) {
        clearInterval(interval);
        reject(new Error("RDKit-JS initialization timed out"));
      }
      elapsed += POLL;
    }, POLL);
  });
  return rdkitReady;
}

const MoleculeRenderer = ({ smiles, size = 200, className = "" }) => {
  const [svg, setSvg] = useState(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(false);
  const prevSmiles = useRef(null);

  useEffect(() => {
    if (!smiles || !smiles.trim()) {
      setSvg(null); setError(false); setLoading(false);
      prevSmiles.current = null;
      return;
    }
    if (smiles === prevSmiles.current) return;
    prevSmiles.current = smiles;

    setLoading(true);
    setError(false);
    setSvg(null);

    getRDKit()
      .then((RDKit) => {
        let mol;
        try {
          mol = RDKit.get_mol(smiles);
        } catch (_) {
          mol = null;
        }
        if (!mol || !mol.is_valid()) {
          setError(true);
        } else {
          // get_svg() with options object is most reliable
          const opts = JSON.stringify({ width: size, height: size });
          setSvg(mol.get_svg(opts));
        }
        if (mol) mol.delete(); // free WASM memory
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [smiles, size]);

  if (!smiles || !smiles.trim()) return null;

  if (loading) {
    return (
      <div
        className={`molecule-loading flex items-center justify-center ${className}`}
        style={{ width: size, height: size, background: "rgba(255,255,255,0.05)", borderRadius: 8 }}
      >
        <div style={{ textAlign: "center" }}>
          <div
            style={{
              width: 24, height: 24, border: "3px solid #a855f7",
              borderTopColor: "transparent", borderRadius: "50%",
              animation: "spin 0.8s linear infinite", margin: "0 auto 6px",
            }}
          />
          <span style={{ fontSize: 11, color: "#c4b5fd" }}>Rendering…</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div
        className={`molecule-error flex items-center gap-1 ${className}`}
        style={{
          fontSize: 12, color: "#f87171", padding: "6px 10px",
          background: "rgba(239,68,68,0.1)", borderRadius: 6,
          border: "1px solid rgba(239,68,68,0.3)"
        }}
      >
        <span>⚠</span>
        <span>Invalid SMILES</span>
      </div>
    );
  }

  if (!svg) return null;

  return (
    <div
      className={className}
      dangerouslySetInnerHTML={{ __html: svg }}
      title={smiles}
      style={{
        background: "white", borderRadius: 8, padding: 4,
        width: size, height: size, flexShrink: 0,
        boxShadow: "0 0 0 1px rgba(168,85,247,0.25)",
      }}
    />
  );
};

export default MoleculeRenderer;
