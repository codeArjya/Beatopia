"use client";

import { useFrame } from "@react-three/fiber";
import { useMemo, useRef, type Ref, type RefObject } from "react";
import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";

import { HERO, type HeroRig } from "../config";
import { boosted, extrudeUp, outline, seededRandom } from "./dims";

const PLATE_HEIGHT = 0.045;
const TRACE_WIDTH = 0.022;
const TRACE_HEIGHT = 0.006;
const TRACE_GAP = 0.072;

/**
 * Trace bundles. Each line runs along x for `a`, turns 45 degrees for `b`, then runs along z for `c`.
 * `sx` and `sz` flip the direction; `n` is how many parallel lines the bundle has.
 */
const BUSES = [
  { x: -1.22, z: 1.52, a: 0.9, b: 0.5, c: 1.1, sx: 1, sz: -1, n: 5 },
  { x: 1.26, z: 1.6, a: 0.7, b: 0.4, c: 1.55, sx: -1, sz: -1, n: 4 },
  { x: -1.26, z: -1.62, a: 1.0, b: 0.45, c: 0.9, sx: 1, sz: 1, n: 5 },
  { x: 1.2, z: -1.5, a: 0.45, b: 0.55, c: 0.75, sx: -1, sz: 1, n: 3 },
  { x: -0.34, z: 0.18, a: 0.6, b: 0.3, c: 0.5, sx: 1, sz: 1, n: 4 },
  { x: 0.24, z: -0.36, a: 0.5, b: 0.35, c: 0.6, sx: -1, sz: -1, n: 3 },
] as const;

/** Chips and connectors: [x, z, width, depth, height]. All dark neutrals. */
const CHIPS: readonly (readonly [number, number, number, number, number])[] = [
  [0.56, -1.04, 0.8, 0.8, 0.09],
  [-0.76, -0.74, 0.5, 0.36, 0.07],
  [-0.62, 1.02, 0.42, 0.42, 0.07],
  [0.86, 0.76, 0.3, 0.52, 0.06],
  [0, 1.8, 1.3, 0.12, 0.1],
];

/** Capacitors: [x, z]. */
const CAPS: readonly (readonly [number, number])[] = [
  [1.06, -0.2],
  [1.06, 0.06],
  [-1.1, 0.16],
  [-0.2, -1.62],
  [0.06, -1.62],
];

const traceVertex = /* glsl */ `
  attribute float aPhase;
  varying float vPhase;
  varying vec3 vPos;
  void main() {
    vPhase = aPhase;
    vPos = position;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

// Each trace switches on at its own moment as uGlow rises, then carries a slow travelling shimmer.
const traceFragment = /* glsl */ `
  uniform float uGlow;
  uniform float uTime;
  uniform vec3 uIdle;
  uniform vec3 uLit;
  varying float vPhase;
  varying vec3 vPos;
  void main() {
    float on = smoothstep(vPhase * 0.6, vPhase * 0.6 + 0.4, uGlow);
    float flow = 0.72 + 0.28 * sin((vPos.x + vPos.z) * 3.0 - uTime * 2.2 + vPhase * 40.0);
    gl_FragColor = vec4(mix(uIdle, uLit * flow, on), 1.0);
  }
