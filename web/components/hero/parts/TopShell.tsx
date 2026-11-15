"use client";

import { useMemo, type Ref } from "react";
import * as THREE from "three";

import { HERO } from "../config";
import { DIM, extrudeUp, outline, outlineRing, padCenter, roundedRect } from "./dims";

/** The skirt stops a hair above the seam, so a thin shadow line separates the two shells. */
const SEAM_GAP = 0.012;

/**
 * Layer 1, the top shell: a soft-edged plate with a 4x4 grid of pad cutouts and a window for the screen,
 * on a skirt that reaches down to the seam.
 */
export function TopShell({ ref }: { ref?: Ref<THREE.Group> }) {
  const { plate, skirt } = useMemo(() => {
    const top = outline();
    for (let row = 0; row < 4; row++) {
      for (let col = 0; col < 4; col++) {
        const [x, z] = padCenter(row, col);
        top.holes.push(roundedRect(new THREE.Path(), x, -z, DIM.pad.hole, DIM.pad.hole, DIM.pad.radius + 0.02));
      }
    }
    top.holes.push(
      roundedRect(
        new THREE.Path(),
        0,
        -DIM.screen.centerZ,
        DIM.screen.width + DIM.screen.hole * 2,
        DIM.screen.depth + DIM.screen.hole * 2,
        0.1,
      ),
    );
    const plateGeometry = extrudeUp(top, DIM.plateHeight, 0.03);
    plateGeometry.translate(0, DIM.skirtHeight, 0);

    // Runs from just above the seam up into the plate (a small overlap hides the join).
    const skirtGeometry = extrudeUp(outlineRing(0, DIM.wall), DIM.skirtHeight - SEAM_GAP + 0.03, 0);
    skirtGeometry.translate(0, SEAM_GAP, 0);
    return { plate: plateGeometry, skirt: skirtGeometry };
  }, []);

  return (
    <group ref={ref}>
      <mesh geometry={plate}>
        <meshStandardMaterial color={HERO.colors.shell} roughness={0.8} metalness={0.12} />
      </mesh>
      <mesh geometry={skirt}>
        <meshStandardMaterial color={HERO.colors.shell} roughness={0.84} metalness={0.1} />
      </mesh>
    </group>
  );
}
