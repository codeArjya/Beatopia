"use client";

import { useFrame } from "@react-three/fiber";
import { useMemo, useRef, type Ref } from "react";
import * as THREE from "three";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";

import { HERO } from "../config";
import { DIM, TOP_Y, boosted } from "./dims";

const GLASS_HEIGHT = 0.05;
const GLASS_Y = TOP_Y - GLASS_HEIGHT / 2 + 0.004;
const DISPLAY_Y = TOP_Y - GLASS_HEIGHT - 0.012;
const PLAYHEAD_START = 0.34;

const vertexShader = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

// One big waveform drawn as bars: played bars in off-white, the rest dim, and a violet playhead line.
const fragmentShader = /* glsl */ `
  uniform float uPlayhead;
  uniform vec3 uPlayed;
  uniform vec3 uUnplayed;
  uniform vec3 uHead;
  uniform vec3 uBack;
  varying vec2 vUv;

  float hash(float n) { return fract(sin(n * 127.1) * 43758.5453); }

  void main() {
    const float BARS = 58.0;
    vec2 uv = vec2((vUv.x - 0.04) / 0.92, vUv.y);
    float inside = step(0.0, uv.x) * step(uv.x, 1.0);
    float index = floor(uv.x * BARS);
    float cell = fract(uv.x * BARS);

    // A loop-shaped envelope: four hits with tails, plus per-bar variation.
    float beat = fract(index / BARS * 4.0);
    float envelope = 0.2 + 0.8 * exp(-beat * 3.2);
    float height = clamp(envelope * (0.42 + 0.58 * hash(index + 3.0)), 0.07, 1.0) * 0.86;

    float bar = inside * step(0.2, cell) * step(cell, 0.8) * step(abs(uv.y - 0.5) * 2.0, height);
    float played = step((index + 0.5) / BARS, uPlayhead);
    vec3 color = uBack + bar * mix(uUnplayed, uPlayed, played);

    float line = inside * smoothstep(0.006, 0.0015, abs(uv.x - uPlayhead)) * step(abs(uv.y - 0.5), 0.47);
    color = mix(color, uHead, line);
    gl_FragColor = vec4(color, 1.0);
  }
`;

/**
 * Layer 3, the screen: a small glass slab over a glowing waveform (#EDEDED) with a violet playhead line.
 * The waveform and playhead are pushed past 1.0 so the bloom pass catches them.
 */
export function Screen({ ref, frozen }: { ref?: Ref<THREE.Group>; frozen: boolean }) {
  const material = useRef<THREE.ShaderMaterial>(null);
  const glass = useMemo(
    () => new RoundedBoxGeometry(DIM.screen.width, GLASS_HEIGHT, DIM.screen.depth, 4, 0.022),
    [],
  );
  const uniforms = useMemo(
    () => ({
      uPlayhead: { value: PLAYHEAD_START },
      uPlayed: { value: boosted(HERO.colors.text, HERO.fx.screenBoost) },
      uUnplayed: { value: new THREE.Color(HERO.colors.waveUnplayed) },
      uHead: { value: boosted(HERO.colors.accent, HERO.fx.playheadBoost) },
      uBack: { value: new THREE.Color("#060608") },
    }),
    [],
  );

  // The playhead loops across the window like a preview on repeat.
  useFrame(({ clock }) => {
    if (!material.current || frozen) return;
    material.current.uniforms.uPlayhead.value = (clock.elapsedTime * 0.085 + PLAYHEAD_START) % 1;
  });

  return (
    <group ref={ref}>
      {/* tray the display sits in */}
      <mesh position={[0, DISPLAY_Y - 0.06, DIM.screen.centerZ]}>
        <boxGeometry args={[DIM.screen.width + 0.1, 0.1, DIM.screen.depth + 0.1]} />
        <meshStandardMaterial color="#09090b" roughness={0.9} />
      </mesh>
      <mesh position={[0, DISPLAY_Y, DIM.screen.centerZ]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[DIM.screen.width - 0.06, DIM.screen.depth - 0.06]} />
        <shaderMaterial
          ref={material}
          uniforms={uniforms}
          vertexShader={vertexShader}
          fragmentShader={fragmentShader}
          toneMapped={false}
        />
      </mesh>
      <mesh geometry={glass} position={[0, GLASS_Y, DIM.screen.centerZ]}>
        <meshPhysicalMaterial
          color="#0b0b12"
          transparent
          opacity={0.2}
          roughness={0.06}
          metalness={0}
          clearcoat={1}
          clearcoatRoughness={0.05}
          depthWrite={false}
        />
      </mesh>
    </group>
  );
}
