let sessionToken = "";
export const setSessionToken = (value) => {
  sessionToken = value;
};
export const getSessionToken = () => sessionToken;
export async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "X-AimGuard-Token": sessionToken,
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "The request could not be completed.",
    );
  return data;
}
export const bytes = (n) =>
  n > 1024 ** 3
    ? `${(n / 1024 ** 3).toFixed(2)} GiB`
    : `${(n / 1024 ** 2).toFixed(1)} MiB`;
export const score = (p) => (p?.score == null ? "—" : (p.score * 100).toFixed(1));
export const relativeDate = (date) => {
  const seconds = Math.max(0, (Date.now() - new Date(date)) / 1000);
  return seconds < 60
    ? "Just now"
    : seconds < 3600
      ? `${Math.floor(seconds / 60)}m ago`
      : seconds < 86400
        ? `${Math.floor(seconds / 3600)}h ago`
        : new Date(date).toLocaleDateString(undefined, {
            month: "short",
            day: "numeric",
          });
};
export const weaponName = (w) =>
  ({
    ak47: "AK-47",
    m4a1: "M4A4",
    m4a1_silencer: "M4A1-S",
    deagle: "Desert Eagle",
    hkp2000: "P2000",
    usp_silencer: "USP-S",
    awp: "AWP",
  })[w] || w?.replace("weapon_", "").toUpperCase();
export const mapCode = (name) =>
  ({
    "Dust II": "D2",
    Mirage: "MR",
    Inferno: "IF",
    Ancient: "AC",
    Nuke: "NK",
    Anubis: "AN",
    Overpass: "OP",
    Cache: "CH",
    Vertigo: "VG",
  })[name] || "CS";
export const statusMeta = (p) =>
  p?.status === "flag_for_review"
    ? ["Review recommended", "review"]
    : p?.status === "not_flagged"
      ? ["No review flag", "clear"]
      : ["Insufficient evidence", "neutral"];
