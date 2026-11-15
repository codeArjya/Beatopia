"use client";

import { ArrowDownIcon } from "lucide-react";
import type Lenis from "lenis";
import dynamic from "next/dynamic";
import Image from "next/image";
import { useLayoutEffect, useRef, useSyncExternalStore, type CSSProperties } from "react";

import { AppButton } from "@/components/adapters";
import { SEARCH_INPUT_ID } from "@/components/shell/SkipLink";
import still from "@/public/hero/sampler-still.jpg";

import { HERO, HERO_CINEMA_QUERY, SEARCH_SECTION_ID } from "./config";

// three.js, GSAP and Lenis load only where the scroll story actually runs.
const HeroSampler = dynamic(() => import("./HeroSampler"), { ssr: false });

/** One line per exploded layer. The leader lines point at these parts, in this order. */
const FEATURES = [
  { part: "Pads", lead: "Chips.", rest: "Pick a mood, a tempo, a key." },
  { part: "Screen", lead: "One big waveform.", rest: "Cut, loop, stretch." },
  { part: "Speaker", lead: "Stems.", rest: "Take just the drums." },
] as const;

/** Height of the still image as a share of the stage (it is a square crop around the device). */
const STILL_HEIGHT = 0.92;

function subscribeToCinema(onChange: () => void) {
  const query = window.matchMedia(HERO_CINEMA_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

/** True where the pinned WebGL story runs. Decided live: resizing, rotating or flipping reduced motion re-decides. */
function useCinema(): boolean {
  return useSyncExternalStore(
    subscribeToCinema,
    () => window.matchMedia(HERO_CINEMA_QUERY).matches,
    () => false,
  );
}

/**
 * The hero at the top of the search page. All text is real HTML here; the 3D device (HeroSampler) is a lazy,
 * decorative layer behind it.
 *
 * Two layouts, switched in CSS by the `cinema` variant (see app/globals.css) so nothing jumps on load:
 *  - cinema: a stage pinned for HERO.scrollVh of scroll, text on the left, the device on the right.
 *  - everyone else (phones, short windows, reduced motion): the still image, then the same text, stacked.
 */
export function HeroSection({ backdropSrc }: { backdropSrc: string | null }) {
  const sectionRef = useRef<HTMLElement>(null);
  const lenisRef = useRef<Lenis | null>(null);
  const cinema = useCinema();

  // A shared search link (/?q=... or ?chips=...) should open on the search, not on the intro above it.
  useLayoutEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if ((params.has("q") || params.has("chips")) && window.scrollY < 8) {
      document.getElementById(SEARCH_SECTION_ID)?.scrollIntoView();
    }
  }, []);

  const goToSearch = () => {
    const target = document.getElementById(SEARCH_SECTION_ID);
    if (!target) return;
    document.getElementById(SEARCH_INPUT_ID)?.focus({ preventScroll: true });
    if (lenisRef.current) {
      // Lenis honours the section's scroll margin, so it stops flush under the sticky header.
      lenisRef.current.scrollTo(target, { duration: 1.1 });
    } else {
      const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      target.scrollIntoView({ behavior: reduced ? "auto" : "smooth" });
    }
  };

  return (
    <section
      ref={sectionRef}
      aria-labelledby="hero-title"
      style={
        {
          "--hero-scroll": `${HERO.scrollVh}vh`,
          "--hero-center": `${HERO.camera.centerX * 100}%`,
          // Matches the 3D framing: the device scales with the stage height, or with the width once the
          // window is narrower than HERO.camera.fitAspect.
          "--hero-still": `min(${STILL_HEIGHT * 100}%, ${((STILL_HEIGHT * 100) / HERO.camera.fitAspect).toFixed(2)}vw)`,
        } as CSSProperties
      }
      className="relative overflow-x-clip cinema:h-[calc(100svh_-_3.5rem_+_var(--hero-scroll))]"
    >
      <div
        data-hero-stage
        className="relative cinema:sticky cinema:top-14 cinema:h-[calc(100svh_-_3.5rem)] cinema:overflow-hidden"
      >
        {/* Decorative layer: still image, then the canvas over it once it has drawn, and the leader lines. */}
        <div
          aria-hidden
          className="pointer-events-none relative mx-auto aspect-square w-full max-w-[34rem] cinema:absolute cinema:inset-0 cinema:mx-0 cinema:aspect-auto cinema:max-w-none"
        >
          {/* The assembled device, captured from the real scene: shown while WebGL loads, and instead of it. */}
          <div
            data-hero-still
            className="absolute inset-0 cinema:inset-auto cinema:top-1/2 cinema:left-(--hero-center) cinema:aspect-square cinema:h-(--hero-still) cinema:-translate-x-1/2 cinema:-translate-y-1/2"
          >
            <Image
              src={still}
              alt=""
              fill
              preload
              sizes="(max-width: 720px) 100vw, 56vw"
              className="object-cover [mask-image:radial-gradient(closest-side,#000_64%,transparent_100%)]"
            />
          </div>
          {cinema && <HeroSampler sectionRef={sectionRef} lenisRef={lenisRef} backdropSrc={backdropSrc} />}
          {FEATURES.map((feature) => (
            <span key={feature.part}>
              <span
                data-hero-line
                className="absolute top-0 left-0 hidden h-px w-px origin-left [transform:scaleX(0)] bg-foreground/45 cinema:block"
              />
              <span
                data-hero-dot
                className="absolute -top-[2.5px] -left-[2.5px] hidden size-[5px] rounded-full bg-foreground opacity-0 cinema:block"
              />
            </span>
          ))}
          {/* Blends the bottom of the stage into the page, so the search rises out of the same dark room. */}
          <div className="absolute inset-x-0 bottom-0 hidden h-28 bg-linear-to-b from-transparent to-background cinema:block" />
        </div>

        {/* Text. In the cinema layout it sits in the empty space left of the device, never over it. */}
        <div className="relative z-10 cinema:pointer-events-none cinema:absolute cinema:inset-0">
          <div className="mx-auto w-full max-w-7xl px-4 pb-14 sm:px-6 cinema:h-full cinema:pb-0">
            <div className="relative cinema:h-full">
              <div className="cinema:absolute cinema:inset-y-0 cinema:left-0 cinema:flex cinema:w-[min(38%,30rem)] cinema:flex-col cinema:justify-center">
                <div data-hero-intro>
                  <p className="eyebrow">For producers learning to sample</p>
                  <h1
                    id="hero-title"
                    className="mt-3 text-[clamp(2.25rem,4.1vw,3.5rem)] leading-[1.05] font-extrabold tracking-[-0.025em] text-balance"
                  >
                    <span className="block">Find the sound.</span>
                    <span className="block">Shape it.</span>
                    <span className="block">Keep going.</span>
                  </h1>
                  <p className="mt-5 max-w-[36ch] text-[17px] leading-7 text-text-secondary">
                    Search a curated Creative Commons library, hear the loop, then chop it in your browser.
                  </p>

                  <div className="mt-8 grid items-center">
                    <p
                      data-hero-cue
                      className="col-start-1 row-start-1 hidden items-center gap-2 font-mono text-[11px] tracking-[0.1em] text-text-secondary uppercase cinema:flex"
                    >
                      <ArrowDownIcon className="size-3.5 motion-safe:animate-bounce" aria-hidden />
                      Scroll to take it apart
                    </p>
                    <div data-hero-cta className="col-start-1 row-start-1 cinema:invisible cinema:opacity-0">
                      <AppButton
                        size="lg"
                        onClick={goToSearch}
                        className="pointer-events-auto h-11 px-7 text-[15px] pointer-coarse:min-h-11"
                      >
                        Start digging
                      </AppButton>
                    </div>
                  </div>
                </div>
              </div>

              <ol className="mt-12 space-y-6 cinema:absolute cinema:inset-0 cinema:mt-0 cinema:space-y-0">
                {FEATURES.map((feature, index) => (
                  <li
                    key={feature.part}
                    data-hero-label
                    className="border-t border-border pt-5 cinema:absolute cinema:top-0 cinema:left-0 cinema:w-max cinema:max-w-[min(19rem,29vw)] cinema:border-0 cinema:pt-0 cinema:opacity-0 cinema:will-change-transform"
                  >
                    <p className="eyebrow">
                      <span className="text-text-tertiary">0{index + 1}</span> {feature.part}
                    </p>
                    <p className="mt-2 text-[22px] leading-7 font-bold tracking-[-0.01em]">
                      {feature.lead} <span className="text-text-secondary">{feature.rest}</span>
                    </p>
                  </li>
                ))}
              </ol>

              <a
                data-hero-skip
                href={`#${SEARCH_SECTION_ID}`}
                onClick={(event) => {
                  event.preventDefault();
                  goToSearch();
                }}
                className="pointer-events-auto absolute bottom-7 left-0 hidden rounded-sm font-mono text-[11px] tracking-[0.1em] text-text-tertiary uppercase underline-offset-4 hover:text-foreground hover:underline cinema:block"
              >
                Skip intro
              </a>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
