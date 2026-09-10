"use client";

import { useEffect, useRef } from "react";

// The centrepiece behind the landing page. Several looks share one shader and
// one quad; `variant` picks the branch. All of them are monochrome with a
// touch of chromatic split, fade and grow in over the intro, then move very
// slowly. Contrast stays low because text and panels sit on top.
//
//   ring    a thin luminous lens ring -- the default, chosen by eye
//   glass   a refractive orb, closest to the reference
//   chrome  the same orb as liquid metal: smooth bands, hard highlights
//   smoke   no orb; slow ink rising through a soft spotlight
//   horizon a perspective grid running to a glowing horizon
//
// The others stay reachable with ?bg= on the landing page.

export type BackgroundVariant = "glass" | "chrome" | "smoke" | "ring" | "horizon";
const VARIANT_INDEX: Record<BackgroundVariant, number> = {
  glass: 0,
  chrome: 1,
  smoke: 2,
  ring: 3,
  horizon: 4,
};

const VERTEX = `
attribute vec2 a_pos;
void main() { gl_Position = vec4(a_pos, 0.0, 1.0); }
`;

const FRAGMENT = `
precision highp float;
uniform vec2  u_res;
uniform float u_time;
uniform float u_intro;
uniform int   u_variant;

float hash(vec2 p) {
  p = fract(p * vec2(127.1, 311.7));
  p += dot(p, p + 19.19);
  return fract(p.x * p.y);
}
float noise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x),
             mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y);
}
float fbm(vec2 p) {
  float v = 0.0, a = 0.5;
  mat2 r = mat2(0.8, 0.6, -0.6, 0.8);
  for (int i = 0; i < 6; i++) { v += a * noise(p); p = r * p * 2.05 + 1.7; a *= 0.5; }
  return v;
}

// Texture seen through the orb, sampled at a warped position so it looks bent
// by the surface. When metal is set, noise is swapped for smooth bands.
float lens(vec2 uv, float z, float t, float shift, bool metal) {
  float bend = 1.0 + 0.45 * (1.0 - z);
  vec2 q = uv * bend;
  float c = cos(t * 0.12), s = sin(t * 0.12);
  q = mat2(c, -s, s, c) * q + shift;
  if (metal) {
    float w = fbm(q * 1.3 + t * 0.04) * 2.0;
    return 0.5 + 0.5 * sin(q.x * 6.0 + w * 3.0 + t * 0.2);
  }
  float w = fbm(q * 2.2 + t * 0.05);
  return fbm(q * 3.5 + w * 1.6 - t * 0.03);
}

vec3 orb(vec2 p, float R, float t, float intro, bool metal) {
  vec3 col = vec3(0.0);
  float d = length(p);
  float halo = exp(-max(d - R, 0.0) * 6.0) * (metal ? 0.4 : 0.5);
  col += vec3(0.85, 0.9, 1.0) * halo;
  if (d < R) {
    vec2 uv = p / R;
    float z = sqrt(max(0.0, 1.0 - dot(uv, uv)));
    float rim = 1.0 - z;
    float ab = 0.012 + 0.03 * rim;
    vec3 tex = vec3(lens(uv, z, t, ab, metal), lens(uv, z, t, 0.0, metal), lens(uv, z, t, -ab, metal));
    tex = metal ? smoothstep(0.15, 0.95, tex) : smoothstep(0.25, 0.85, tex);
    tex = mix(vec3(dot(tex, vec3(0.333))), tex, metal ? 0.35 : 0.55);
    vec3 n = vec3(uv, z);
    vec3 l = normalize(vec3(-0.45, 0.6, 0.65));
    float diff = 0.35 + 0.65 * max(dot(n, l), 0.0);
    float fres = pow(rim, 2.5);
    float spec = pow(max(dot(reflect(-l, n), vec3(0, 0, 1)), 0.0), metal ? 90.0 : 40.0);
    vec3 body = tex * diff * (metal ? 0.65 : 0.5)
              + vec3(0.9, 0.95, 1.0) * fres * 0.85
              + spec * (metal ? 1.2 : 0.5);
    col = mix(col, body, smoothstep(R, R - 0.004, d));
  }
  return col * intro;
}

vec3 smoke(vec2 p, float t, float intro) {
  // Ink rising slowly through a spotlight from above.
  vec2 q = p * 1.4 + vec2(0.0, -t * 0.06);
  float w = fbm(q * 1.5 + vec2(t * 0.03, 0.0));
  float f = fbm(q * 2.2 + w * 1.8);
  f = smoothstep(0.35, 0.9, f);
  float spot = exp(-length(p * vec2(1.0, 1.6)) * 1.8);
  float ab = 0.01;
  float fr = smoothstep(0.35, 0.9, fbm(q * 2.2 + w * 1.8 + ab));
  float fb = smoothstep(0.35, 0.9, fbm(q * 2.2 + w * 1.8 - ab));
  vec3 col = vec3(fr, f, fb) * spot * 0.55 + vec3(0.02) * spot;
  return col * intro;
}

vec3 ring(vec2 p, float t, float intro) {
  float R = 0.48 * (0.7 + 0.3 * intro);
  float d = abs(length(p) - R);
  float core = exp(-d * 120.0);
  float glow = exp(-d * 9.0) * 0.5;
  float ab = 0.006;
  float r = exp(-abs(length(p) - R - ab) * 120.0);
  float b = exp(-abs(length(p) - R + ab) * 120.0);
  // A slow-moving bright arc so it is not static.
  float a = atan(p.y, p.x);
  float arc = 0.5 + 0.5 * cos(a - t * 0.3);
  vec3 col = vec3(r, core, b) * (0.5 + 0.7 * arc) + vec3(0.85, 0.9, 1.0) * glow * (0.6 + 0.4 * arc);
  col += vec3(0.02) * exp(-length(p) * 1.5);
  return col * intro;
}

vec3 horizon(vec2 p, float t, float intro) {
  // Perspective floor grid running to a glowing horizon just above centre.
  float hy = 0.12;
  vec3 col = vec3(0.0);
  float glow = exp(-abs(p.y - hy) * 9.0) * 0.35;
  col += vec3(0.85, 0.9, 1.0) * glow;
  if (p.y < hy) {
    float depth = hy - p.y;
    float z = 0.12 / max(depth, 0.001);
    vec2 g = vec2(p.x * z * 2.2, z - t * 0.25);
    vec2 f = abs(fract(g) - 0.5);
    float line = min(f.x, f.y);
    float grid = 1.0 - smoothstep(0.0, 0.03 + 0.06 * depth, line);
    float fade = exp(-depth * 3.5) * smoothstep(0.0, 0.05, depth);
    col += vec3(0.9) * grid * fade * 0.45;
  }
  return col * intro;
}

void main() {
  vec2 p = (gl_FragCoord.xy - 0.5 * u_res) / u_res.y;
  p.y += 0.06;
  float intro = smoothstep(0.0, 1.0, u_intro);
  float t = u_time;
  vec3 col;
  if (u_variant == 0)      col = orb(p, 0.52 * (0.6 + 0.4 * intro), t, intro, false);
  else if (u_variant == 1) col = orb(p, 0.52 * (0.6 + 0.4 * intro), t, intro, true);
  else if (u_variant == 2) col = smoke(p, t, intro);
  else if (u_variant == 3) col = ring(p, t, intro);
  else                     col = horizon(p, t, intro);
  gl_FragColor = vec4(col, 1.0);
}
`;

