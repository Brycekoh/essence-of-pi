"use client";

import { useEffect, useRef } from "react";

// The centrepiece: a glass sphere that fades and grows in over the first
// couple of seconds, then slowly turns. It sits behind the upload panel and
// reads as refracted light -- a swirling monochrome texture with a touch of
// chromatic split at the edges, a bright fresnel rim, and a soft halo.
//
// One fragment shader on a quad. No raymarching: the "sphere" is a disc whose
// surface normal is reconstructed from its radius, which is all the lighting
// needs and a fraction of the cost.

const VERTEX = `
attribute vec2 a_pos;
void main() { gl_Position = vec4(a_pos, 0.0, 1.0); }
`;

const FRAGMENT = `
precision highp float;
uniform vec2  u_res;
uniform float u_time;
uniform float u_intro;   // 0 -> 1 over the intro

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

// The texture seen through the glass, sampled at a warped position so it
// looks bent by the surface rather than painted on it.
float lens(vec2 uv, float z, float t, float shift) {
  float bend = 1.0 + 0.45 * (1.0 - z);
  vec2 q = uv * bend;
  float c = cos(t * 0.12), s = sin(t * 0.12);
  q = mat2(c, -s, s, c) * q;
  q += shift;
  float w = fbm(q * 2.2 + t * 0.05);
  return fbm(q * 3.5 + w * 1.6 - t * 0.03);
}

void main() {
  vec2 p = (gl_FragCoord.xy - 0.5 * u_res) / u_res.y;
  p.y += 0.06;   // sit a little low, behind the panel

  float intro = smoothstep(0.0, 1.0, u_intro);
  float R = 0.52 * (0.6 + 0.4 * intro);
  float d = length(p);

  vec3 col = vec3(0.0);

  // Halo outside the sphere: soft, wide, slightly cool.
  float halo = exp(-max(d - R, 0.0) * 6.0) * 0.55;
  col += vec3(0.85, 0.9, 1.0) * halo * intro;

  if (d < R) {
    vec2 uv = p / R;
    float z = sqrt(max(0.0, 1.0 - dot(uv, uv)));   // surface normal z
    float t = u_time;

    // Chromatic split: three samples, offset a little more toward the rim.
    float rim = 1.0 - z;
    float ab = 0.012 + 0.03 * rim;
    float r = lens(uv, z, t, ab);
    float g = lens(uv, z, t, 0.0);
    float b = lens(uv, z, t, -ab);
    vec3 tex = vec3(r, g, b);
    tex = smoothstep(0.25, 0.85, tex);           // crisp facets, not mud
    tex = mix(vec3(dot(tex, vec3(0.333))), tex, 0.55);  // mostly monochrome

    // Lighting: a key light up-left, a fresnel rim, a specular highlight.
    vec3 n = vec3(uv, z);
    vec3 l = normalize(vec3(-0.45, 0.6, 0.65));
    float diff = 0.35 + 0.65 * max(dot(n, l), 0.0);
    float fres = pow(rim, 2.5);
    float spec = pow(max(dot(reflect(-l, n), vec3(0, 0, 1)), 0.0), 40.0);

    // Kept dim: text and panels sit on top of this, and the rim is what
    // should read, not the interior.
    vec3 body = tex * diff * 0.5 + vec3(0.9, 0.95, 1.0) * fres * 0.85 + spec * 0.5;
    // Anti-aliased edge.
    float edge = smoothstep(R, R - 0.004, d);
    col = mix(col, body, edge);
  }

  // Fade the whole thing in with the intro.
  col *= intro;
  gl_FragColor = vec4(col, 1.0);
}
`;

export function SphereCanvas({ introSeconds = 2.5 }: { introSeconds?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl", { antialias: false, alpha: false });
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

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      canvas.width = Math.floor(window.innerWidth * dpr);
      canvas.height = Math.floor(window.innerHeight * dpr);
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.uniform2f(uRes, canvas.width, canvas.height);
    };
    resize();
    window.addEventListener("resize", resize);

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const start = performance.now();
    let frame = 0;

    const draw = () => {
      const t = (performance.now() - start) / 1000;
      gl.uniform1f(uTime, reduced ? 0 : t);
      gl.uniform1f(uIntro, reduced ? 1 : Math.min(1, t / introSeconds));
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      if (!reduced && !document.hidden) frame = requestAnimationFrame(draw);
    };
    const onVisibility = () => {
      cancelAnimationFrame(frame);
      if (!document.hidden) frame = requestAnimationFrame(draw);
    };
    document.addEventListener("visibilitychange", onVisibility);
    frame = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", onVisibility);
      gl.deleteProgram(program);
    };
  }, [introSeconds]);

  return (
    <canvas
      ref={ref}
      aria-hidden
      className="pointer-events-none fixed inset-0 z-0 h-full w-full"
    />
  );
}
