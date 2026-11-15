"use client";

import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";

import { HERO } from "./config";
import { FX_LAYER } from "./Particles";

const vertexShader = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = position.xy * 0.5 + 0.5;
    // Straight to clip space: this triangle always fills the screen, behind everything.
    gl_Position = vec4(position.xy, 1.0, 1.0);
  }
`;

// Either the supplied studio image or a code-drawn haze, centred behind the device, and always faded back to
// the exact page background before it reaches the edges, so the hero has no visible frame.
const fragmentShader = /* glsl */ `
  uniform vec3 uBackground;
  uniform vec3 uAccent;
  uniform vec2 uCenter;
  uniform float uAspect;
  uniform float uOpacity;
  uniform float uViolet;
  uniform float uWhite;
  uniform sampler2D uMap;
  uniform float uMapMix;
  uniform float uMapAspect;
  varying vec2 vUv;

  void main() {
    // p is measured in screen heights from the device centre.
    vec2 p = vUv - uCenter;
    p.x *= uAspect;
    float r = length(p);
    float fade = smoothstep(0.86, 0.1, r);

    // Code-drawn studio: a soft white haze and a faint violet light from behind.
    vec3 drawn = uBackground
      + vec3(uWhite) * exp(-r * r * 2.2)
      + uAccent * uViolet * exp(-dot(p - vec2(0.03, 0.05), p - vec2(0.03, 0.05)) * 5.5);

    // Image: cover-fit and centred on the device.
    float scale = max(1.15, 1.36 * uAspect / uMapAspect);
    vec2 uv = vec2(p.x / (uMapAspect * scale), p.y / scale) + 0.5;
    vec3 image = texture2D(uMap, uv).rgb;

    vec3 studio = mix(drawn, image, uMapMix);
    gl_FragColor = vec4(mix(uBackground, studio, fade * uOpacity), 1.0);
  }
`;

/**
 * The dark studio behind the device. Draws a soft haze in code; if `src` is given (HERO.backdrop.image)
 * and loads, that image fades in on top of the code-drawn version, which stays as the fallback.
 */
export function Backdrop({ src }: { src: string | null }) {
  const material = useRef<THREE.ShaderMaterial>(null);
  const mapMix = useRef(0);
  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array([-1, -1, 0, 3, -1, 0, -1, 3, 0]), 3));
    return g;
  }, []);
  const uniforms = useMemo(
    () => ({
      uBackground: { value: new THREE.Color(HERO.colors.background) },
      uAccent: { value: new THREE.Color(HERO.colors.accent) },
      uCenter: { value: new THREE.Vector2(HERO.camera.centerX, 0.5) },
      uAspect: { value: 1.6 },
      uOpacity: { value: HERO.backdrop.opacity },
      uViolet: { value: HERO.backdrop.hazeViolet },
      uWhite: { value: HERO.backdrop.hazeWhite },
      uMap: { value: null as THREE.Texture | null },
      uMapMix: { value: 0 },
      uMapAspect: { value: 16 / 9 },
    }),
    [],
  );

  useEffect(() => {
    if (!src) return;
    let cancelled = false;
    let texture: THREE.Texture | null = null;
    new THREE.TextureLoader().load(
      src,
      (loaded) => {
        if (cancelled || !material.current) {
          loaded.dispose();
          return;
        }
        texture = loaded;
        loaded.colorSpace = THREE.SRGBColorSpace;
        const image = loaded.image as { width: number; height: number };
        material.current.uniforms.uMap.value = loaded;
        material.current.uniforms.uMapAspect.value = image.width / image.height;
        mapMix.current = 1;
      },
      undefined,
      () => {
        // Missing or broken image: keep the code-drawn backdrop.
      },
    );
    return () => {
      cancelled = true;
      mapMix.current = 0;
      texture?.dispose();
    };
  }, [src]);

  useFrame(({ size }, delta) => {
    const m = material.current;
    if (!m) return;
    m.uniforms.uAspect.value = size.width / size.height;
    const current = m.uniforms.uMapMix.value as number;
    m.uniforms.uMapMix.value = current + (mapMix.current - current) * Math.min(1, delta * 2.5);
  });

  return (
    <mesh geometry={geometry} frustumCulled={false} renderOrder={-1000} layers={FX_LAYER}>
      <shaderMaterial
        ref={material}
        uniforms={uniforms}
        vertexShader={vertexShader}
        fragmentShader={fragmentShader}
        depthTest={false}
        depthWrite={false}
        toneMapped={false}
      />
    </mesh>
  );
}