`;

function buildTraces() {
  const random = seededRandom(7);
  const segments: THREE.BufferGeometry[] = [];
  const vias: THREE.BufferGeometry[] = [];

  const addSegment = (ax: number, az: number, bx: number, bz: number, phase: number) => {
    const dx = bx - ax;
    const dz = bz - az;
    const length = Math.hypot(dx, dz);
    const box = new THREE.BoxGeometry(length + TRACE_WIDTH, TRACE_HEIGHT, TRACE_WIDTH);
    box.rotateY(Math.atan2(-dz, dx));
    box.translate((ax + bx) / 2, TRACE_HEIGHT / 2, (az + bz) / 2);
    const count = box.getAttribute("position").count;
    box.setAttribute("aPhase", new THREE.BufferAttribute(new Float32Array(count).fill(phase), 1));
    segments.push(box);
  };
  const addVia = (x: number, z: number) => {
    const via = new THREE.CylinderGeometry(0.04, 0.04, 0.012, 12);
    via.translate(x, 0.006, z);
    vias.push(via);
  };

  for (const bus of BUSES) {
    for (let k = 0; k < bus.n; k++) {
      // Shifting each line across the diagonal keeps all three legs parallel.
      const x0 = bus.x + bus.sx * TRACE_GAP * k;
      const z0 = bus.z - bus.sz * TRACE_GAP * k;
      const x1 = x0 + bus.sx * bus.a;
      const x2 = x1 + bus.sx * bus.b;
      const z2 = z0 + bus.sz * bus.b;
      const z3 = z2 + bus.sz * bus.c;
      const phase = random();
      addSegment(x0, z0, x1, z0, phase);
      addSegment(x1, z0, x2, z2, phase);
      addSegment(x2, z2, x2, z3, phase);
      addVia(x0, z0);
      addVia(x2, z3);
    }
  }
  return { traces: mergeGeometries(segments), vias: mergeGeometries(vias) };
}

function buildComponents() {
  const chips = CHIPS.map(([x, z, w, d, h]) => new THREE.BoxGeometry(w, h, d).translate(x, h / 2, z));
  const caps = CAPS.map(([x, z]) => new THREE.CylinderGeometry(0.07, 0.07, 0.12, 16).translate(x, 0.06, z));
  return { chips: mergeGeometries(chips), caps: mergeGeometries(caps) };
}

/**
 * Layer 4, the circuit board: a deep gray plate with thin traces that light up violet when the device comes
 * apart (driven by `rig.traces`), plus a few chips and capacitors.
 */
export function Board({
  ref,
  rigRef,
  frozen,
}: {
  ref?: Ref<THREE.Group>;
  rigRef: RefObject<HeroRig>;
  frozen: boolean;
}) {
  const material = useRef<THREE.ShaderMaterial>(null);
  const plate = useMemo(() => extrudeUp(outline(0.115), PLATE_HEIGHT).translate(0, -PLATE_HEIGHT, 0), []);
  const { traces, vias } = useMemo(() => buildTraces(), []);
  const { chips, caps } = useMemo(() => buildComponents(), []);
  const uniforms = useMemo(
    () => ({
      uGlow: { value: 0 },
      uTime: { value: 0 },
      uIdle: { value: new THREE.Color(HERO.colors.traceIdle) },
      uLit: { value: boosted(HERO.colors.accent, HERO.fx.traceBoost) },
    }),
    [],
  );

  useFrame(({ clock }) => {
    if (!material.current) return;
    material.current.uniforms.uGlow.value = rigRef.current.traces;
    material.current.uniforms.uTime.value = frozen ? 0 : clock.elapsedTime;
  });

  return (
    <group ref={ref}>
      <mesh geometry={plate}>
        <meshStandardMaterial color={HERO.colors.board} roughness={0.72} metalness={0.2} />
      </mesh>
      <mesh geometry={traces}>
        <shaderMaterial
          ref={material}
          uniforms={uniforms}
          vertexShader={traceVertex}
          fragmentShader={traceFragment}
          toneMapped={false}
        />
      </mesh>
      <mesh geometry={vias}>
        <meshStandardMaterial color="#8d8d9b" roughness={0.35} metalness={0.9} />
      </mesh>
      <mesh geometry={chips}>
        <meshStandardMaterial color="#0c0c0f" roughness={0.55} metalness={0.1} />
      </mesh>
      <mesh geometry={caps}>
        <meshStandardMaterial color="#2a2a32" roughness={0.4} metalness={0.7} />
      </mesh>
    </group>
  );
}
