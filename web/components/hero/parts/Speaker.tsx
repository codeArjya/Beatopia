"use client";

import { useMemo, type Ref } from "react";
import * as THREE from "three";

import { HERO } from "../config";
import { DIM } from "./dims";

/** Under the pad grid, where a hand would cover it least. */
const CENTER_Z = DIM.pad.centerZ - 0.1;

/**
 * Layer 5, the speaker: a matte black cone in a shallow basket, with a thin violet light around the rim.
 * The rim light stays under the bloom threshold: it is a line of color, not a glow.
 */
export function Speaker({ ref }: { ref?: Ref<THREE.Group> }) {
  const cone = useMemo(
    () =>
      new THREE.LatheGeometry(
        [
          new THREE.Vector2(0.2, -0.14),
          new THREE.Vector2(0.4, -0.116),
          new THREE.Vector2(0.62, -0.072),
          new THREE.Vector2(0.83, -0.018),
        ],
        72,
      ),
    [],
  );
  const rimColor = useMemo(() => new THREE.Color(HERO.colors.accent).multiplyScalar(1.5), []);

  return (
    <group ref={ref}>
      <group position={[0, 0, CENTER_Z]}>
        {/* frame */}
        <mesh rotation={[Math.PI / 2, 0, 0]} scale={[1, 1, 0.6]}>
          <torusGeometry args={[1.07, 0.05, 12, 96]} />
          <meshStandardMaterial color="#2b2b33" roughness={0.6} metalness={0.5} />
        </mesh>
        {/* rubber surround */}
        <mesh rotation={[Math.PI / 2, 0, 0]} scale={[1, 1, 0.7]} position={[0, -0.008, 0]}>
          <torusGeometry args={[0.91, 0.085, 14, 96]} />
          <meshStandardMaterial color="#1c1c22" roughness={0.5} />
        </mesh>
        <mesh geometry={cone}>
          <meshStandardMaterial color="#141418" roughness={0.95} side={THREE.DoubleSide} />
        </mesh>
        {/* dust cap */}
        <mesh position={[0, -0.249, 0]}>
          <sphereGeometry args={[0.24, 32, 12, 0, Math.PI * 2, 0, 1.1]} />
          <meshStandardMaterial color="#18181d" roughness={0.38} />
        </mesh>
        {/* basket and magnet */}
        <mesh position={[0, -0.1, 0]}>
          <cylinderGeometry args={[1.0, 0.5, 0.16, 48, 1, true]} />
          <meshStandardMaterial color="#0e0e11" roughness={0.85} metalness={0.3} side={THREE.DoubleSide} />
        </mesh>
        <mesh position={[0, -0.2, 0]}>
          <cylinderGeometry args={[0.46, 0.46, 0.08, 40]} />
          <meshStandardMaterial color="#1e1e24" roughness={0.5} metalness={0.6} />
        </mesh>
        {/* violet rim light */}
        <mesh rotation={[Math.PI / 2, 0, 0]} position={[0, 0.014, 0]}>
          <torusGeometry args={[1.0, 0.016, 8, 128]} />
          <meshBasicMaterial color={rimColor} toneMapped={false} />
        </mesh>
      </group>
    </group>
  );
}
