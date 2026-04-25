import React, { useState, useCallback } from "react";
import MoleculeRenderer from "./MoleculeRenderer";

/**
 * SmilesInput
 * Combines a styled text input for SMILES with a live 2D preview.
 *
 * Props
 * -----
 * value       {string}    Controlled SMILES value
 * onChange    {Function}  Called with new SMILES string
 * label       {string}    Field label (default "SMILES")
 * placeholder {string}
 * disabled    {bool}
 * id          {string}    HTML id for the input (for testing)
 * showPresets {bool}      Show common-molecule quick-fill buttons (default true)
 * previewSize {number}    Molecule preview size in px (default 180)
 */

const COMMON_MOLECULES = [
  { name: "Aspirin",      smiles: "CC(=O)Oc1ccccc1C(=O)O" },
  { name: "Paracetamol",  smiles: "CC(=O)Nc1ccc(O)cc1" },
  { name: "Ibuprofen",    smiles: "CC(C)Cc1ccc(cc1)C(C)C(=O)O" },
  { name: "Caffeine",     smiles: "Cn1cnc2c1c(=O)n(C)c(=O)n2C" },
  { name: "Ethanol",      smiles: "CCO" },
  { name: "Benzene",      smiles: "c1ccccc1" },
];

// Simple client-side validity check (avoids network round-trip for empty/short strings)
function looksLikeSmiles(s) {
  if (!s || s.trim().length < 1) return null; // empty → neutral
  // RDKit will be the true arbiter; we just check obvious garbage
  return /^[A-Za-z0-9@+\-=\\/()[\]#%.,:]+$/.test(s.trim());
}

const SmilesInput = ({
  value = "",
  onChange,
  label = "SMILES",
  placeholder = "e.g. CC(=O)Oc1ccccc1C(=O)O",
  disabled = false,
  id = "smiles-input",
  showPresets = true,
  previewSize = 180,
  className = "",
}) => {
  const [copied, setCopied] = useState(false);
  const [isValid, setIsValid] = useState(null); // null=neutral, true, false

  const handleChange = useCallback(
    (e) => {
      const v = e.target.value;
      onChange(v);
      setIsValid(looksLikeSmiles(v));
    },
    [onChange]
  );

  const handleRendererError = useCallback(() => setIsValid(false), []);
  const handleRendererSuccess = useCallback(() => {
    if (value.trim()) setIsValid(true);
  }, [value]);

  const handleCopy = () => {
    if (!value) return;
    navigator.clipboard.writeText(value).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  const handlePreset = (smiles) => {
    onChange(smiles);
    setIsValid(true);
  };

  // Border colour by validity state
  const borderColor =
    isValid === true
      ? "1px solid rgba(74,222,128,0.7)"   // green
      : isValid === false
      ? "1px solid rgba(248,113,113,0.7)"  // red
      : "1px solid rgba(168,85,247,0.35)"; // neutral purple

  return (
    <div className={`smiles-input-root ${className}`} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {/* Label row */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <label htmlFor={id} style={{ color: "#e9d5ff", fontWeight: 600, fontSize: 14 }}>
          {label}
        </label>
        {value && (
          <button
            onClick={handleCopy}
            title="Copy SMILES"
            style={{
              background: "rgba(168,85,247,0.15)", border: "1px solid rgba(168,85,247,0.4)",
              borderRadius: 6, padding: "2px 10px", color: "#d8b4fe", fontSize: 12,
              cursor: "pointer", transition: "background 0.15s",
            }}
          >
            {copied ? "✓ Copied" : "Copy"}
          </button>
        )}
      </div>

      {/* Input + preview row */}
      <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
        {/* Text input */}
        <input
          id={id}
          data-testid={id}
          type="text"
          value={value}
          onChange={handleChange}
          placeholder={placeholder}
          disabled={disabled}
          spellCheck={false}
          autoComplete="off"
          style={{
            flex: 1,
            background: "rgba(255,255,255,0.07)",
            border: borderColor,
            borderRadius: 8,
            padding: "10px 14px",
            color: "#f3f4f6",
            fontSize: 14,
            fontFamily: "monospace",
            outline: "none",
            transition: "border 0.2s",
            minWidth: 0,
          }}
        />

        {/* Live 2D preview */}
        {value.trim() && (
          <SmilePreviewWrapper
            smiles={value}
            size={previewSize}
            onError={handleRendererError}
            onSuccess={handleRendererSuccess}
          />
        )}
      </div>

      {/* Validity hint */}
      {isValid === false && value.trim() && (
        <span style={{ fontSize: 12, color: "#f87171" }}>
          ⚠ May be invalid SMILES — check syntax
        </span>
      )}
      {isValid === true && (
        <span style={{ fontSize: 12, color: "#4ade80" }}>
          ✓ Valid structure
        </span>
      )}

      {/* Presets */}
      {showPresets && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          <span style={{ fontSize: 12, color: "#a78bfa", alignSelf: "center", marginRight: 2 }}>
            Quick:
          </span>
          {COMMON_MOLECULES.map((mol) => (
            <button
              key={mol.name}
              onClick={() => handlePreset(mol.smiles)}
              style={{
                background: "rgba(139,92,246,0.15)",
                border: "1px solid rgba(139,92,246,0.35)",
                borderRadius: 20,
                padding: "3px 12px",
                color: "#c4b5fd",
                fontSize: 12,
                cursor: "pointer",
                transition: "background 0.15s",
              }}
              onMouseEnter={(e) => (e.target.style.background = "rgba(139,92,246,0.3)")}
              onMouseLeave={(e) => (e.target.style.background = "rgba(139,92,246,0.15)")}
            >
              {mol.name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

const SmilePreviewWrapper = ({ smiles, size, onError, onSuccess }) => {
  return (
    <div style={{ flexShrink: 0 }}>
      <MoleculeRenderer
        smiles={smiles}
        size={size}
        className="preview-renderer"
      />
    </div>
  );
};

export default SmilesInput;
