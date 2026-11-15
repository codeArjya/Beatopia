"use client";

import { useFrame } from "@react-three/fiber";
import { useLayoutEffect, useMemo, useRef, type Ref, type RefObject } from "react";
import * as THREE from "three";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";

import { HERO, LAYER, type HeroRig } from "../config";
import { DIM, TOP_Y, padCenter } from "./dims";

/** Top of a resting pad: it stands a little proud of the top shell. */
const PAD_TOP = TOP_Y + 0.055;
const PAD_Y = PAD_TOP - DIM.pad.height / 2;
const MEMBRANE_Y = PAD_TOP - DIM.pad.height - 0.02;

/** A 16-step idle pattern of pad indices (-1 = rest), so the assembled device looks played. */
const PATTERN = [12, -1, 5, -1, 14, 9, -1, 2, 12, -1, 7, 5, 14, -1, 10, -1];

type Scratch = { matrix: THREE.Matrix4; color: THREE.Color; white: THREE.Color };

/**
 * Layer 2, the sixteen rubber pads: one instanced mesh, one chip hue per row, slightly glossy, on a thin
 * rubber membrane so the layer moves as one piece.
 */
export function Pads({
  ref,
  rigRef,
  frozen,
}: {
  ref?: Ref<THREE.Group>;
  rigRef: RefObject<HeroRig>;
  frozen: boolean;
}) {
  const mesh = useRef<THREE.InstancedMesh>(null);
  const scratch = useRef<Scratch | null>(null);
  const geometry = useMemo(
    () => new RoundedBoxGeometry(DIM.pad.size, DIM.pad.height, DIM.pad.size, 5, DIM.pad.radius),
    [],
  );
  const colors = useMemo(() => HERO.colors.padRows.map((hex) => new THREE.Color(hex)), []);

  useLayoutEffect(() => {
    const m = mesh.current;
    if (!m) return;
    const matrix = new THREE.Matrix4();
    for (let i = 0; i < 16; i++) {
      const [x, z] = padCenter(Math.floor(i / 4), i % 4);
      m.setMatrixAt(i, matrix.makeTranslation(x, PAD_Y, z));
      m.setColorAt(i, colors[Math.floor(i / 4)]);
    }
    m.instanceMatrix.needsUpdate = true;
    if (m.instanceColor) m.instanceColor.needsUpdate = true;
  }, [colors]);

  // Idle pattern: the played pad dips and brightens, then recovers. Only while the device is closed.
  useFrame(({ clock }) => {
    const m = mesh.current;
    if (!m || frozen) return;
    scratch.current ??= { matrix: new THREE.Matrix4(), color: new THREE.Color(), white: new THREE.Color("#ffffff") };
    const s = scratch.current;
    const closed = 1 - Math.min(1, Math.abs(rigRef.current.layers[LAYER.pads].lift) * 6);
    const beat = clock.elapsedTime / HERO.idle.padStep;
    const active = PATTERN[Math.floor(beat) % PATTERN.length];
    const hit = Math.exp(-(beat % 1) * 4.5) * closed;
    for (let i = 0; i < 16; i++) {
      const amount = i === active ? hit : 0;
      const [x, z] = padCenter(Math.floor(i / 4), i % 4);
      m.setMatrixAt(i, s.matrix.makeTranslation(x, PAD_Y - 0.04 * amount, z));
      m.setColorAt(i, s.color.copy(colors[Math.floor(i / 4)]).lerp(s.white, 0.42 * amount));
    }
    m.instanceMatrix.needsUpdate = true;
    if (m.instanceColor) m.instanceColor.needsUpdate = true;
  });

  return (
    <group ref={ref}>
      <instancedMesh ref={mesh} args={[geometry, undefined, 16]} frustumCulled={false}>
        <meshPhysicalMaterial roughness={0.36} metalness={0} clearcoat={0.55} clearcoatRoughness={0.28} />
      </instancedMesh>
      <mesh position={[0, MEMBRANE_Y, DIM.pad.centerZ]}>
        <boxGeometry args={[DIM.pad.pitch * 4 + 0.12, 0.04, DIM.pad.pitch * 4 + 0.12]} />
        <meshStandardMaterial color={HERO.colors.rubber} roughness={0.95} />
      </mesh>
    </group>
  );
}
