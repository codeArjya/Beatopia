import * as THREE from "three";

/**
 * Shared measurements of the Beatopia sampler (world units; the device is about 3.2 wide and 4.2 deep).
 * x = right, y = up, z = toward the viewer. The device is centred on the origin; the seam between the two
 * shells is at y = 0.
 */
export const DIM = {
  width: 3.2,
  depth: 4.2,
  corner: 0.46,
  wall: 0.085,

  /** Top shell: skirt from the seam up to the plate, then the plate. */
  skirtHeight: 0.27,
  plateHeight: 0.12,
  /** Bottom shell: floor, then walls up to the seam. */
  floorHeight: 0.09,
  trayHeight: 0.31,

  pad: { size: 0.56, pitch: 0.7, height: 0.2, radius: 0.075, hole: 0.6, centerZ: 0.5 },
  screen: { width: 2.66, depth: 0.72, centerZ: -1.41, hole: 0.035 },
} as const;

/** y of the top face of the top shell. */
export const TOP_Y = DIM.skirtHeight + DIM.plateHeight;
/** y of the underside of the bottom shell. */
export const BOTTOM_Y = -(DIM.trayHeight + DIM.floorHeight);

/** Centre of pad (row, col). Row 0 is the back row. */
export function padCenter(row: number, col: number): [x: number, z: number] {
  return [(col - 1.5) * DIM.pad.pitch, DIM.pad.centerZ + (row - 1.5) * DIM.pad.pitch];
}

/** Adds a rounded rectangle centred on (cx, cy) to a shape or path (2D, before it is laid flat). */
export function roundedRect<T extends THREE.Path>(path: T, cx: number, cy: number, w: number, h: number, r: number): T {
  const x = cx - w / 2;
  const y = cy - h / 2;
  const rr = Math.min(r, w / 2, h / 2);
  path.moveTo(x + rr, y);
  path.lineTo(x + w - rr, y);
  path.absarc(x + w - rr, y + rr, rr, -Math.PI / 2, 0, false);
  path.lineTo(x + w, y + h - rr);
  path.absarc(x + w - rr, y + h - rr, rr, 0, Math.PI / 2, false);
  path.lineTo(x + rr, y + h);
  path.absarc(x + rr, y + h - rr, rr, Math.PI / 2, Math.PI, false);
  path.lineTo(x, y + rr);
  path.absarc(x + rr, y + rr, rr, Math.PI, Math.PI * 1.5, false);
  path.closePath();
  return path;
}

/** The device outline, grown or shrunk by `inset` (positive = smaller). */
export function outline(inset = 0): THREE.Shape {
  return roundedRect(
    new THREE.Shape(),
    0,
    0,
    DIM.width - inset * 2,
    DIM.depth - inset * 2,
    Math.max(0.02, DIM.corner - inset),
  );
}

/** A ring: the outline at `outerInset` with the outline at `innerInset` cut out of it. */
export function outlineRing(outerInset: number, innerInset: number): THREE.Shape {
  const shape = outline(outerInset);
  shape.holes.push(
    roundedRect(
      new THREE.Path(),
      0,
      0,
      DIM.width - innerInset * 2,
      DIM.depth - innerInset * 2,
      Math.max(0.02, DIM.corner - innerInset),
    ),
  );
  return shape;
}

/**
 * Extrudes a flat shape upward. Shapes are drawn in 2D as (x, -z), so the result is laid flat with its
 * underside at y = 0 and its thickness going up.
 */
export function extrudeUp(
  shape: THREE.Shape,
  height: number,
  bevel = 0,
  curveSegments = 10,
): THREE.ExtrudeGeometry {
  const geometry = new THREE.ExtrudeGeometry(shape, {
    depth: Math.max(0.001, height - bevel * 2),
    bevelEnabled: bevel > 0,
    bevelThickness: bevel,
    bevelSize: bevel,
    // Pull the bevel back in, so the outline (and every cutout) keeps its drawn size.
    bevelOffset: -bevel,
    bevelSegments: 3,
    curveSegments,
  });
  geometry.rotateX(-Math.PI / 2);
  geometry.translate(0, bevel, 0);
  return geometry;
}

/** Small deterministic random generator, so the board and particles look the same on every load. */
export function seededRandom(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** A color pushed past 1.0 so the bloom pass picks it up. Returns a linear-space vector. */
export function boosted(hex: string, boost: number): THREE.Color {
  return new THREE.Color(hex).multiplyScalar(boost);
}
