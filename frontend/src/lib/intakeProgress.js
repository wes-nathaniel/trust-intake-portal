// Intake completeness rules (mirrored server-side by _intake_missing_steps in server.py)
const ASSET_DOC_TYPES = new Set(["bank_statement", "deed", "title", "insurance_policy", "business_document"]);

export const STEP_LABELS = {
  grantors: "Grantors", trustee: "Trustee", successor: "Successor Trustees", beneficiaries: "Beneficiaries",
  assets: "What You Own", ein: "EIN Workflow", documents: "Documents",
};

export function isStepComplete(key, trustCase) {
  if (!trustCase) return false;
  const maxGrantors = trustCase.trust_type === "joint" ? 2 : 1;
  const docs = (trustCase.documents || []).filter((d) => !d.is_deleted);
  switch (key) {
    case "grantors": return (trustCase.grantors?.length || 0) >= maxGrantors;
    case "trustee": return (trustCase.trustees?.length || 0) >= 1;
    case "successor": return (trustCase.successor_trustees?.length || 0) >= 1;
    case "beneficiaries": return (trustCase.beneficiaries?.length || 0) >= 1;
    case "assets":
      return (trustCase.assets?.length || 0) >= 1 || (trustCase.asset_items?.length || 0) >= 1
        || docs.some((d) => ASSET_DOC_TYPES.has(d.doc_type))
        || !!trustCase.acknowledgments?.no_assets_ack;
    case "ein": return trustCase.ein?.authorized === true;
    case "documents": {
      const types = new Set(docs.map((d) => d.doc_type));
      const baseDone = types.has("government_id") && types.has("proof_of_address");
      if ((trustCase.intake_path || "new") === "review") return baseDone && types.has("existing_trust");
      return baseDone;
    }
    default: return false;
  }
}

export function missingSteps(trustCase) {
  const keys = (trustCase?.intake_path || "new") === "review"
    ? ["documents"]
    : ["grantors", "trustee", "successor", "beneficiaries", "assets", "ein", "documents"];
  return keys.filter((k) => !isStepComplete(k, trustCase));
}
