// Shared across any page that filters/browses RFQs by org (the RFQ
// browse table and the project-creation RFQ picker) -- don't duplicate.
export const ORG_OPTIONS: { value: string; label: string }[] = [
  { value: "ADDCORG", label: "ADDC" },
  { value: "TRANSORG", label: "TRANS" },
  { value: "AADCORG", label: "AADC" },
  { value: "ADWEAORG", label: "ADWEA" },
  { value: "AMPCORG", label: "AMPC" },
  { value: "ADSSCORG", label: "ADSSC" },
  { value: "BPCORG", label: "BPC" },
  { value: "all", label: "All organizations" },
];
