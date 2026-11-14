// "CC0", "CC-BY-4.0", "CC-BY-SA-3.0", "CC-BY-NC-4.0" → creativecommons.org deed URL; null when unknown.
export function licenseUrl(license: string): string | null {
  const l = license.trim().toUpperCase();
  if (l === "CC0" || l === "CC0-1.0") return "https://creativecommons.org/publicdomain/zero/1.0/";
  const m = l.match(/^CC-(BY(?:-(?:SA|NC|ND))*)-(\d\.\d)$/);
  return m ? `https://creativecommons.org/licenses/${m[1].toLowerCase()}/${m[2]}/` : null;
}