export function SphereCanvas({
  introSeconds = 2.5,
  variant = "glass",
}: {
  introSeconds?: number;
  variant?: BackgroundVariant;
}) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;

    // Read before the context exists: it decides whether the drawing buffer
    // is preserved.
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // Reduced motion paints one still frame and never animates, so that frame
    // has to survive being presented. With the default preserveDrawingBuffer
    // of false the browser may discard it -- a headless screenshot showed pure
    // black where the ring should be. Animated mode repaints every frame and
    // does not pay for the preserved buffer.
    const gl = canvas.getContext("webgl", {
      antialias: false,
      alpha: false,
      preserveDrawingBuffer: reduced,
    });
    if (!gl) return;

    const compile = (type: number, src: string) => {
      const s = gl.createShader(type)!;
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
        console.warn(gl.getShaderInfoLog(s));
        return null;
      }
      return s;
    };
    const vs = compile(gl.VERTEX_SHADER, VERTEX);
    const fs = compile(gl.FRAGMENT_SHADER, FRAGMENT);
    if (!vs || !fs) return;

    const program = gl.createProgram()!;
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);
    gl.useProgram(program);

    const quad = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, quad);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const aPos = gl.getAttribLocation(program, "a_pos");
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

    const uRes = gl.getUniformLocation(program, "u_res");
    const uTime = gl.getUniformLocation(program, "u_time");
    const uIntro = gl.getUniformLocation(program, "u_intro");
    const uVariant = gl.getUniformLocation(program, "u_variant");
    gl.uniform1i(uVariant, VARIANT_INDEX[variant] ?? 0);

    const start = performance.now();
    let frame = 0;

    const paint = () => {
      const t = (performance.now() - start) / 1000;
      gl.uniform1f(uTime, reduced ? 0 : t);
      gl.uniform1f(uIntro, reduced ? 1 : Math.min(1, t / introSeconds));
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    };

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      canvas.width = Math.floor(window.innerWidth * dpr);
      canvas.height = Math.floor(window.innerHeight * dpr);
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.uniform2f(uRes, canvas.width, canvas.height);
      // Resizing clears the canvas. The animation loop repaints on its next
      // frame; with reduced motion there is no loop, so without this the
      // background would stay black after the first resize.
      if (reduced) paint();
    };
    resize();
    window.addEventListener("resize", resize);

    const loop = () => {
      paint();
      if (!document.hidden) frame = requestAnimationFrame(loop);
    };
    const onVisibility = () => {
      cancelAnimationFrame(frame);
      if (!reduced && !document.hidden) frame = requestAnimationFrame(loop);
    };
    document.addEventListener("visibilitychange", onVisibility);
    if (!reduced) frame = requestAnimationFrame(loop);

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", onVisibility);
      gl.deleteProgram(program);
    };
  }, [introSeconds, variant]);

  return (
    <canvas
      ref={ref}
      aria-hidden
      className="pointer-events-none fixed inset-0 z-0 h-full w-full"
    />
  );
}
