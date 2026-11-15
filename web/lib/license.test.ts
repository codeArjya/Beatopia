import { describe, expect, it } from "vitest";

import { licenseUrl } from "./license";

describe("licenseUrl", () => {
  it.each([
    ["CC0", "https://creativecommons.org/publicdomain/zero/1.0/"],
    ["CC-BY-4.0", "https://creativecommons.org/licenses/by/4.0/"],
    ["CC-BY-SA-3.0", "https://creativecommons.org/licenses/by-sa/3.0/"],
    ["CC-BY-NC-ND-4.0", "https://creativecommons.org/licenses/by-nc-nd/4.0/"],
    ["cc-by-nc-4.0", "https://creativecommons.org/licenses/by-nc/4.0/"],
  ])("%s", (license, url) => expect(licenseUrl(license)).toBe(url));

  it("returns null for unknown strings", () => {
    expect(licenseUrl("All rights reserved")).toBeNull();
    expect(licenseUrl("CC-BY")).toBeNull();
  });
});
