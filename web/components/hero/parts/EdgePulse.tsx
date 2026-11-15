"use client";

import { useFrame } from "@react-three/fiber";
import { useMemo, useRef, type RefObject } from "react";
import * as THREE from "three";

import { HERO, type HeroRig } from "../config";
import { boosted, extrudeUp, outlineRing } from "./dims";

const HEIGHT = 0.03;

const vertexShader = /* glsl */ `
  varying vec3 vPos;
  void main() {
    vPos = position;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

// A bright head with a fading tail, travelling once around the seam.
const fragmentShader = /* glsl */ `
  uniform float uHead;
  uniform float uGlow;
  uniform vec3 uColor;
  varying vec3 vPos;
  void main() {
    float around = atan(vPos.z, vPos.x) / 6.28318530718 + 0.5;
    float behind = fract(uHead - around);
    float tail = exp(-behind * 7.0);
    float head = smoothstep(0.03, 0.0, min(behind, 1.0 - behind));
    gl_FragColor = vec4(uColor * (tail * 0.85 + head + 0.06) * uGlow, 1.0);
  }
`;

/**
 * The seam light: one short violet pulse that runs along the edge where the two shells meet, right after
 * the device closes (`rig.pulse`). Invisible the rest of the time.
 */
export function EdgePulse({ rigRef }: { rigRef: RefObject<HeroRig> }) {
  const mesh = useRef<THREE.Mesh>(null);
  const material = useRef<THREE.ShaderMaterial>(null);
  const geometry = useMemo(() => extrudeUp(outlineRing(-0.014, 0.03), HEIGHT).translate(0, -HEIGHT / 2, 0), []);
  const uniforms = useMemo(
    () => ({
      uHead: { value: 0 },
      uGlow: { value: 0 },
      uColor: { value: boosted(HERO.colors.accent, HERO.fx.pulseBoost) },
    }),
    [],
  );

  useFrame(() => {
    if (!mesh.current || !material.current) return;
    const { head, glow } = rigRef.current.pulse;
    mesh.current.visible = glow > 0.001;
    // Starts at the front-left corner and runs clockwise.
    material.current.uniforms.uHead.value = head + 0.36;
    material.current.uniforms.uGlow.value = glow;
  });

  return (
    <mesh ref={mesh} geometry={geometry} visible={false}>
      <shaderMaterial
        ref={material}
        uniforms={uniforms}
        vertexShader={vertexShader}
        fragmentShader={fragmentShader}
        blending={THREE.AdditiveBlending}
        transparent
        depthWrite={false}
        toneMapped={false}
      />
    </mesh>
  );
}
