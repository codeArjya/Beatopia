"use client";

import { useMemo, type Ref, type RefObject } from "react";
import * as THREE from "three";

import { HERO, type HeroRig } from "../config";
import { BOTTOM_Y, DIM, extrudeUp, outline, outlineRing } from "./dims";
import { EdgePulse } from "./EdgePulse";

/** The walls stop a hair below the seam (the top shell does the same from above). */
const SEAM_GAP = 0.012;

const FEET: readonly (readonly [number, number])[] = [
  [-1.12, -1.62],
  [1.12, -1.62],
  [-1.12, 1.62],
  [1.12, 1.62],
];

/**
 * Layer 6, the bottom shell: a soft-edged tray with four rubber feet and a seat ring for the speaker.
 * It also carries the seam light, since the seam is the tray's top edge.
 */
export function BottomShell({ ref, rigRef }: { ref?: Ref<THREE.Group>; rigRef: RefObject<HeroRig> }) {
  const { floor, walls } = useMemo(() => {
    const floorGeometry = extrudeUp(outline(), DIM.floorHeight, 0.03).translate(0, BOTTOM_Y, 0);
    const wallGeometry = extrudeUp(outlineRing(0, DIM.wall), DIM.trayHeight - SEAM_GAP + 0.03, 0).translate(
      0,
      -DIM.trayHeight - 0.03,
      0,
    );
    return { floor: floorGeometry, walls: wallGeometry };
  }, []);

  return (
    <group ref={ref}>
      <mesh geometry={floor}>
        <meshStandardMaterial color={HERO.colors.shell} roughness={0.82} metalness={0.12} />
      </mesh>
      <mesh geometry={walls}>
        <meshStandardMaterial color={HERO.colors.shell} roughness={0.84} metalness={0.1} />
      </mesh>
      {/* seat ring for the speaker, visible when the device is open */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -DIM.trayHeight + 0.004, DIM.pad.centerZ - 0.1]}>
        <ringGeometry args={[1.04, 1.13, 72]} />
        <meshStandardMaterial color="#26262d" roughness={0.6} metalness={0.4} />
      </mesh>
      {FEET.map(([x, z]) => (
        <mesh key={`${x}:${z}`} position={[x, BOTTOM_Y - 0.012, z]}>
          <cylinderGeometry args={[0.17, 0.15, 0.04, 24]} />
          <meshStandardMaterial color={HERO.colors.rubber} roughness={0.95} />
        </mesh>
      ))}
      <EdgePulse rigRef={rigRef} />
    </group>
  );
}
